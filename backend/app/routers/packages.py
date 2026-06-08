from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..auth import require_page
from ..database import get_db
from ..models import ATM, UpdatePackage, UpdateTarget, User
from ..schemas import PackageAssignRequest, PackageAssignResponse, PackageDetails, PackageSummary
from ..services.audit_service import write_audit
from ..services.package_service import create_package_from_upload

router = APIRouter(prefix="/api/packages", tags=["packages"])


def reset_target_for_retry(target: UpdateTarget) -> None:
    target.status = "pending"
    target.last_error = None
    target.completed_at = None
    target.progress_percent = 0
    target.progress_phase = "pending"
    target.progress_message = "Retry requested"
    target.bytes_downloaded = None
    target.total_bytes = None
    target.last_progress_at = None


@router.get("", response_model=list[PackageSummary])
def list_packages(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("packages")),
) -> list[PackageSummary]:
    packages = db.query(UpdatePackage).order_by(UpdatePackage.created_at.desc()).all()
    summaries: list[PackageSummary] = []
    for package in packages:
        counts = dict(
            db.query(UpdateTarget.status, func.count(UpdateTarget.id))
            .filter(UpdateTarget.package_id == package.id)
            .group_by(UpdateTarget.status)
            .all()
        )
        summaries.append(
            PackageSummary(
                id=package.id,
                version=package.version,
                original_filename=package.original_filename,
                sha256=package.sha256,
                size_bytes=package.size_bytes,
                notes=package.notes,
                created_at=package.created_at,
                total_targets=sum(counts.values()),
                pending_targets=counts.get("pending", 0) + counts.get("downloading", 0),
                applied_targets=counts.get("applied", 0),
                failed_targets=counts.get("failed", 0),
            )
        )
    return summaries


@router.get("/{package_id}", response_model=PackageDetails)
def get_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("packages")),
) -> UpdatePackage:
    package = (
        db.query(UpdatePackage)
        .options(joinedload(UpdatePackage.targets).joinedload(UpdateTarget.atm))
        .filter(UpdatePackage.id == package_id)
        .first()
    )
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")
    return package


@router.post("/upload", response_model=PackageSummary, status_code=status.HTTP_201_CREATED)
def upload_package(
    file: UploadFile = File(...),
    version: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("upload")),
) -> PackageSummary:
    package = create_package_from_upload(db, upload=file, version=version, notes=notes, created_by=current_user)
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="package_uploaded",
        entity_type="update_package",
        entity_id=str(package.id),
        details={
            "version": package.version,
            "filename": Path(package.original_filename).name,
            "sha256": package.sha256,
        },
    )
    db.commit()
    db.refresh(package)
    return PackageSummary(
        id=package.id,
        version=package.version,
        original_filename=package.original_filename,
        sha256=package.sha256,
        size_bytes=package.size_bytes,
        notes=package.notes,
        created_at=package.created_at,
    )


@router.post("/{package_id}/assign", response_model=PackageAssignResponse)
def assign_package(
    package_id: int,
    payload: PackageAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("packages")),
) -> PackageAssignResponse:
    package = db.query(UpdatePackage).filter(UpdatePackage.id == package_id).first()
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")

    atms = db.query(ATM).filter(ATM.atm_id.in_(payload.atm_ids)).all()
    found_ids = {atm.atm_id for atm in atms}
    missing = sorted(set(payload.atm_ids) - found_ids)
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"missing_atm_ids": missing})

    targets: list[UpdateTarget] = []
    assigned = 0
    for atm in atms:
        target = (
            db.query(UpdateTarget)
            .filter(UpdateTarget.package_id == package.id, UpdateTarget.atm_id == atm.id)
            .first()
        )
        if target:
            if target.status in {"failed", "downloading"}:
                reset_target_for_retry(target)
            targets.append(target)
            continue
        target = UpdateTarget(package_id=package.id, atm_id=atm.id, status="pending")
        db.add(target)
        targets.append(target)
        assigned += 1

    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="package_assigned",
        entity_type="update_package",
        entity_id=str(package.id),
        details={"atm_ids": payload.atm_ids, "new_targets": assigned},
    )
    db.commit()
    for target in targets:
        db.refresh(target)
    return PackageAssignResponse(package_id=package.id, assigned=assigned, targets=targets)


@router.post("/{package_id}/retry-failed", response_model=PackageAssignResponse)
def retry_failed_targets(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("packages")),
) -> PackageAssignResponse:
    package = db.query(UpdatePackage).filter(UpdatePackage.id == package_id).first()
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")

    targets = (
        db.query(UpdateTarget)
        .join(ATM)
        .filter(UpdateTarget.package_id == package.id, UpdateTarget.status == "failed")
        .all()
    )
    for target in targets:
        reset_target_for_retry(target)

    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="package_failed_targets_retried",
        entity_type="update_package",
        entity_id=str(package.id),
        details={"atm_ids": [target.atm.atm_id for target in targets], "retried_targets": len(targets)},
    )
    db.commit()
    for target in targets:
        db.refresh(target)
    return PackageAssignResponse(package_id=package.id, assigned=len(targets), targets=targets)
