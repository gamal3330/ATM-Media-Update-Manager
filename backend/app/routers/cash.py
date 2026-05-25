from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_agent_atm, get_current_user
from ..database import get_db
from ..models import ATM, AtmCashAlert, AtmCashSnapshot, AtmCashThreshold, AtmCashUnit, User
from ..schemas import (
    CashAlertRead,
    CashAtmDetails,
    CashSnapshotRequest,
    CashSummary,
    CashThresholdCreate,
    CashThresholdRead,
    CashThresholdUpdate,
)
from ..services.audit_service import write_audit

router = APIRouter(tags=["cash"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def threshold_for_unit(db: Session, atm: ATM, denomination: int) -> tuple[int, int, int]:
    threshold = (
        db.query(AtmCashThreshold)
        .filter(AtmCashThreshold.atm_id == atm.id, AtmCashThreshold.denomination == denomination)
        .first()
    )
    if threshold:
        return threshold.low_threshold_count, threshold.critical_threshold_count, threshold.max_capacity
    return atm.cash_low_threshold_default, atm.cash_critical_threshold_default, 2000


def classify_cash_alert(current_count: int, low_threshold: int, critical_threshold: int) -> tuple[str | None, str | None]:
    if current_count <= 0:
        return "EMPTY", "critical"
    if current_count <= critical_threshold:
        return "CRITICAL", "critical"
    if current_count <= low_threshold:
        return "LOW", "warning"
    return None, None


def sync_alert_for_unit(
    db: Session,
    atm: ATM,
    unit_no: int,
    current_count: int,
    low_threshold: int,
    critical_threshold: int,
) -> None:
    alert_type, severity = classify_cash_alert(current_count, low_threshold, critical_threshold)
    open_alert = (
        db.query(AtmCashAlert)
        .filter(AtmCashAlert.atm_id == atm.id, AtmCashAlert.unit_no == unit_no, AtmCashAlert.status == "open")
        .first()
    )

    if alert_type is None:
        if open_alert:
            open_alert.status = "closed"
            open_alert.closed_at = utcnow()
        return

    threshold_count = critical_threshold if alert_type in {"EMPTY", "CRITICAL"} else low_threshold
    message = f"Cash {alert_type.lower()} on unit {unit_no}: {current_count} notes remaining"
    if open_alert:
        open_alert.alert_type = alert_type
        open_alert.severity = severity or "warning"
        open_alert.message = message
        open_alert.current_count = current_count
        open_alert.threshold_count = threshold_count
        return

    db.add(
        AtmCashAlert(
            atm_id=atm.id,
            unit_no=unit_no,
            alert_type=alert_type,
            severity=severity or "warning",
            message=message,
            current_count=current_count,
            threshold_count=threshold_count,
        )
    )
    write_audit(
        db,
        actor_type="agent",
        actor_id=atm.atm_id,
        action="cash_alert_opened",
        entity_type="atm_cash_alert",
        entity_id=atm.atm_id,
        details={"unit_no": unit_no, "alert_type": alert_type, "current_count": current_count},
    )


@router.post("/api/agent/cash-snapshot")
def submit_cash_snapshot(
    payload: CashSnapshotRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if payload.atm_id and payload.atm_id != atm.atm_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM ID does not match credentials")

    snapshot = AtmCashSnapshot(
        atm_id=atm.id,
        snapshot_json=payload.model_dump(mode="json"),
        source=payload.source,
        read_at=payload.read_at,
    )
    db.add(snapshot)

    statuses = dict(atm.module_status_json or {})
    statuses["cash_monitoring"] = "running"
    atm.module_status_json = statuses

    for unit_payload in payload.cash_units:
        low_threshold, critical_threshold, max_capacity = threshold_for_unit(db, atm, unit_payload.denomination)
        unit = db.query(AtmCashUnit).filter(
            AtmCashUnit.atm_id == atm.id,
            AtmCashUnit.unit_no == unit_payload.unit_no,
        ).first()
        values = unit_payload.model_dump()
        values["min_threshold"] = low_threshold
        values["max_capacity"] = unit_payload.max_capacity or max_capacity
        values["source"] = payload.source
        values["read_at"] = payload.read_at

        if unit is None:
            unit = AtmCashUnit(atm_id=atm.id, **values)
            db.add(unit)
        else:
            for key, value in values.items():
                setattr(unit, key, value)

        sync_alert_for_unit(
            db,
            atm,
            unit_payload.unit_no,
            unit_payload.current_count,
            low_threshold,
            critical_threshold,
        )

    db.commit()
    return {"ok": True}


@router.get("/api/cash/summary", response_model=CashSummary)
def cash_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CashSummary:
    units = db.query(AtmCashUnit).order_by(AtmCashUnit.updated_at.desc()).all()
    open_alerts = db.query(AtmCashAlert).filter(AtmCashAlert.status == "open").all()
    low_atms = {alert.atm_id for alert in open_alerts if alert.alert_type == "LOW"}
    empty_atms = {alert.atm_id for alert in open_alerts if alert.alert_type == "EMPTY"}

    now = utcnow()
    stale_atms: set[int] = set()
    for atm in db.query(ATM).filter(ATM.cash_monitoring_enabled.is_(True)).all():
        latest = (
            db.query(AtmCashSnapshot)
            .filter(AtmCashSnapshot.atm_id == atm.id)
            .order_by(AtmCashSnapshot.read_at.desc())
            .first()
        )
        if not latest:
            stale_atms.add(atm.id)
            continue
        read_at = latest.read_at
        if read_at.tzinfo is None:
            read_at = read_at.replace(tzinfo=timezone.utc)
        if now - read_at > timedelta(minutes=atm.cash_stale_after_minutes):
            stale_atms.add(atm.id)

    return CashSummary(
        atm_count=db.query(ATM).count(),
        cash_low_atms=len(low_atms),
        cash_empty_atms=len(empty_atms),
        cash_stale_atms=len(stale_atms),
        open_alerts=len(open_alerts),
        units=units,
    )


@router.get("/api/cash/atms/{atm_id}", response_model=CashAtmDetails)
def cash_atm_details(
    atm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CashAtmDetails:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")
    return CashAtmDetails(
        atm=atm,
        units=db.query(AtmCashUnit).filter(AtmCashUnit.atm_id == atm.id).order_by(AtmCashUnit.unit_no.asc()).all(),
        alerts=(
            db.query(AtmCashAlert)
            .filter(AtmCashAlert.atm_id == atm.id)
            .order_by(AtmCashAlert.opened_at.desc())
            .limit(50)
            .all()
        ),
        thresholds=(
            db.query(AtmCashThreshold)
            .filter(AtmCashThreshold.atm_id == atm.id)
            .order_by(AtmCashThreshold.denomination.asc())
            .all()
        ),
    )


@router.get("/api/cash/alerts", response_model=list[CashAlertRead])
def list_cash_alerts(
    status_filter: str = "open",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AtmCashAlert]:
    query = db.query(AtmCashAlert)
    if status_filter != "all":
        query = query.filter(AtmCashAlert.status == status_filter)
    return query.order_by(AtmCashAlert.opened_at.desc()).limit(200).all()


@router.post("/api/cash/thresholds", response_model=CashThresholdRead, status_code=status.HTTP_201_CREATED)
def create_or_update_threshold(
    payload: CashThresholdCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AtmCashThreshold:
    atm = db.query(ATM).filter(ATM.atm_id == payload.atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")
    threshold = (
        db.query(AtmCashThreshold)
        .filter(AtmCashThreshold.atm_id == atm.id, AtmCashThreshold.denomination == payload.denomination)
        .first()
    )
    if threshold is None:
        threshold = AtmCashThreshold(atm_id=atm.id, denomination=payload.denomination)
        db.add(threshold)
    threshold.low_threshold_count = payload.low_threshold_count
    threshold.critical_threshold_count = payload.critical_threshold_count
    threshold.max_capacity = payload.max_capacity
    threshold.updated_by = current_user.username
    atm.config_version += 1
    atm.config_updated_at = utcnow()
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="cash_threshold_updated",
        entity_type="atm",
        entity_id=atm.atm_id,
        details=payload.model_dump(),
    )
    db.commit()
    db.refresh(threshold)
    return threshold


@router.put("/api/cash/thresholds/{threshold_id}", response_model=CashThresholdRead)
def update_threshold(
    threshold_id: int,
    payload: CashThresholdUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AtmCashThreshold:
    threshold = db.query(AtmCashThreshold).filter(AtmCashThreshold.id == threshold_id).first()
    if not threshold:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cash threshold not found")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(threshold, key, value)
    threshold.updated_by = current_user.username
    threshold.atm.config_version += 1
    threshold.atm.config_updated_at = utcnow()
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="cash_threshold_updated",
        entity_type="atm_cash_threshold",
        entity_id=str(threshold.id),
        details=changes,
    )
    db.commit()
    db.refresh(threshold)
    return threshold
