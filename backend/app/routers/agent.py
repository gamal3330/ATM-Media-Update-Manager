from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import get_agent_atm
from ..cash_layout import normalized_cash_layout
from ..database import get_db
from ..models import ATM, AgentCommand, AgentLog, AtmCashSnapshot, AtmSwitchProbe, UpdatePackage, UpdateResult, UpdateTarget
from ..schemas import (
    AgentCommandAckRequest,
    AgentCommandRead,
    AgentConfigAckRequest,
    AgentConfigResponse,
    AgentModulesConfig,
    AgentLogRequest,
    AgentNoUpdate,
    AgentProgressRequest,
    AgentUpdateAvailable,
    HeartbeatRequest,
    HeartbeatResponse,
    AgentSwitchProbeRequest,
    AgentSwitchProbeResult,
    CashMonitoringRemoteConfig,
    MediaUpdateRemoteConfig,
    UpdateResultRequest,
)
from ..services.audit_service import write_audit
from ..services.package_service import ALLOWED_IMAGE_EXTENSIONS

router = APIRouter(prefix="/api/agent", tags=["agent"])


def effective_cash_provider(atm: ATM) -> str:
    if atm.cash_monitoring_enabled and atm.cash_provider == "vendor_cdm":
        return "xfs_cdm"
    return atm.cash_provider


def has_recent_cash_snapshot(db: Session, atm: ATM, now: datetime) -> bool:
    latest = (
        db.query(AtmCashSnapshot)
        .filter(AtmCashSnapshot.atm_id == atm.id)
        .order_by(AtmCashSnapshot.read_at.desc())
        .first()
    )
    if latest is None:
        return False
    read_at = latest.read_at
    if read_at.tzinfo is None:
        read_at = read_at.replace(tzinfo=timezone.utc)
    return now - read_at <= timedelta(minutes=atm.cash_stale_after_minutes)


def update_target_progress(
    target: UpdateTarget,
    *,
    phase: str,
    percent: int,
    message: str | None = None,
    bytes_downloaded: int | None = None,
    total_bytes: int | None = None,
) -> None:
    target.progress_phase = phase
    target.progress_percent = max(0, min(100, percent))
    target.last_progress_at = datetime.now(timezone.utc)
    if message is not None:
        target.progress_message = message
    if bytes_downloaded is not None:
        target.bytes_downloaded = bytes_downloaded
    if total_bytes is not None:
        target.total_bytes = total_bytes


@router.get("/config", response_model=AgentConfigResponse)
def get_agent_config(atm: ATM = Depends(get_agent_atm)) -> AgentConfigResponse:
    allowed_extensions = sorted(extension.lstrip(".") for extension in ALLOWED_IMAGE_EXTENSIONS)
    return AgentConfigResponse(
        atm_id=atm.atm_id,
        config_version=atm.config_version,
        config_sync_interval_seconds=atm.config_sync_interval_seconds,
        modules=AgentModulesConfig(
            media_update=MediaUpdateRemoteConfig(
                enabled=atm.media_update_enabled,
                media_path=atm.media_path,
                backup_path=atm.backup_path,
                temp_path=atm.temp_path,
                check_interval_seconds=atm.check_interval_seconds,
                allowed_extensions=allowed_extensions,
            ),
            cash_monitoring=CashMonitoringRemoteConfig(
                enabled=atm.cash_monitoring_enabled,
                atm_cash_mode=atm.atm_cash_mode,
                provider=effective_cash_provider(atm),
                xfs_profile=atm.xfs_profile,
                xfs_logical_service=atm.xfs_logical_service,
                xfs_msxfs_path=atm.xfs_msxfs_path,
                xfs_version_range=atm.xfs_version_range,
                read_interval_seconds=atm.cash_read_interval_seconds,
                cash_layout=normalized_cash_layout(atm.cash_layout_json),
                stale_after_minutes=atm.cash_stale_after_minutes,
            ),
        ),
        media_path=atm.media_path,
        backup_path=atm.backup_path,
        temp_path=atm.temp_path,
        heartbeat_interval_seconds=atm.heartbeat_interval_seconds,
        check_interval_seconds=atm.check_interval_seconds,
        allowed_extensions=allowed_extensions,
    )


@router.post("/config-ack")
def acknowledge_agent_config(
    payload: AgentConfigAckRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if payload.atm_id and payload.atm_id != atm.atm_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM ID does not match credentials")

    atm.last_config_sync_at = datetime.now(timezone.utc)
    if payload.success:
        atm.applied_config_version = payload.applied_config_version
        atm.last_config_error = None
        if payload.enabled_modules:
            statuses = dict(atm.module_status_json or {})
            for module_name in payload.enabled_modules:
                statuses.setdefault(module_name, "configured")
            atm.module_status_json = statuses
    else:
        atm.last_config_error = payload.message or "Config sync failed"

    db.commit()
    return {"ok": True}


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    payload: HeartbeatRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> HeartbeatResponse:
    if payload.atm_id and payload.atm_id != atm.atm_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM ID does not match credentials")

    atm.status = "online"
    now = datetime.now(timezone.utc)
    atm.last_seen = now
    atm.last_heartbeat_at = now
    if payload.agent_version:
        atm.agent_version = payload.agent_version
    if payload.latency_ms is not None:
        atm.latency_ms = payload.latency_ms
    if payload.module_statuses:
        statuses = dict(atm.module_status_json or {})
        incoming_statuses = dict(payload.module_statuses)
        if incoming_statuses.get("cash_monitoring") == "error" and has_recent_cash_snapshot(db, atm, now):
            incoming_statuses["cash_monitoring"] = "running"
        statuses.update(incoming_statuses)
        atm.module_status_json = statuses
    if payload.service_status:
        atm.status = payload.service_status
    current_version = payload.current_package_version or payload.current_version
    if current_version:
        atm.current_package_version = current_version
        atm.last_image_version = current_version
    if payload.applied_config_version is not None:
        atm.applied_config_version = payload.applied_config_version
    pending = (
        db.query(UpdateTarget)
        .filter(UpdateTarget.atm_id == atm.id, UpdateTarget.status.in_(["pending", "downloading"]))
        .count()
    )
    db.commit()
    return HeartbeatResponse(pending_updates=pending)


@router.get("/check-update", response_model=AgentUpdateAvailable | AgentNoUpdate)
def check_update(
    request: Request,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> AgentUpdateAvailable | AgentNoUpdate:
    atm.status = "online"
    atm.last_seen = datetime.now(timezone.utc)

    target = (
        db.query(UpdateTarget)
        .join(UpdatePackage)
        .filter(UpdateTarget.atm_id == atm.id, UpdateTarget.status == "pending")
        .order_by(UpdatePackage.created_at.asc())
        .first()
    )
    if not target:
        db.commit()
        return AgentNoUpdate(update_available=False)

    target.last_checked_at = datetime.now(timezone.utc)
    update_target_progress(target, phase="pending", percent=0, message="Update is ready for download")
    db.commit()

    package = target.package
    download_url = str(request.url_for("download_package", package_id=package.id))
    return AgentUpdateAvailable(
        update_available=True,
        has_update=True,
        package_id=package.id,
        version=package.version,
        sha256=package.sha256,
        size_bytes=package.size_bytes,
        download_url=download_url,
    )


@router.get("/commands", response_model=list[AgentCommandRead])
def list_agent_commands(
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> list[AgentCommand]:
    return (
        db.query(AgentCommand)
        .filter(
            AgentCommand.atm_id == atm.id,
            AgentCommand.status == "pending",
            AgentCommand.command_type == "cash_read_now",
        )
        .order_by(AgentCommand.created_at.asc())
        .limit(5)
        .all()
    )


@router.post("/commands/{command_id}/ack", response_model=AgentCommandRead)
def acknowledge_agent_command(
    command_id: int,
    payload: AgentCommandAckRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> AgentCommand:
    command = (
        db.query(AgentCommand)
        .filter(AgentCommand.id == command_id, AgentCommand.atm_id == atm.id)
        .first()
    )
    if not command:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent command not found")
    if command.command_type != "cash_read_now":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Only read-only cash read commands are enabled")

    now = datetime.now(timezone.utc)
    command.status = payload.status
    if payload.status == "acknowledged":
        command.acknowledged_at = now
        command.last_error = None
    if payload.status in {"completed", "failed"}:
        if command.acknowledged_at is None:
            command.acknowledged_at = now
        command.completed_at = now
        command.last_error = payload.message if payload.status == "failed" else None

    write_audit(
        db,
        actor_type="agent",
        actor_id=atm.atm_id,
        action="agent_command_reported",
        entity_type="agent_command",
        entity_id=str(command.id),
        details={"command_type": command.command_type, "status": payload.status, "message": payload.message},
    )
    db.commit()
    db.refresh(command)
    return command


@router.get("/switch-probe", response_model=AgentSwitchProbeRequest)
def get_switch_probe_request(
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> AgentSwitchProbeRequest:
    probe = (
        db.query(AtmSwitchProbe)
        .filter(AtmSwitchProbe.atm_id == atm.id, AtmSwitchProbe.status == "pending")
        .order_by(AtmSwitchProbe.requested_at.asc())
        .first()
    )
    if not probe:
        return AgentSwitchProbeRequest(has_probe=False)

    probe.status = "running"
    probe.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(probe)
    return AgentSwitchProbeRequest(has_probe=True, probe=probe)


@router.post("/switch-probe-result")
def report_switch_probe_result(
    payload: AgentSwitchProbeResult,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    probe = (
        db.query(AtmSwitchProbe)
        .filter(AtmSwitchProbe.id == payload.probe_id, AtmSwitchProbe.atm_id == atm.id)
        .first()
    )
    if not probe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Switch probe not found")

    now = datetime.now(timezone.utc)
    probe.status = payload.status
    probe.completed_at = now
    probe.latency_ms = payload.latency_ms
    probe.error_message = payload.error_message if payload.status == "failed" else None

    atm.last_switch_probe_status = payload.status
    atm.last_switch_probe_latency_ms = payload.latency_ms
    atm.last_switch_probe_error = probe.error_message
    atm.last_switch_probe_at = now

    write_audit(
        db,
        actor_type="agent",
        actor_id=atm.atm_id,
        action="switch_probe_reported",
        entity_type="atm_switch_probe",
        entity_id=str(probe.id),
        details={
            "host": probe.host,
            "port": probe.port,
            "status": probe.status,
            "latency_ms": probe.latency_ms,
            "error_message": probe.error_message,
        },
    )
    db.commit()
    return {"ok": True}


@router.get("/download/{package_id}", name="download_package")
def download_package(
    package_id: int,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> FileResponse:
    target = (
        db.query(UpdateTarget)
        .filter(UpdateTarget.atm_id == atm.id, UpdateTarget.package_id == package_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package is not assigned to this ATM")

    package = db.query(UpdatePackage).filter(UpdatePackage.id == package_id).first()
    if not package or not Path(package.storage_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package file not found")

    target.status = "downloading"
    target.attempt_count += 1
    target.last_checked_at = datetime.now(timezone.utc)
    update_target_progress(
        target,
        phase="downloading",
        percent=1,
        message="Download started",
        bytes_downloaded=0,
        total_bytes=package.size_bytes,
    )
    db.commit()
    return FileResponse(
        package.storage_path,
        media_type="application/zip",
        filename=package.original_filename,
    )


@router.post("/progress")
def report_progress(
    payload: AgentProgressRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    target = (
        db.query(UpdateTarget)
        .filter(UpdateTarget.atm_id == atm.id, UpdateTarget.package_id == payload.package_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned package not found")

    if payload.phase in {"downloading", "applying", "rollback"} and target.status not in {"applied", "failed"}:
        target.status = "downloading"
    if payload.phase == "failed":
        target.status = "failed"
        target.last_error = payload.message
    if payload.phase == "applied":
        target.status = "applied"

    update_target_progress(
        target,
        phase=payload.phase,
        percent=payload.progress_percent,
        message=payload.message,
        bytes_downloaded=payload.bytes_downloaded,
        total_bytes=payload.total_bytes,
    )
    db.commit()
    return {"ok": True}


@router.post("/report-result")
def report_result(
    payload: UpdateResultRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if payload.atm_id and payload.atm_id != atm.atm_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM ID does not match credentials")

    target = (
        db.query(UpdateTarget)
        .filter(UpdateTarget.atm_id == atm.id, UpdateTarget.package_id == payload.package_id)
        .first()
    )
    package = db.query(UpdatePackage).filter(UpdatePackage.id == payload.package_id).first()
    if not target or not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned package not found")

    result_status = "applied" if payload.status == "success" else "failed"
    target.status = result_status
    target.completed_at = datetime.now(timezone.utc)
    target.last_error = payload.message if payload.status == "failed" else None
    update_target_progress(
        target,
        phase="applied" if payload.status == "success" else "failed",
        percent=100 if payload.status == "success" else target.progress_percent,
        message=payload.message,
    )
    if payload.status == "success":
        atm.current_package_version = payload.version or package.version
        atm.last_image_version = payload.version or package.version

    result = UpdateResult(
        atm_id=atm.id,
        package_id=package.id,
        status=result_status,
        message=payload.message,
        started_at=payload.started_at,
        finished_at=payload.finished_at,
    )
    db.add(result)
    write_audit(
        db,
        actor_type="agent",
        actor_id=atm.atm_id,
        action="update_result_reported",
        entity_type="update_package",
        entity_id=str(package.id),
        details={"status": result_status, "message": payload.message, "rollback_done": payload.rollback_done},
    )
    db.commit()
    return {"ok": True}


@router.post("/logs")
def submit_log(
    payload: AgentLogRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if payload.atm_id and payload.atm_id != atm.atm_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM ID does not match credentials")

    context = payload.context
    if context is None and payload.details is not None:
        context = {"details": payload.details} if isinstance(payload.details, str) else payload.details
    log = AgentLog(
        atm_id=atm.id,
        level=payload.level,
        message=payload.message,
        context=context,
    )
    db.add(log)
    db.commit()
    return {"ok": True}
