from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..auth import require_page
from ..database import get_db
from ..models import ATM, AgentPackage, AgentUpdateTarget, User
from ..schemas import (
    AgentPackageAssignRequest,
    AgentPackageAssignResponse,
    AgentPackageDetails,
    AgentPackageSummary,
)
from ..services.agent_update_service import mark_stale_agent_update_targets
from ..services.agent_package_service import create_agent_package_from_upload
from ..services.audit_service import write_audit

router = APIRouter(prefix="/api/agent-packages", tags=["agent-packages"])


def reset_agent_target_for_retry(target: AgentUpdateTarget) -> None:
    target.status = "pending"
    target.last_error = None
    target.completed_at = None
    target.progress_percent = 0
    target.progress_phase = "pending"
    target.progress_message = "Retry requested"
    target.bytes_downloaded = None
    target.total_bytes = None
    target.last_progress_at = None


@router.get("", response_model=list[AgentPackageSummary])
def list_agent_packages(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("agent-updates")),
) -> list[AgentPackageSummary]:
    if mark_stale_agent_update_targets(db):
        db.commit()
    packages = db.query(AgentPackage).order_by(AgentPackage.created_at.desc()).limit(limit).all()
    package_ids = [package.id for package in packages]
    counts_by_package: dict[int, dict[str, int]] = {package_id: {} for package_id in package_ids}
    if package_ids:
        count_rows = (
            db.query(AgentUpdateTarget.agent_package_id, AgentUpdateTarget.status, func.count(AgentUpdateTarget.id))
            .filter(AgentUpdateTarget.agent_package_id.in_(package_ids))
            .group_by(AgentUpdateTarget.agent_package_id, AgentUpdateTarget.status)
            .all()
        )
        for package_id, target_status, count in count_rows:
            counts_by_package.setdefault(package_id, {})[target_status] = count
    summaries: list[AgentPackageSummary] = []
    for package in packages:
        counts = counts_by_package.get(package.id, {})
        summaries.append(
            AgentPackageSummary(
                id=package.id,
                version=package.version,
                architecture=package.architecture,
                agent_original_filename=package.agent_original_filename,
                agent_sha256=package.agent_sha256,
                agent_size_bytes=package.agent_size_bytes,
                updater_original_filename=package.updater_original_filename,
                updater_sha256=package.updater_sha256,
                updater_size_bytes=package.updater_size_bytes,
                notes=package.notes,
                created_at=package.created_at,
                total_targets=sum(counts.values()),
                pending_targets=counts.get("pending", 0) + counts.get("downloading", 0) + counts.get("applying", 0),
                applied_targets=counts.get("applied", 0),
                failed_targets=counts.get("failed", 0),
            )
        )
    return summaries


@router.get("/{package_id}", response_model=AgentPackageDetails)
def get_agent_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("agent-updates")),
) -> AgentPackage:
    if mark_stale_agent_update_targets(db, package_id=package_id):
        db.commit()
    package = (
        db.query(AgentPackage)
        .options(joinedload(AgentPackage.targets).joinedload(AgentUpdateTarget.atm))
        .filter(AgentPackage.id == package_id)
        .first()
    )
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package not found")
    return package


@router.post("/upload", response_model=AgentPackageSummary, status_code=status.HTTP_201_CREATED)
def upload_agent_package(
    agent_file: UploadFile = File(...),
    updater_file: UploadFile = File(...),
    version: str = Form(...),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("agent-updates")),
) -> AgentPackageSummary:
    package = create_agent_package_from_upload(
        db,
        agent_upload=agent_file,
        updater_upload=updater_file,
        version=version,
        notes=notes,
        created_by=current_user,
    )
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="agent_package_uploaded",
        entity_type="agent_package",
        entity_id=str(package.id),
        details={
            "version": package.version,
            "architecture": package.architecture,
            "agent_filename": Path(package.agent_original_filename).name,
            "agent_sha256": package.agent_sha256,
            "updater_filename": Path(package.updater_original_filename).name,
            "updater_sha256": package.updater_sha256,
        },
    )
    db.commit()
    db.refresh(package)
    return AgentPackageSummary(
        id=package.id,
        version=package.version,
        architecture=package.architecture,
        agent_original_filename=package.agent_original_filename,
        agent_sha256=package.agent_sha256,
        agent_size_bytes=package.agent_size_bytes,
        updater_original_filename=package.updater_original_filename,
        updater_sha256=package.updater_sha256,
        updater_size_bytes=package.updater_size_bytes,
        notes=package.notes,
        created_at=package.created_at,
    )


@router.post("/{package_id}/assign", response_model=AgentPackageAssignResponse)
def assign_agent_package(
    package_id: int,
    payload: AgentPackageAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("agent-updates")),
) -> AgentPackageAssignResponse:
    package = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package not found")

    atms = db.query(ATM).filter(ATM.atm_id.in_(payload.atm_ids)).all()
    found_ids = {atm.atm_id for atm in atms}
    missing = sorted(set(payload.atm_ids) - found_ids)
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"missing_atm_ids": missing})

    targets: list[AgentUpdateTarget] = []
    assigned = 0
    for atm in atms:
        target = (
            db.query(AgentUpdateTarget)
            .filter(AgentUpdateTarget.agent_package_id == package.id, AgentUpdateTarget.atm_id == atm.id)
            .first()
        )
        if target:
            if target.status in {"failed", "downloading", "applying"}:
                reset_agent_target_for_retry(target)
            targets.append(target)
            continue
        target = AgentUpdateTarget(agent_package_id=package.id, atm_id=atm.id, status="pending")
        db.add(target)
        targets.append(target)
        assigned += 1

    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="agent_package_assigned",
        entity_type="agent_package",
        entity_id=str(package.id),
        details={"atm_ids": payload.atm_ids, "new_targets": assigned},
    )
    db.commit()
    for target in targets:
        db.refresh(target)
    return AgentPackageAssignResponse(agent_package_id=package.id, assigned=assigned, targets=targets)


@router.post("/{package_id}/retry-failed", response_model=AgentPackageAssignResponse)
def retry_failed_agent_targets(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("agent-updates")),
) -> AgentPackageAssignResponse:
    package = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package not found")

    targets = (
        db.query(AgentUpdateTarget)
        .join(ATM)
        .filter(AgentUpdateTarget.agent_package_id == package.id, AgentUpdateTarget.status == "failed")
        .all()
    )
    for target in targets:
        reset_agent_target_for_retry(target)

    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="agent_package_failed_targets_retried",
        entity_type="agent_package",
        entity_id=str(package.id),
        details={"atm_ids": [target.atm.atm_id for target in targets], "retried_targets": len(targets)},
    )
    db.commit()
    for target in targets:
        db.refresh(target)
    return AgentPackageAssignResponse(agent_package_id=package.id, assigned=len(targets), targets=targets)
