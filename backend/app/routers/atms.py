from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import generate_api_key, get_current_user, hash_api_key
from ..database import get_db
from ..models import ATM, AgentCommand, AgentLog, UpdateResult, UpdateTarget, User
from ..schemas import AgentCommandRead, ATMDiagnostics, ATMCreate, ATMCreateResponse, ATMRead, ATMRebootRequest, ATMUpdate
from ..services.audit_service import write_audit

router = APIRouter(prefix="/api/atms", tags=["atms"])

CONFIG_FIELDS = {
    "media_path",
    "backup_path",
    "temp_path",
    "check_interval_seconds",
    "heartbeat_interval_seconds",
}


@router.get("", response_model=list[ATMRead])
def list_atms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ATM]:
    return db.query(ATM).order_by(ATM.branch, ATM.atm_id).all()


@router.post("", response_model=ATMCreateResponse, status_code=status.HTTP_201_CREATED)
def create_atm(
    payload: ATMCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ATMCreateResponse:
    if db.query(ATM).filter(ATM.atm_id == payload.atm_id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ATM ID already exists")

    api_key = generate_api_key()
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
        config_updated_at=datetime.now(timezone.utc),
    )
    db.add(atm)
    db.flush()
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
    current_user: User = Depends(get_current_user),
) -> ATM:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")
    return atm


@router.get("/{atm_id}/diagnostics", response_model=ATMDiagnostics)
def get_atm_diagnostics(
    atm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
            "On the ATM, run: sc.exe query ATMMediaAgent, then check "
            "C:\\Program Files\\ATM Media Agent\\logs\\agent.log."
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


@router.post("/{atm_id}/regenerate-api-key", response_model=ATMCreateResponse)
def regenerate_atm_api_key(
    atm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
) -> ATM:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")

    changes = payload.model_dump(exclude_unset=True)
    config_changes = {
        key: value for key, value in changes.items() if key in CONFIG_FIELDS and getattr(atm, key) != value
    }
    for key, value in changes.items():
        setattr(atm, key, value)

    if config_changes:
        atm.config_version += 1
        atm.config_updated_at = datetime.now(timezone.utc)
        atm.last_config_error = None
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


@router.post("/{atm_id}/reboot", response_model=AgentCommandRead)
def request_atm_reboot(
    atm_id: str,
    payload: ATMRebootRequest,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentCommand:
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
            "reason": payload.reason or "Requested from ATM Media Update Manager",
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
    current_user: User = Depends(get_current_user),
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
    db.delete(atm)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
