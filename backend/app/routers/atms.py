from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import generate_api_key, hash_api_key, require_any_page, require_page, user_has_page
from ..cash_layout import normalized_cash_layout
from ..database import get_db
from ..models import (
    ATM,
    AuditLog,
    AgentCommand,
    AgentLog,
    AtmAgentConfig,
    AtmCashAlert,
    AtmCashSnapshot,
    AtmCashThreshold,
    AtmCashUnit,
    AtmRejectRetractStatus,
    AtmSwitchProbe,
    NotificationDelivery,
    NotificationRecipient,
    UpdateResult,
    UpdateTarget,
    User,
)
from ..schemas import (
    AgentCommandRead,
    ATMDiagnostics,
    ATMCreate,
    ATMCreateResponse,
    AtmEventRead,
    ATMRead,
    ATMRebootRequest,
    ATMUpdate,
    SwitchProbeRequest,
    SwitchProbeRead,
)
from ..services.audit_service import write_audit

router = APIRouter(prefix="/api/atms", tags=["atms"])

CONFIG_FIELDS = {
    "media_path",
    "backup_path",
    "temp_path",
    "check_interval_seconds",
    "heartbeat_interval_seconds",
    "config_sync_interval_seconds",
    "media_update_enabled",
    "cash_monitoring_enabled",
    "cash_provider",
    "xfs_profile",
    "xfs_logical_service",
    "xfs_msxfs_path",
    "xfs_version_range",
    "atm_cash_mode",
    "cash_layout_json",
    "cash_read_interval_seconds",
    "cash_low_threshold_default",
    "cash_critical_threshold_default",
    "cash_stale_after_minutes",
    "switch_probe_host",
    "switch_probe_port",
    "switch_probe_interval_seconds",
}


def default_xfs_logical_service(xfs_profile: str | None) -> str:
    return "CDM" if xfs_profile == "grg" else "MediaDispenser1"


def record_agent_config_snapshot(db: Session, atm: ATM, updated_by: str | None) -> None:
    db.add(
        AtmAgentConfig(
            atm_id=atm.id,
            config_version=atm.config_version,
            heartbeat_interval_seconds=atm.heartbeat_interval_seconds,
            config_sync_interval_seconds=atm.config_sync_interval_seconds,
            media_update_enabled=atm.media_update_enabled,
            media_path=atm.media_path,
            backup_path=atm.backup_path,
            temp_path=atm.temp_path,
            media_check_interval_seconds=atm.check_interval_seconds,
            cash_monitoring_enabled=atm.cash_monitoring_enabled,
            cash_provider=atm.cash_provider,
            xfs_profile=atm.xfs_profile,
            xfs_logical_service=atm.xfs_logical_service,
            xfs_msxfs_path=atm.xfs_msxfs_path,
            xfs_version_range=atm.xfs_version_range,
            atm_cash_mode=atm.atm_cash_mode,
            cash_layout_json=atm.cash_layout_json,
            cash_read_interval_seconds=atm.cash_read_interval_seconds,
            cash_stale_after_minutes=atm.cash_stale_after_minutes,
            switch_probe_interval_seconds=atm.switch_probe_interval_seconds,
            updated_by=updated_by,
        )
    )


@router.get("", response_model=list[ATMRead])
def list_atms(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_page("dashboard", "atms", "cash")),
) -> list[ATM]:
    return db.query(ATM).order_by(ATM.branch, ATM.atm_id).all()


@router.post("", response_model=ATMCreateResponse, status_code=status.HTTP_201_CREATED)
def create_atm(
    payload: ATMCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("atms-manage")),
) -> ATMCreateResponse:
    if db.query(ATM).filter(ATM.atm_id == payload.atm_id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ATM ID already exists")

    api_key = generate_api_key()
    xfs_profile = payload.xfs_profile or "ncr_aptra"
    atm = ATM(
        atm_id=payload.atm_id,
        name=payload.name,
        vpn_ip=payload.vpn_ip,
        branch=payload.branch,
        status="offline",
        api_key_hash=hash_api_key(api_key),
        media_path=payload.media_path or "C:\\ATM\\Media",
        backup_path=payload.backup_path or "C:\\ATM\\Media_Backup",
        temp_path=payload.temp_path or "C:\\ATM\\Temp",
        check_interval_seconds=payload.check_interval_seconds or 300,
        heartbeat_interval_seconds=payload.heartbeat_interval_seconds or 60,
        config_sync_interval_seconds=payload.config_sync_interval_seconds or 120,
        media_update_enabled=True if payload.media_update_enabled is None else payload.media_update_enabled,
        cash_monitoring_enabled=False if payload.cash_monitoring_enabled is None else payload.cash_monitoring_enabled,
        cash_provider=payload.cash_provider or "xfs_cdm",
        xfs_profile=xfs_profile,
        xfs_logical_service=payload.xfs_logical_service or default_xfs_logical_service(xfs_profile),
        xfs_msxfs_path=payload.xfs_msxfs_path,
        xfs_version_range=payload.xfs_version_range or "0x00031E03",
        atm_cash_mode=payload.atm_cash_mode or "DISPENSE_ONLY",
        cash_layout_json=normalized_cash_layout(
            [item.model_dump() for item in payload.cash_layout] if payload.cash_layout is not None else None
        ),
        cash_read_interval_seconds=payload.cash_read_interval_seconds or 120,
        cash_low_threshold_default=payload.cash_low_threshold_default or 300,
        cash_critical_threshold_default=payload.cash_critical_threshold_default or 100,
        cash_stale_after_minutes=payload.cash_stale_after_minutes or 10,
        switch_probe_host=payload.switch_probe_host or "172.16.75.25",
        switch_probe_port=payload.switch_probe_port or 10200,
        switch_probe_interval_seconds=payload.switch_probe_interval_seconds or 30,
        config_updated_at=datetime.now(timezone.utc),
    )
    db.add(atm)
    db.flush()
    record_agent_config_snapshot(db, atm, current_user.username)
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="atm_created",
        entity_type="atm",
        entity_id=atm.atm_id,
        details={"name": atm.name, "branch": atm.branch, "vpn_ip": atm.vpn_ip},
    )
    db.commit()
    db.refresh(atm)
    return ATMCreateResponse(atm=atm, api_key=api_key)


@router.get("/{atm_id}", response_model=ATMRead)
def get_atm(
    atm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_page("dashboard", "atms", "cash")),
) -> ATM:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")
    return atm


@router.get("/{atm_id}/diagnostics", response_model=ATMDiagnostics)
def get_atm_diagnostics(
    atm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("atms")),
) -> ATMDiagnostics:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")

    recent_logs = (
        db.query(AgentLog)
        .filter(AgentLog.atm_id == atm.id)
        .order_by(AgentLog.created_at.desc())
        .limit(10)
        .all()
    )
    recent_commands = (
        db.query(AgentCommand)
        .filter(AgentCommand.atm_id == atm.id)
        .order_by(AgentCommand.created_at.desc())
        .limit(5)
        .all()
    )
    last_reboot_command = next((command for command in recent_commands if command.command_type == "reboot"), None)
    error_logs = [log for log in recent_logs if log.level in {"warning", "error"}]
    last_error_log = error_logs[0] if error_logs else None
    server_error_log = next(
        (
            log
            for log in error_logs
            if "server" in log.message.lower()
            or "communication" in log.message.lower()
            or "connection" in log.message.lower()
        ),
        last_error_log,
    )

    if atm.last_heartbeat_at is None:
        reporting_status = "never_reported"
        severity = "warning"
        summary = "No heartbeat received yet"
        recommended_action = "Install/start the Agent service, then verify API URL and API Key on the ATM."
    elif atm.is_online:
        reporting_status = "reporting"
        severity = "ok"
        summary = "Agent is reporting normally"
        recommended_action = "No action required."
    else:
        reporting_status = "not_reporting"
        severity = "critical"
        summary = "Service not reporting"
        recommended_action = (
            "On the ATM, run: sc.exe query ATMUnifiedAgent, then check "
            "C:\\Program Files\\QIB ATM Manager Agent\\logs\\agent.log."
        )
        if last_reboot_command and last_reboot_command.status == "completed":
            summary = "Service not reporting after reboot"

    return ATMDiagnostics(
        atm_id=atm.atm_id,
        is_online=atm.is_online,
        service_status=atm.status,
        reporting_status=reporting_status,
        severity=severity,
        summary=summary,
        recommended_action=recommended_action,
        last_heartbeat_at=atm.last_heartbeat_at,
        seconds_since_last_seen=atm.seconds_since_last_seen,
        last_agent_error=atm.last_agent_error,
        last_agent_error_at=atm.last_agent_error_at,
        last_server_error=server_error_log.message if server_error_log else None,
        last_server_error_at=server_error_log.created_at if server_error_log else None,
        last_reboot_command=last_reboot_command,
        recent_logs=recent_logs,
        recent_commands=recent_commands,
    )


def event_severity_from_status(status_value: str | None) -> str:
    status_text = (status_value or "").lower()
    if status_text in {"failed", "error", "cancelled", "critical"}:
        return "error"
    if status_text in {"pending", "acknowledged", "running", "warning", "open"}:
        return "warning"
    if status_text in {"success", "completed", "applied", "sent", "closed", "ok"}:
        return "success"
    return "info"


def event_severity_from_log(level: str | None) -> str:
    level_text = (level or "").lower()
    if level_text == "error":
        return "error"
    if level_text == "warning":
        return "warning"
    return "info"


def event_item(
    *,
    event_id: str,
    occurred_at: datetime | None,
    source: str,
    event_type: str,
    title: str,
    severity: str = "info",
    message: str | None = None,
    status_value: str | None = None,
    actor: str | None = None,
    details: dict | None = None,
) -> AtmEventRead | None:
    if occurred_at is None:
        return None
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return AtmEventRead(
        id=event_id,
        occurred_at=occurred_at,
        source=source,
        event_type=event_type,
        severity=severity,
        title=title,
        message=message,
        status=status_value,
        actor=actor,
        details=details or {},
    )


@router.get("/{atm_id}/events", response_model=list[AtmEventRead])
def list_atm_events(
    atm_id: str,
    limit: int = 80,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_page("atms", "logs")),
) -> list[AtmEventRead]:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")

    per_source_limit = max(10, min(limit, 200))
    events: list[AtmEventRead] = []

    def add(item: AtmEventRead | None) -> None:
        if item is not None:
            events.append(item)

    add(
        event_item(
            event_id=f"atm:last-heartbeat:{atm.id}",
            occurred_at=atm.last_heartbeat_at or atm.last_seen,
            source="agent",
            event_type="heartbeat",
            title="آخر اتصال من Agent",
            severity="success" if atm.is_online else "warning",
            message=f"Agent {atm.agent_version or '-'} · latency {atm.latency_ms if atm.latency_ms is not None else '-'} ms",
            status_value="online" if atm.is_online else "offline",
        )
    )
    add(
        event_item(
            event_id=f"atm:last-config-sync:{atm.id}",
            occurred_at=atm.last_config_sync_at,
            source="config",
            event_type="config_sync",
            title="آخر مزامنة إعدادات",
            severity="success" if atm.applied_config_version >= atm.config_version else "warning",
            message=f"Applied {atm.applied_config_version} / Current {atm.config_version}",
            status_value="synced" if atm.applied_config_version >= atm.config_version else "pending",
        )
    )

    for log in (
        db.query(AgentLog)
        .filter(AgentLog.atm_id == atm.id)
        .order_by(AgentLog.created_at.desc())
        .limit(per_source_limit)
        .all()
    ):
        add(
            event_item(
                event_id=f"agent-log:{log.id}",
                occurred_at=log.created_at,
                source="agent",
                event_type="agent_log",
                title=f"Agent log · {log.level}",
                severity=event_severity_from_log(log.level),
                message=log.message,
                status_value=log.level,
                details=log.context or {},
            )
        )

    for command in (
        db.query(AgentCommand)
        .filter(AgentCommand.atm_id == atm.id)
        .order_by(AgentCommand.created_at.desc())
        .limit(per_source_limit)
        .all()
    ):
        add(
            event_item(
                event_id=f"agent-command:{command.id}",
                occurred_at=command.completed_at or command.acknowledged_at or command.created_at,
                source="command",
                event_type=command.command_type,
                title=f"أمر Agent · {command.command_type}",
                severity=event_severity_from_status(command.status),
                message=command.last_error,
                status_value=command.status,
                actor=command.requested_by,
                details=command.payload or {},
            )
        )

    for alert in (
        db.query(AtmCashAlert)
        .filter(AtmCashAlert.atm_id == atm.id)
        .order_by(AtmCashAlert.opened_at.desc())
        .limit(per_source_limit)
        .all()
    ):
        add(
            event_item(
                event_id=f"cash-alert-opened:{alert.id}",
                occurred_at=alert.opened_at,
                source="cash",
                event_type=alert.alert_type,
                title=f"تنبيه نقد · {alert.alert_type}",
                severity="error" if alert.severity == "critical" else "warning",
                message=alert.message,
                status_value=alert.status,
                details={
                    "unit_no": alert.unit_no,
                    "current_count": alert.current_count,
                    "threshold_count": alert.threshold_count,
                },
            )
        )
        add(
            event_item(
                event_id=f"cash-alert-closed:{alert.id}",
                occurred_at=alert.closed_at,
                source="cash",
                event_type=f"{alert.alert_type}_CLOSED",
                title=f"إغلاق تنبيه نقد · {alert.alert_type}",
                severity="success",
                message=alert.message,
                status_value="closed",
                details={"unit_no": alert.unit_no},
            )
        )

    for snapshot in (
        db.query(AtmCashSnapshot)
        .filter(AtmCashSnapshot.atm_id == atm.id)
        .order_by(AtmCashSnapshot.received_at.desc())
        .limit(20)
        .all()
    ):
        units_count = len((snapshot.snapshot_json or {}).get("cash_units") or [])
        add(
            event_item(
                event_id=f"cash-snapshot:{snapshot.id}",
                occurred_at=snapshot.received_at,
                source="cash",
                event_type="cash_snapshot",
                title="وصول قراءة نقد",
                severity="success",
                message=f"{units_count} cassette readings · {snapshot.source}",
                status_value="received",
                details={"read_at": snapshot.read_at.isoformat(), "source": snapshot.source},
            )
        )

    for probe in (
        db.query(AtmSwitchProbe)
        .filter(AtmSwitchProbe.atm_id == atm.id)
        .order_by(AtmSwitchProbe.requested_at.desc())
        .limit(per_source_limit)
        .all()
    ):
        add(
            event_item(
                event_id=f"switch-probe:{probe.id}",
                occurred_at=probe.completed_at or probe.started_at or probe.requested_at,
                source="switch",
                event_type="switch_probe",
                title="فحص السويتش",
                severity=event_severity_from_status(probe.status),
                message=probe.error_message or f"{probe.host}:{probe.port}",
                status_value=probe.status,
                actor=probe.requested_by,
                details={"host": probe.host, "port": probe.port, "latency_ms": probe.latency_ms},
            )
        )

    for target in (
        db.query(UpdateTarget)
        .filter(UpdateTarget.atm_id == atm.id)
        .order_by(UpdateTarget.assigned_at.desc())
        .limit(per_source_limit)
        .all()
    ):
        version = target.package.version if target.package else str(target.package_id)
        add(
            event_item(
                event_id=f"update-target:{target.id}",
                occurred_at=target.completed_at or target.last_progress_at or target.assigned_at,
                source="media",
                event_type="update_target",
                title=f"تحديث وسائط · {version}",
                severity=event_severity_from_status(target.status),
                message=target.last_error or target.progress_message,
                status_value=target.status,
                details={
                    "package_id": target.package_id,
                    "version": version,
                    "progress_percent": target.progress_percent,
                    "progress_phase": target.progress_phase,
                    "attempt_count": target.attempt_count,
                },
            )
        )

    for result in (
        db.query(UpdateResult)
        .filter(UpdateResult.atm_id == atm.id)
        .order_by(UpdateResult.created_at.desc())
        .limit(per_source_limit)
        .all()
    ):
        version = result.package.version if result.package else str(result.package_id)
        add(
            event_item(
                event_id=f"update-result:{result.id}",
                occurred_at=result.finished_at or result.started_at or result.created_at,
                source="media",
                event_type="update_result",
                title=f"نتيجة تحديث · {version}",
                severity=event_severity_from_status(result.status),
                message=result.message,
                status_value=result.status,
                details={"package_id": result.package_id, "version": version},
            )
        )

    for delivery in (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.atm_id == atm.id)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(per_source_limit)
        .all()
    ):
        add(
            event_item(
                event_id=f"notification-delivery:{delivery.id}",
                occurred_at=delivery.sent_at or delivery.created_at,
                source="notification",
                event_type=delivery.event_type,
                title="إرسال تنبيه بريد",
                severity=event_severity_from_status(delivery.status),
                message=delivery.error_message or delivery.subject,
                status_value=delivery.status,
                details={"recipient_email": delivery.recipient_email, "subject": delivery.subject},
            )
        )

    for audit in (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "atm", AuditLog.entity_id == atm.atm_id)
        .order_by(AuditLog.created_at.desc())
        .limit(per_source_limit)
        .all()
    ):
        add(
            event_item(
                event_id=f"audit:{audit.id}",
                occurred_at=audit.created_at,
                source="audit",
                event_type=audit.action,
                title=f"إجراء إداري · {audit.action}",
                severity="info",
                actor=audit.actor_id,
                details=audit.details or {},
            )
        )

    events.sort(key=lambda item: item.occurred_at, reverse=True)
    return events[: max(1, min(limit, 200))]


@router.post("/{atm_id}/regenerate-api-key", response_model=ATMCreateResponse)
def regenerate_atm_api_key(
    atm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("atms-manage")),
) -> ATMCreateResponse:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")

    api_key = generate_api_key()
    atm.api_key_hash = hash_api_key(api_key)
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="atm_api_key_regenerated",
        entity_type="atm",
        entity_id=atm.atm_id,
        details={
            "name": atm.name,
            "branch": atm.branch,
            "note": "Existing installed agents must be reinstalled or updated with the new API key.",
        },
    )
    db.commit()
    db.refresh(atm)
    return ATMCreateResponse(atm=atm, api_key=api_key)


@router.put("/{atm_id}", response_model=ATMRead)
def update_atm(
    atm_id: str,
    payload: ATMUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("atms")),
) -> ATM:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")

    changes = payload.model_dump(exclude_unset=True)
    if "cash_layout" in changes:
        changes["cash_layout_json"] = normalized_cash_layout(changes.pop("cash_layout"))
    if "xfs_profile" in changes and "xfs_logical_service" not in changes:
        old_default = default_xfs_logical_service(atm.xfs_profile)
        if atm.xfs_logical_service == old_default:
            changes["xfs_logical_service"] = default_xfs_logical_service(changes["xfs_profile"])
    config_changes = {
        key: value for key, value in changes.items() if key in CONFIG_FIELDS and getattr(atm, key) != value
    }
    for key, value in changes.items():
        setattr(atm, key, value)

    if config_changes:
        atm.config_version += 1
        atm.config_updated_at = datetime.now(timezone.utc)
        atm.last_config_error = None
        record_agent_config_snapshot(db, atm, current_user.username)
        write_audit(
            db,
            actor_type="user",
            actor_id=current_user.username,
            action="atm_config_updated",
            entity_type="atm",
            entity_id=atm.atm_id,
            details={
                "config_version": atm.config_version,
                "changes": config_changes,
            },
        )

    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="atm_updated",
        entity_type="atm",
        entity_id=atm.atm_id,
        details=changes,
    )
    db.commit()
    db.refresh(atm)
    return atm


@router.post("/{atm_id}/switch-probe", response_model=SwitchProbeRead, status_code=status.HTTP_202_ACCEPTED)
def request_switch_probe(
    atm_id: str,
    payload: SwitchProbeRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_page("atms", "cash")),
) -> AtmSwitchProbe:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")

    host = payload.host if payload and payload.host else atm.switch_probe_host
    port = payload.port if payload and payload.port else atm.switch_probe_port
    host_or_port_changed = host != atm.switch_probe_host or port != atm.switch_probe_port
    if host_or_port_changed:
        if not user_has_page(current_user, "atms-manage"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM management permission required")
        previous = {"switch_probe_host": atm.switch_probe_host, "switch_probe_port": atm.switch_probe_port}
        atm.switch_probe_host = host
        atm.switch_probe_port = port
        atm.config_version += 1
        atm.config_updated_at = datetime.now(timezone.utc)
        record_agent_config_snapshot(db, atm, current_user.username)
        write_audit(
            db,
            actor_type="user",
            actor_id=current_user.username,
            action="atm_switch_probe_target_updated",
            entity_type="atm",
            entity_id=atm.atm_id,
            details={
                "previous": previous,
                "current": {"switch_probe_host": host, "switch_probe_port": port},
                "config_version": atm.config_version,
            },
        )

    existing = (
        db.query(AtmSwitchProbe)
        .filter(AtmSwitchProbe.atm_id == atm.id, AtmSwitchProbe.status.in_(["pending", "running"]))
        .order_by(AtmSwitchProbe.requested_at.desc())
        .first()
    )
    if existing:
        if existing.host == host and existing.port == port:
            return existing
        existing.status = "cancelled"
        existing.error_message = "Superseded by a new switch probe target"
        existing.completed_at = datetime.now(timezone.utc)
        db.flush()

    probe = AtmSwitchProbe(
        atm_id=atm.id,
        host=host,
        port=port,
        status="pending",
        requested_by=current_user.username,
    )
    db.add(probe)
    db.flush()
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="switch_probe_requested",
        entity_type="atm",
        entity_id=atm.atm_id,
        details={"probe_id": probe.id, "host": probe.host, "port": probe.port},
    )
    db.commit()
    db.refresh(probe)
    return probe


@router.get("/{atm_id}/switch-probes", response_model=list[SwitchProbeRead])
def list_switch_probes(
    atm_id: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_page("atms", "cash")),
) -> list[AtmSwitchProbe]:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")
    return (
        db.query(AtmSwitchProbe)
        .filter(AtmSwitchProbe.atm_id == atm.id)
        .order_by(AtmSwitchProbe.requested_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )


@router.post("/{atm_id}/reboot", response_model=AgentCommandRead)
def request_atm_reboot(
    atm_id: str,
    payload: ATMRebootRequest,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("atms-manage")),
) -> AgentCommand:
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Remote ATM commands are disabled for QIB ATM Manager Agent")
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")

    active_update_count = db.query(UpdateTarget).filter(
        UpdateTarget.atm_id == atm.id,
        UpdateTarget.status.in_(["pending", "downloading"]),
    ).count()
    if active_update_count and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "ATM has active updates",
                "active_update_count": active_update_count,
            },
        )

    existing = (
        db.query(AgentCommand)
        .filter(
            AgentCommand.atm_id == atm.id,
            AgentCommand.command_type == "reboot",
            AgentCommand.status.in_(["pending", "acknowledged"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ATM already has a pending reboot request")

    command = AgentCommand(
        atm_id=atm.id,
        command_type="reboot",
        status="pending",
        requested_by=current_user.username,
        payload={
            "reason": payload.reason or "Requested from QIB ATM Manager",
            "delay_seconds": payload.delay_seconds,
            "force": force,
        },
    )
    db.add(command)
    db.flush()
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="atm_reboot_requested",
        entity_type="atm",
        entity_id=atm.atm_id,
        details={
            "command_id": command.id,
            "delay_seconds": payload.delay_seconds,
            "reason": payload.reason,
            "force": force,
            "active_update_count": active_update_count,
        },
    )
    db.commit()
    db.refresh(command)
    return command


@router.delete("/{atm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_atm(
    atm_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("atms-manage")),
) -> Response:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")

    active_update_count = db.query(UpdateTarget).filter(
        UpdateTarget.atm_id == atm.id,
        UpdateTarget.status.in_(["pending", "downloading"]),
    ).count()
    if active_update_count and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "ATM has active updates",
                "active_update_count": active_update_count,
            },
        )

    details = {
        "name": atm.name,
        "branch": atm.branch,
        "vpn_ip": atm.vpn_ip,
        "force": force,
        "deleted_update_targets": db.query(UpdateTarget).filter(UpdateTarget.atm_id == atm.id).count(),
        "deleted_update_results": db.query(UpdateResult).filter(UpdateResult.atm_id == atm.id).count(),
        "deleted_agent_logs": db.query(AgentLog).filter(AgentLog.atm_id == atm.id).count(),
        "deleted_cash_units": db.query(AtmCashUnit).filter(AtmCashUnit.atm_id == atm.id).count(),
        "deleted_switch_probes": db.query(AtmSwitchProbe).filter(AtmSwitchProbe.atm_id == atm.id).count(),
        "deleted_reject_retract_status": db.query(AtmRejectRetractStatus).filter(
            AtmRejectRetractStatus.atm_id == atm.id
        ).count(),
    }
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="atm_deleted",
        entity_type="atm",
        entity_id=atm.atm_id,
        details=details,
    )

    db.query(UpdateTarget).filter(UpdateTarget.atm_id == atm.id).delete(synchronize_session=False)
    db.query(UpdateResult).filter(UpdateResult.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AgentLog).filter(AgentLog.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AgentCommand).filter(AgentCommand.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AtmAgentConfig).filter(AtmAgentConfig.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AtmCashUnit).filter(AtmCashUnit.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AtmRejectRetractStatus).filter(AtmRejectRetractStatus.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AtmSwitchProbe).filter(AtmSwitchProbe.atm_id == atm.id).delete(synchronize_session=False)
    db.query(NotificationDelivery).filter(NotificationDelivery.atm_id == atm.id).delete(synchronize_session=False)
    db.query(NotificationRecipient).filter(NotificationRecipient.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AtmCashSnapshot).filter(AtmCashSnapshot.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AtmCashAlert).filter(AtmCashAlert.atm_id == atm.id).delete(synchronize_session=False)
    db.query(AtmCashThreshold).filter(AtmCashThreshold.atm_id == atm.id).delete(synchronize_session=False)
    db.delete(atm)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
