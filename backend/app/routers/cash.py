from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_agent_atm, get_current_user
from ..cash_layout import normalized_cash_layout
from ..database import get_db
from ..models import ATM, AtmCashAlert, AtmCashSnapshot, AtmCashThreshold, AtmCashUnit, AtmRejectRetractStatus, User
from ..schemas import (
    CashAlertRead,
    CashAtmDetails,
    CashAtmReportRead,
    CashForecastRead,
    CashReportOverview,
    CashSnapshotRequest,
    CashSummary,
    CashThresholdCreate,
    CashThresholdRead,
    CashThresholdUpdate,
)
from ..services.audit_service import write_audit

router = APIRouter(tags=["cash"])

CASSETTE_ALERT_TYPES = {
    "CASH_LOW",
    "CASH_CRITICAL",
    "CASH_EMPTY",
    "CASSETTE_MISSING",
    "CASSETTE_INOP",
    "CURRENCY_MISMATCH",
    "DENOMINATION_MISMATCH",
}
REJECT_RETRACT_ALERT_TYPES = {"REJECT_BIN_HIGH", "REJECT_BIN_FULL", "RETRACT_OCCURRED"}
RISK_RANK = {"CRITICAL": 0, "LOW": 1, "STALE": 2, "OK": 3, "UNKNOWN": 4}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def layout_by_cassette(atm: ATM) -> dict[int, dict[str, Any]]:
    return {int(item["cassette_no"]): item for item in normalized_cash_layout(atm.cash_layout_json)}


def apply_current_layout_to_units(atm: ATM, units: list[AtmCashUnit]) -> list[AtmCashUnit]:
    layout_map = layout_by_cassette(atm)
    for unit in units:
        layout = layout_map.get(unit.cassette_no)
        if layout is None:
            continue
        unit.expected_currency = layout["currency"]
        unit.expected_denomination = int(layout["denomination"])
        unit.low_threshold = int(layout["low_threshold"])
        unit.critical_threshold = int(layout["critical_threshold"])
        unit.max_capacity = int(layout["max_capacity"])
        unit.layout_match_status = layout_match_status(unit, layout)[0]
    return units


def sync_alert(
    db: Session,
    atm: ATM,
    *,
    unit_no: int,
    alert_type: str,
    severity: str,
    message: str,
    current_count: int,
    threshold_count: int,
) -> None:
    open_alert = (
        db.query(AtmCashAlert)
        .filter(
            AtmCashAlert.atm_id == atm.id,
            AtmCashAlert.unit_no == unit_no,
            AtmCashAlert.alert_type == alert_type,
            AtmCashAlert.status == "open",
        )
        .first()
    )
    if open_alert:
        open_alert.severity = severity
        open_alert.message = message
        open_alert.current_count = current_count
        open_alert.threshold_count = threshold_count
        return

    db.add(
        AtmCashAlert(
            atm_id=atm.id,
            unit_no=unit_no,
            alert_type=alert_type,
            severity=severity,
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


def close_inactive_alerts(db: Session, atm: ATM, unit_no: int, active_types: set[str], candidates: set[str]) -> None:
    open_alerts = (
        db.query(AtmCashAlert)
        .filter(
            AtmCashAlert.atm_id == atm.id,
            AtmCashAlert.unit_no == unit_no,
            AtmCashAlert.status == "open",
            AtmCashAlert.alert_type.in_(candidates),
        )
        .all()
    )
    for alert in open_alerts:
        if alert.alert_type not in active_types:
            alert.status = "closed"
            alert.closed_at = utcnow()


def cash_count_alert(current_count: int, low_threshold: int, critical_threshold: int) -> tuple[str | None, str | None, int]:
    if current_count <= 0:
        return "CASH_EMPTY", "critical", 0
    if current_count <= critical_threshold:
        return "CASH_CRITICAL", "critical", critical_threshold
    if current_count <= low_threshold:
        return "CASH_LOW", "warning", low_threshold
    return None, None, 0


def cassette_health_alert(status: str, physical_status: str) -> tuple[str | None, str | None]:
    status_value = status.upper()
    physical_value = physical_status.upper()
    if physical_value not in {"PRESENT", "OK"}:
        return "CASSETTE_MISSING", "critical"
    if status_value in {"INOP", "INOPERATIVE", "ERROR", "FATAL"}:
        return "CASSETTE_INOP", "critical"
    return None, None


def layout_match_status(unit_payload, layout: dict[str, Any]) -> tuple[str, set[str]]:
    active_types: set[str] = set()
    if unit_payload.reported_currency != layout["currency"]:
        active_types.add("CURRENCY_MISMATCH")
    if unit_payload.reported_denomination != int(layout["denomination"]):
        active_types.add("DENOMINATION_MISMATCH")
    if "CURRENCY_MISMATCH" in active_types:
        return "CURRENCY_MISMATCH", active_types
    if "DENOMINATION_MISMATCH" in active_types:
        return "DENOMINATION_MISMATCH", active_types
    return "MATCH", active_types


def snapshot_unit_readings(db: Session, atm: ATM, cassette_no: int, limit: int = 16) -> list[tuple[datetime, int]]:
    snapshots = (
        db.query(AtmCashSnapshot)
        .filter(AtmCashSnapshot.atm_id == atm.id)
        .order_by(AtmCashSnapshot.read_at.desc())
        .limit(limit)
        .all()
    )
    readings: list[tuple[datetime, int]] = []
    for snapshot in snapshots:
        payload = snapshot.snapshot_json or {}
        for unit in payload.get("cash_units") or []:
            if int(unit.get("cassette_no") or 0) != cassette_no:
                continue
            readings.append((snapshot.read_at, int(unit.get("current_count") or 0)))
            break
    return sorted(readings, key=lambda item: item[0])


def cash_risk(current_count: int, low_threshold: int, critical_threshold: int, days_to_empty: float | None) -> str:
    if current_count <= critical_threshold or (days_to_empty is not None and days_to_empty <= 1):
        return "CRITICAL"
    if current_count <= low_threshold or (days_to_empty is not None and days_to_empty <= 3):
        return "LOW"
    return "OK"


def forecast_for_unit(db: Session, atm: ATM, unit: AtmCashUnit) -> CashForecastRead:
    readings = snapshot_unit_readings(db, atm, unit.cassette_no)
    total_drop = 0
    total_hours = 0.0
    for (previous_at, previous_count), (current_at, current_count) in zip(readings, readings[1:]):
        if previous_at.tzinfo is None:
            previous_at = previous_at.replace(tzinfo=timezone.utc)
        if current_at.tzinfo is None:
            current_at = current_at.replace(tzinfo=timezone.utc)
        hours = (current_at - previous_at).total_seconds() / 3600
        drop = previous_count - current_count
        if hours > 0 and drop > 0:
            total_drop += drop
            total_hours += hours

    notes_per_day: float | None = None
    days_to_low: float | None = None
    days_to_empty: float | None = None
    if total_drop > 0 and total_hours > 0:
        notes_per_day = round((total_drop / total_hours) * 24, 2)
        if notes_per_day > 0:
            days_to_empty = round(unit.current_count / notes_per_day, 2)
            days_to_low = round(max(0, unit.current_count - unit.low_threshold) / notes_per_day, 2)

    risk = cash_risk(unit.current_count, unit.low_threshold, unit.critical_threshold, days_to_empty)
    return CashForecastRead(
        atm_id=atm.atm_id,
        atm_name=atm.name,
        branch=atm.branch,
        cassette_no=unit.cassette_no,
        currency=unit.expected_currency or unit.reported_currency,
        denomination=unit.expected_denomination or unit.reported_denomination,
        current_count=unit.current_count,
        low_threshold=unit.low_threshold,
        critical_threshold=unit.critical_threshold,
        notes_per_day=notes_per_day,
        days_to_low=days_to_low,
        days_to_empty=days_to_empty,
        risk=risk,
        last_read_at=unit.read_at,
        sample_count=len(readings),
    )


def forecasts_for_atm(db: Session, atm: ATM, units: list[AtmCashUnit]) -> list[CashForecastRead]:
    return [forecast_for_unit(db, atm, unit) for unit in units]


def latest_cash_read_at(db: Session, atm: ATM) -> datetime | None:
    latest = (
        db.query(AtmCashSnapshot)
        .filter(AtmCashSnapshot.atm_id == atm.id)
        .order_by(AtmCashSnapshot.read_at.desc())
        .first()
    )
    return latest.read_at if latest else None


def is_cash_stale(atm: ATM, read_at: datetime | None, now: datetime) -> bool:
    if read_at is None:
        return True
    if read_at.tzinfo is None:
        read_at = read_at.replace(tzinfo=timezone.utc)
    return now - read_at > timedelta(minutes=atm.cash_stale_after_minutes)


@router.post("/api/agent/cash-snapshot")
def submit_cash_snapshot(
    payload: CashSnapshotRequest,
    atm: ATM = Depends(get_agent_atm),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if payload.atm_id and payload.atm_id != atm.atm_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ATM ID does not match credentials")
    if payload.atm_cash_mode != "DISPENSE_ONLY":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only DISPENSE_ONLY cash mode is supported")

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

    layout_map = layout_by_cassette(atm)
    for unit_payload in payload.cash_units:
        layout = layout_map.get(unit_payload.cassette_no)
        if layout is None:
            layout = {
                "cassette_no": unit_payload.cassette_no,
                "currency": unit_payload.reported_currency,
                "denomination": unit_payload.reported_denomination,
                "max_capacity": 2000,
                "low_threshold": atm.cash_low_threshold_default,
                "critical_threshold": atm.cash_critical_threshold_default,
            }

        low_threshold = int(layout["low_threshold"])
        critical_threshold = int(layout["critical_threshold"])
        max_capacity = int(layout["max_capacity"])
        layout_status, mismatch_types = layout_match_status(unit_payload, layout)

        unit = db.query(AtmCashUnit).filter(
            AtmCashUnit.atm_id == atm.id,
            AtmCashUnit.unit_no == unit_payload.cassette_no,
        ).first()
        values = {
            "unit_no": unit_payload.cassette_no,
            "cassette_no": unit_payload.cassette_no,
            "cassette_id": unit_payload.cassette_id,
            "cassette_name": unit_payload.cassette_name or f"Dispense Cassette {unit_payload.cassette_no}",
            "expected_currency": layout["currency"],
            "expected_denomination": int(layout["denomination"]),
            "reported_currency": unit_payload.reported_currency,
            "reported_denomination": unit_payload.reported_denomination,
            "currency": unit_payload.reported_currency,
            "denomination": unit_payload.reported_denomination,
            "initial_count": unit_payload.initial_count,
            "current_count": unit_payload.current_count,
            "reject_count": unit_payload.reject_count,
            "retract_count": unit_payload.retract_count,
            "retracted_count": unit_payload.retract_count,
            "dispensed_count": unit_payload.dispensed_count,
            "presented_count": unit_payload.presented_count,
            "min_threshold": low_threshold,
            "low_threshold": low_threshold,
            "critical_threshold": critical_threshold,
            "max_capacity": max_capacity,
            "status": unit_payload.status,
            "physical_status": unit_payload.physical_status,
            "layout_match_status": layout_status,
            "source": payload.source,
            "read_at": payload.read_at,
        }

        if unit is None:
            unit = AtmCashUnit(atm_id=atm.id, **values)
            db.add(unit)
        else:
            for key, value in values.items():
                setattr(unit, key, value)

        active_types = set(mismatch_types)
        count_alert, count_severity, count_threshold = cash_count_alert(
            unit_payload.current_count,
            low_threshold,
            critical_threshold,
        )
        if count_alert and count_severity:
            active_types.add(count_alert)
            sync_alert(
                db,
                atm,
                unit_no=unit_payload.cassette_no,
                alert_type=count_alert,
                severity=count_severity,
                message=f"{count_alert} on dispense cassette {unit_payload.cassette_no}: {unit_payload.current_count} notes",
                current_count=unit_payload.current_count,
                threshold_count=count_threshold,
            )

        health_alert, health_severity = cassette_health_alert(unit_payload.status, unit_payload.physical_status)
        if health_alert and health_severity:
            active_types.add(health_alert)
            sync_alert(
                db,
                atm,
                unit_no=unit_payload.cassette_no,
                alert_type=health_alert,
                severity=health_severity,
                message=f"{health_alert} on dispense cassette {unit_payload.cassette_no}",
                current_count=unit_payload.current_count,
                threshold_count=0,
            )

        for mismatch_type in mismatch_types:
            expected = layout["currency"] if mismatch_type == "CURRENCY_MISMATCH" else layout["denomination"]
            reported = unit_payload.reported_currency if mismatch_type == "CURRENCY_MISMATCH" else unit_payload.reported_denomination
            sync_alert(
                db,
                atm,
                unit_no=unit_payload.cassette_no,
                alert_type=mismatch_type,
                severity="critical",
                message=f"{mismatch_type} on cassette {unit_payload.cassette_no}: expected {expected}, reported {reported}",
                current_count=unit_payload.current_count,
                threshold_count=0,
            )

        close_inactive_alerts(db, atm, unit_payload.cassette_no, active_types, CASSETTE_ALERT_TYPES)

    reject_retract = (
        db.query(AtmRejectRetractStatus)
        .filter(AtmRejectRetractStatus.atm_id == atm.id)
        .first()
    )
    rr_values = payload.reject_retract.model_dump()
    rr_values["read_at"] = payload.read_at
    if reject_retract is None:
        reject_retract = AtmRejectRetractStatus(atm_id=atm.id, **rr_values)
        db.add(reject_retract)
    else:
        for key, value in rr_values.items():
            setattr(reject_retract, key, value)

    active_rr_alerts: set[str] = set()
    reject_high_threshold = max(1, int(payload.reject_retract.reject_max_capacity * 0.8))
    if payload.reject_retract.reject_count >= payload.reject_retract.reject_max_capacity:
        active_rr_alerts.add("REJECT_BIN_FULL")
        sync_alert(
            db,
            atm,
            unit_no=0,
            alert_type="REJECT_BIN_FULL",
            severity="critical",
            message="Reject bin is full",
            current_count=payload.reject_retract.reject_count,
            threshold_count=payload.reject_retract.reject_max_capacity,
        )
    elif payload.reject_retract.reject_count >= reject_high_threshold:
        active_rr_alerts.add("REJECT_BIN_HIGH")
        sync_alert(
            db,
            atm,
            unit_no=0,
            alert_type="REJECT_BIN_HIGH",
            severity="warning",
            message="Reject bin count is high",
            current_count=payload.reject_retract.reject_count,
            threshold_count=reject_high_threshold,
        )
    if payload.reject_retract.retract_count > 0:
        active_rr_alerts.add("RETRACT_OCCURRED")
        sync_alert(
            db,
            atm,
            unit_no=0,
            alert_type="RETRACT_OCCURRED",
            severity="warning",
            message="Retract bin has notes pulled back from customer presentation",
            current_count=payload.reject_retract.retract_count,
            threshold_count=1,
        )
    close_inactive_alerts(db, atm, 0, active_rr_alerts, REJECT_RETRACT_ALERT_TYPES)

    db.commit()
    return {"ok": True}


@router.get("/api/cash/summary", response_model=CashSummary)
def cash_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CashSummary:
    units = db.query(AtmCashUnit).order_by(AtmCashUnit.updated_at.desc()).all()
    atms_by_id = {atm.id: atm for atm in db.query(ATM).all()}
    for unit in units:
        atm = atms_by_id.get(unit.atm_id)
        if atm is not None:
            apply_current_layout_to_units(atm, [unit])

    open_alerts = db.query(AtmCashAlert).filter(AtmCashAlert.status == "open").all()
    low_atms = {alert.atm_id for alert in open_alerts if alert.alert_type == "CASH_LOW"}
    critical_atms = {alert.atm_id for alert in open_alerts if alert.alert_type == "CASH_CRITICAL"}
    empty_atms = {alert.atm_id for alert in open_alerts if alert.alert_type == "CASH_EMPTY"}

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
        cash_critical_atms=len(critical_atms),
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
    units = db.query(AtmCashUnit).filter(AtmCashUnit.atm_id == atm.id).order_by(AtmCashUnit.cassette_no.asc()).all()
    apply_current_layout_to_units(atm, units)
    return CashAtmDetails(
        atm=atm,
        units=units,
        reject_retract=(
            db.query(AtmRejectRetractStatus)
            .filter(AtmRejectRetractStatus.atm_id == atm.id)
            .first()
        ),
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
        forecasts=forecasts_for_atm(db, atm, units),
    )


@router.get("/api/cash/reports/overview", response_model=CashReportOverview)
def cash_report_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CashReportOverview:
    now = utcnow()
    report_rows: list[CashAtmReportRead] = []
    forecast_risks: list[CashForecastRead] = []
    atms = db.query(ATM).filter(ATM.cash_monitoring_enabled.is_(True)).order_by(ATM.branch, ATM.atm_id).all()

    for atm in atms:
        units = db.query(AtmCashUnit).filter(AtmCashUnit.atm_id == atm.id).order_by(AtmCashUnit.cassette_no.asc()).all()
        apply_current_layout_to_units(atm, units)
        forecasts = forecasts_for_atm(db, atm, units)
        forecast_risks.extend([item for item in forecasts if item.risk in {"LOW", "CRITICAL"}])

        totals_by_currency: dict[str, int] = {}
        total_note_count = 0
        for unit in units:
            currency = unit.expected_currency or unit.reported_currency or "N/A"
            denomination = int(unit.expected_denomination or unit.reported_denomination or 0)
            totals_by_currency[currency] = totals_by_currency.get(currency, 0) + unit.current_count * denomination
            total_note_count += unit.current_count

        lowest = min(units, key=lambda item: item.current_count, default=None)
        open_alert_count = (
            db.query(AtmCashAlert)
            .filter(AtmCashAlert.atm_id == atm.id, AtmCashAlert.status == "open")
            .count()
        )
        last_read = latest_cash_read_at(db, atm)
        highest_risk = min((item.risk for item in forecasts), key=lambda risk: RISK_RANK.get(risk, 99), default="UNKNOWN")
        days_values = [item.days_to_empty for item in forecasts if item.days_to_empty is not None]
        report_rows.append(
            CashAtmReportRead(
                atm_id=atm.atm_id,
                name=atm.name,
                branch=atm.branch,
                is_stale=is_cash_stale(atm, last_read, now),
                last_read_at=last_read,
                totals_by_currency=totals_by_currency,
                total_note_count=total_note_count,
                lowest_cassette_no=lowest.cassette_no if lowest else None,
                lowest_current_count=lowest.current_count if lowest else None,
                open_alert_count=open_alert_count,
                highest_risk=highest_risk,
                forecast_days_to_empty=min(days_values) if days_values else None,
            )
        )

    forecast_risks.sort(key=lambda item: (RISK_RANK.get(item.risk, 99), item.days_to_empty if item.days_to_empty is not None else 9999))
    return CashReportOverview(generated_at=now, atms=report_rows, forecast_risks=forecast_risks[:20])


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
