from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import get_agent_atm
from ..cash_layout import normalized_cash_layout
from ..config import settings
from ..database import get_db
from ..models import (
    ATM,
    AgentCommand,
    AgentLog,
    AgentPackage,
    AgentUpdateTarget,
    AtmCashSnapshot,
    AtmJournalEvent,
    AtmSwitchProbe,
    UpdatePackage,
    UpdateResult,
    UpdateTarget,
)
from ..schemas import (
    AgentCommandAckRequest,
    AgentCommandRead,
    AgentConfigAckRequest,
    AgentConfigResponse,
    AgentModulesConfig,
    AgentLogRequest,
    AgentNoUpdate,
    AgentProgressRequest,
    AgentSelfUpdateAvailable,
    AgentSelfUpdateProgressRequest,
    AgentSelfUpdateResultRequest,
    AgentSwitchProbeSnapshot,
    AgentUpdateAvailable,
    HeartbeatRequest,
    HeartbeatResponse,
    AgentSwitchProbeRequest,
    AgentSwitchProbeResult,
    CashMonitoringRemoteConfig,
    JournalEventPayload,
    JournalEventsRequest,
    JournalEventsResponse,
    JournalReaderRemoteConfig,
    MediaUpdateRemoteConfig,
    UpdateResultRequest,
)
from ..services.audit_service import write_audit
from ..services.agent_update_service import mark_stale_agent_update_targets
from ..services.notification_service import notify_journal_out_of_service, notify_switch_probe_failed
from ..services.package_service import ALLOWED_IMAGE_EXTENSIONS

router = APIRouter(prefix="/api/agent", tags=["agent"])
AGENT_UPDATE_ACTIVE_WINDOW = timedelta(minutes=30)
GRG_JOURNAL_GLOB = r"D:\Program Files\DTATMW\Bin\ATMAPP\Log\EJ*.log"
NCR_EJDATA_GLOB = r"C:\Program Files (x86)\NCR APTRA\Advance NDC\Data\EJDATA.LOG"
NCR_MERGED_TRACE_GLOB = r"C:\Program Files (x86)\NCR APTRA\Advance NDC\Debug\MergedTrace_*.log"
NCR_JOURNAL_GLOB = f"{NCR_MERGED_TRACE_GLOB};{NCR_EJDATA_GLOB}"


def effective_cash_provider(atm: ATM) -> str:
    if atm.cash_provider in {"mock", "vendor_cdm"}:
        return "xfs_cdm"
    return atm.cash_provider


def effective_journal_provider(atm: ATM) -> str:
    if (atm.xfs_profile or "").lower() == "ncr_aptra":
        return "ncr_ej"
    return "grg_ej"


def effective_journal_log_glob(atm: ATM) -> str:
    configured = (atm.journal_log_glob or "").strip()
    if effective_journal_provider(atm) == "ncr_ej" and (
        not configured or configured in {GRG_JOURNAL_GLOB, NCR_EJDATA_GLOB}
    ):
        return NCR_JOURNAL_GLOB
    return configured or GRG_JOURNAL_GLOB


def journal_reader_is_enabled(atm: ATM) -> bool:
    return bool(atm.journal_reader_enabled or (atm.xfs_profile or "").lower() in {"grg", "ncr_aptra"})


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


def active_agent_update_download_count(db: Session, package_id: int, now: datetime) -> int:
    cutoff = now - AGENT_UPDATE_ACTIVE_WINDOW
    return (
        db.query(AgentUpdateTarget.id)
        .filter(
            AgentUpdateTarget.agent_package_id == package_id,
            AgentUpdateTarget.status.in_(["downloading", "applying"]),
            or_(
                AgentUpdateTarget.last_progress_at >= cutoff,
                AgentUpdateTarget.last_checked_at >= cutoff,
            ),
        )
        .count()
    )


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


def update_agent_target_progress(
    target: AgentUpdateTarget,
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
        switch_probe_host=atm.switch_probe_host,
        switch_probe_port=atm.switch_probe_port,
        switch_probe_interval_seconds=atm.switch_probe_interval_seconds,
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
            journal_reader=JournalReaderRemoteConfig(
                enabled=journal_reader_is_enabled(atm),
                provider=effective_journal_provider(atm),
                log_glob=effective_journal_log_glob(atm),
                read_interval_seconds=atm.journal_read_interval_seconds,
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
    pending += (
        db.query(AgentUpdateTarget)
        .filter(AgentUpdateTarget.atm_id == atm.id, AgentUpdateTarget.status.in_(["pending", "downloading", "applying"]))
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
    download_url = f"/api/agent/download/{package.id}"
    return AgentUpdateAvailable(
        update_available=True,
        has_update=True,
        package_id=package.id,
        version=package.version,
        sha256=package.sha256,
        size_bytes=package.size_bytes,
        download_url=download_url,
    )


@router.get("/check-agent-update", response_model=AgentSelfUpdateAvailable | AgentNoUpdate)
def check_agent_update(
    request: Request,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> AgentSelfUpdateAvailable | AgentNoUpdate:
    atm.status = "online"
    now = datetime.now(timezone.utc)
    atm.last_seen = now
    mark_stale_agent_update_targets(db, atm_id=atm.id, now=now)

    target = (
        db.query(AgentUpdateTarget)
        .join(AgentPackage)
        .filter(AgentUpdateTarget.atm_id == atm.id, AgentUpdateTarget.status == "pending")
        .order_by(AgentPackage.created_at.asc())
        .first()
    )
    if not target:
        db.commit()
        return AgentNoUpdate(update_available=False)

    if settings.agent_update_max_active_downloads > 0:
        active_downloads = active_agent_update_download_count(db, target.agent_package_id, now)
        if active_downloads >= settings.agent_update_max_active_downloads:
            db.commit()
            return AgentNoUpdate(update_available=False)

    target.last_checked_at = now
    update_agent_target_progress(
        target,
        phase="pending",
        percent=0,
        message="Agent update is ready for download",
    )
    db.commit()

    package = target.package
    return AgentSelfUpdateAvailable(
        update_available=True,
        has_update=True,
        agent_package_id=package.id,
        version=package.version,
        architecture=package.architecture,
        agent_sha256=package.agent_sha256,
        agent_size_bytes=package.agent_size_bytes,
        agent_download_url=f"/api/agent/agent-update-download/{package.id}/agent",
        updater_sha256=package.updater_sha256,
        updater_size_bytes=package.updater_size_bytes,
        updater_download_url=f"/api/agent/agent-update-download/{package.id}/updater",
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


@router.post("/switch-probe-snapshot")
def report_periodic_switch_probe(
    payload: AgentSwitchProbeSnapshot,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    now = datetime.now(timezone.utc)
    previous_status = atm.last_switch_probe_status
    host = payload.host or atm.switch_probe_host
    port = payload.port or atm.switch_probe_port
    error_message = payload.error_message if payload.status == "failed" else None

    probe = AtmSwitchProbe(
        atm_id=atm.id,
        host=host,
        port=port,
        status=payload.status,
        requested_by="agent:auto",
        requested_at=now,
        started_at=now,
        completed_at=now,
        latency_ms=payload.latency_ms,
        error_message=error_message,
    )
    db.add(probe)

    atm.last_switch_probe_status = payload.status
    atm.last_switch_probe_latency_ms = payload.latency_ms
    atm.last_switch_probe_error = error_message
    atm.last_switch_probe_at = now

    write_audit(
        db,
        actor_type="agent",
        actor_id=atm.atm_id,
        action="switch_probe_reported",
        entity_type="atm_switch_probe",
        entity_id="periodic",
        details={
            "host": host,
            "port": port,
            "status": payload.status,
            "latency_ms": payload.latency_ms,
            "error_message": error_message,
            "periodic": True,
        },
    )
    if payload.status == "failed" and previous_status != "failed":
        notify_switch_probe_failed(db, atm, host, port, error_message or "Switch TCP probe failed", now)
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
    storage_path = package.storage_path
    original_filename = package.original_filename
    db.commit()
    db.close()
    return FileResponse(
        storage_path,
        media_type="application/zip",
        filename=original_filename,
    )


@router.get("/agent-update-download/{package_id}/{file_kind}", name="download_agent_update_file")
def download_agent_update_file(
    package_id: int,
    file_kind: str,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> FileResponse:
    if file_kind not in {"agent", "updater"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_kind must be agent or updater")

    target = (
        db.query(AgentUpdateTarget)
        .filter(AgentUpdateTarget.atm_id == atm.id, AgentUpdateTarget.agent_package_id == package_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package is not assigned to this ATM")

    package = db.query(AgentPackage).filter(AgentPackage.id == package_id).first()
    if not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent package not found")

    path = Path(package.agent_storage_path if file_kind == "agent" else package.updater_storage_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent update file not found")

    size_bytes = package.agent_size_bytes if file_kind == "agent" else package.updater_size_bytes
    if target.status != "downloading":
        target.attempt_count += 1
    target.status = "downloading"
    target.last_checked_at = datetime.now(timezone.utc)
    update_agent_target_progress(
        target,
        phase="downloading",
        percent=1,
        message=f"{file_kind} download started",
        bytes_downloaded=0,
        total_bytes=size_bytes,
    )
    download_path = str(path)
    download_filename = "atm-agent.exe" if file_kind == "agent" else "agent-updater.exe"
    db.commit()
    db.close()
    return FileResponse(
        download_path,
        media_type="application/vnd.microsoft.portable-executable",
        filename=download_filename,
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


@router.post("/agent-update-progress")
def report_agent_update_progress(
    payload: AgentSelfUpdateProgressRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    target = (
        db.query(AgentUpdateTarget)
        .filter(AgentUpdateTarget.atm_id == atm.id, AgentUpdateTarget.agent_package_id == payload.agent_package_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned agent package not found")

    if payload.phase in {"downloading", "applying"} and target.status not in {"applied", "failed"}:
        target.status = payload.phase
    if payload.phase == "failed":
        target.status = "failed"
        target.last_error = payload.message
        target.completed_at = datetime.now(timezone.utc)
    if payload.phase == "applied":
        target.status = "applied"
        target.completed_at = datetime.now(timezone.utc)

    update_agent_target_progress(
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


@router.post("/agent-update-result")
def report_agent_update_result(
    payload: AgentSelfUpdateResultRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if payload.atm_id and payload.atm_id != atm.atm_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM ID does not match credentials")

    target = (
        db.query(AgentUpdateTarget)
        .filter(AgentUpdateTarget.atm_id == atm.id, AgentUpdateTarget.agent_package_id == payload.agent_package_id)
        .first()
    )
    package = db.query(AgentPackage).filter(AgentPackage.id == payload.agent_package_id).first()
    if not target or not package:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assigned agent package not found")

    result_status = "applied" if payload.status == "success" else "failed"
    target.status = result_status
    target.completed_at = datetime.now(timezone.utc)
    target.last_error = payload.message if payload.status == "failed" else None
    update_agent_target_progress(
        target,
        phase="applied" if payload.status == "success" else "failed",
        percent=100 if payload.status == "success" else target.progress_percent,
        message=payload.message,
    )
    if payload.status == "success":
        atm.agent_version = payload.version or package.version

    write_audit(
        db,
        actor_type="agent",
        actor_id=atm.atm_id,
        action="agent_update_result_reported",
        entity_type="agent_package",
        entity_id=str(package.id),
        details={"status": result_status, "version": payload.version or package.version, "message": payload.message},
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


JOURNAL_EVENT_LABELS = {
    "TRANSACTION_START": "Journal transaction started",
    "TRANSACTION_END": "Journal transaction ended",
    "TRANSACTION_SERIAL_NUMBER": "Journal transaction serial number",
    "DISPENSE_SUCCESS": "Journal dispense success",
    "PRESENT_SUCCESS": "Journal present success",
    "CARD_TAKEN": "Journal card taken",
    "TAKE_CASH_TIMEOUT": "Journal take cash timeout",
    "MONEY_TAKEN": "Journal money taken",
    "CASSETTE_OUT": "Journal cassette output",
    "LINE_DOWN": "Journal line down",
    "LINE_UP": "Journal line up",
    "ENTER_OFFLINE_MODE": "Journal entered offline mode",
    "EXIT_OFFLINE_MODE": "Journal exited offline mode",
    "ENTER_OUTOFSERVICE_MODE": "Journal entered out-of-service mode",
    "ENTER_INSERVICE_MODE": "Journal entered in-service mode",
    "ATM_POWER_UP": "Journal ATM power up",
    "PRINTER_EVENT": "Journal printer event",
}


def journal_log_message(event_type: str, payload) -> str:
    title = JOURNAL_EVENT_LABELS.get(event_type, f"Journal {event_type.lower().replace('_', ' ')}")
    if event_type == "TRANSACTION_END":
        parts = [title]
        if payload.transaction_type:
            parts.append(f"type={payload.transaction_type}")
        if payload.amount is not None:
            parts.append(f"amount={payload.amount}")
        if payload.currency:
            parts.append(f"currency={payload.currency}")
        if payload.rrn:
            parts.append(f"rrn={payload.rrn}")
        if payload.details.get("completed") is not None:
            parts.append(f"completed={payload.details.get('completed')}")
        return " | ".join(parts)
    if event_type == "CASSETTE_OUT":
        details = payload.details or {}
        return (
            f"{title} | cassette={details.get('cassette_no')} "
            f"out={details.get('out')} reject={details.get('reject')} deno={details.get('denomination')}"
        )
    return title


def has_journal_value(value) -> bool:
    return value not in (None, "", [], {})


def merge_existing_journal_event(event: AtmJournalEvent, payload: JournalEventPayload) -> bool:
    changed = False

    for attr in (
        "transaction_serial",
        "transaction_type",
        "amount",
        "currency",
        "rrn",
        "stan",
        "auth_code",
        "card_masked",
        "receipt_date",
    ):
        incoming = getattr(payload, attr)
        if has_journal_value(incoming) and not has_journal_value(getattr(event, attr)):
            setattr(event, attr, incoming)
            changed = True

    if payload.cassette_outputs and not event.cassette_outputs_json:
        event.cassette_outputs_json = payload.cassette_outputs
        changed = True

    if payload.details:
        current_details = dict(event.details_json or {})
        merged_details = dict(current_details)
        for key, incoming in payload.details.items():
            if not has_journal_value(incoming):
                continue
            current = merged_details.get(key)
            if not has_journal_value(current) or (incoming is True and current is False):
                merged_details[key] = incoming
        if merged_details != current_details:
            event.details_json = merged_details
            changed = True

    return changed


def find_existing_journal_event(db: Session, atm: ATM, payload: JournalEventPayload) -> AtmJournalEvent | None:
    existing = db.query(AtmJournalEvent).filter(AtmJournalEvent.event_uid == payload.event_uid).first()
    if existing:
        return existing

    if payload.event_type != "TRANSACTION_END":
        return None

    query = db.query(AtmJournalEvent).filter(
        AtmJournalEvent.atm_id == atm.id,
        AtmJournalEvent.event_type == payload.event_type,
    )
    if payload.transaction_type:
        query = query.filter(AtmJournalEvent.transaction_type == payload.transaction_type)
    if payload.rrn:
        query = query.filter(AtmJournalEvent.rrn == payload.rrn)
    elif payload.stan and payload.receipt_date:
        query = query.filter(AtmJournalEvent.stan == payload.stan, AtmJournalEvent.receipt_date == payload.receipt_date)
    else:
        return None
    return query.order_by(AtmJournalEvent.received_at.desc()).first()


@router.post("/journal-events", response_model=JournalEventsResponse)
def submit_journal_events(
    payload: JournalEventsRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> JournalEventsResponse:
    if payload.atm_id and payload.atm_id != atm.atm_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM ID does not match credentials")

    inserted = 0
    updated = 0
    skipped = 0
    for item in payload.events:
        exists = find_existing_journal_event(db, atm, item)
        if exists:
            if merge_existing_journal_event(exists, item):
                updated += 1
            else:
                skipped += 1
            continue

        event = AtmJournalEvent(
            atm_id=atm.id,
            event_uid=item.event_uid,
            source=item.source,
            event_type=item.event_type,
            severity=item.severity,
            message=item.message,
            file_path=item.file_path,
            line_number=item.line_number,
            transaction_serial=item.transaction_serial,
            transaction_type=item.transaction_type,
            amount=item.amount,
            currency=item.currency,
            rrn=item.rrn,
            stan=item.stan,
            auth_code=item.auth_code,
            card_masked=item.card_masked,
            receipt_date=item.receipt_date,
            cassette_outputs_json=item.cassette_outputs,
            details_json=item.details,
            occurred_at=item.occurred_at,
        )
        db.add(event)
        inserted += 1
        if item.event_type == "ENTER_OUTOFSERVICE_MODE":
            notify_journal_out_of_service(db, atm, event)

    if inserted or updated:
        atm.last_seen = datetime.now(timezone.utc)
    db.commit()
    return JournalEventsResponse(inserted=inserted, updated=updated, skipped=skipped)
