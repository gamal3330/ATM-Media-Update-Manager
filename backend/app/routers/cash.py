from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_agent_atm, get_current_user
from ..cash_layout import normalized_cash_layout
from ..database import get_db
from ..models import ATM, AgentCommand, AgentLog, AtmCashAlert, AtmCashSnapshot, AtmCashThreshold, AtmCashUnit, AtmRejectRetractStatus, User
from ..schemas import (
    AgentCommandRead,
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
    CashVerificationIssue,
    CashVerificationSummary,
)
from ..services.audit_service import write_audit
from ..services.notification_service import notify_cash_alert_opened

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
SUSPICIOUS_REGRESSION_WINDOW_MINUTES = 30
SUSPICIOUS_REGRESSION_TOTAL_DROP = 1000
READ_NOW_PENDING_TIMEOUT = timedelta(minutes=5)
READ_NOW_ACKNOWLEDGED_TIMEOUT = timedelta(minutes=2)
LAYOUT_VERIFICATION_ISSUES = {
    "CURRENCY_MISMATCH",
    "DENOMINATION_MISMATCH",
    "MISSING_READING",
    "UNCONFIGURED_CASSETTE",
}


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


def verification_issue(
    *,
    cassette_no: int | None,
    code: str,
    severity: str,
    message: str,
    expected: str | int | None = None,
    reported: str | int | None = None,
) -> CashVerificationIssue:
    return CashVerificationIssue(
        cassette_no=cassette_no,
        code=code,
        severity=severity,
        message=message,
        expected=None if expected is None else str(expected),
        reported=None if reported is None else str(reported),
    )


def cash_verification_summary(
    atm: ATM,
    units: list[AtmCashUnit],
    reject_retract: AtmRejectRetractStatus | None,
) -> CashVerificationSummary:
    read_at = max((unit.read_at for unit in units), default=None)
    issues: list[CashVerificationIssue] = []

    if not atm.cash_monitoring_enabled:
        return CashVerificationSummary(
            status="disabled",
            matched=False,
            checked_at=read_at,
            total_units=len(units),
            issues=[
                verification_issue(
                    cassette_no=None,
                    code="CASH_MONITORING_DISABLED",
                    severity="info",
                    message="Cash monitoring is disabled for this ATM",
                )
            ],
        )

    if atm.config_version != atm.applied_config_version:
        issues.append(
            verification_issue(
                cassette_no=None,
                code="CONFIG_PENDING",
                severity="warning",
                message="ATM configuration has not been applied by the agent yet",
                expected=atm.config_version,
                reported=atm.applied_config_version,
            )
        )

    layout_map = layout_by_cassette(atm)
    units_by_cassette = {unit.cassette_no: unit for unit in units}
    matched_units = 0

    if not units:
        issues.append(
            verification_issue(
                cassette_no=None,
                code="NO_READING",
                severity="warning",
                message="No cash snapshot has been received from the ATM yet",
            )
        )
        return CashVerificationSummary(
            status="no_reading",
            matched=False,
            checked_at=read_at,
            total_units=0,
            matched_units=0,
            mismatch_count=0,
            warning_count=len(issues),
            issues=issues,
        )

    for cassette_no, layout in sorted(layout_map.items()):
        unit = units_by_cassette.get(cassette_no)
        if unit is None:
            issues.append(
                verification_issue(
                    cassette_no=cassette_no,
                    code="MISSING_READING",
                    severity="critical",
                    message=f"Configured cassette {cassette_no} was not reported by the ATM",
                    expected=f"{layout['currency']} {layout['denomination']}",
                    reported="missing",
                )
            )
            continue

        unit_matched = True
        if unit.reported_currency != layout["currency"]:
            unit_matched = False
            issues.append(
                verification_issue(
                    cassette_no=cassette_no,
                    code="CURRENCY_MISMATCH",
                    severity="critical",
                    message=f"Cassette {cassette_no} currency does not match the configured layout",
                    expected=layout["currency"],
                    reported=unit.reported_currency,
                )
            )
        if unit.reported_denomination != int(layout["denomination"]):
            unit_matched = False
            issues.append(
                verification_issue(
                    cassette_no=cassette_no,
                    code="DENOMINATION_MISMATCH",
                    severity="critical",
                    message=f"Cassette {cassette_no} denomination does not match the configured layout",
                    expected=layout["denomination"],
                    reported=unit.reported_denomination,
                )
            )

        health_alert, health_severity = cassette_health_alert(unit.status, unit.physical_status)
        if health_alert and health_severity:
            issues.append(
                verification_issue(
                    cassette_no=cassette_no,
                    code=health_alert,
                    severity=health_severity,
                    message=f"Cassette {cassette_no} is not healthy: {unit.status}/{unit.physical_status}",
                    reported=f"{unit.status}/{unit.physical_status}",
                )
            )

        count_alert, count_severity, count_threshold = cash_count_alert(
            unit.current_count,
            int(layout["low_threshold"]),
            int(layout["critical_threshold"]),
        )
        if count_alert and count_severity:
            issues.append(
                verification_issue(
                    cassette_no=cassette_no,
                    code=count_alert,
                    severity=count_severity,
                    message=f"Cassette {cassette_no} count is below threshold",
                    expected=count_threshold,
                    reported=unit.current_count,
                )
            )

        if unit_matched:
            matched_units += 1

    for cassette_no, unit in sorted(units_by_cassette.items()):
        if cassette_no in layout_map:
            continue
        issues.append(
            verification_issue(
                cassette_no=cassette_no,
                code="UNCONFIGURED_CASSETTE",
                severity="warning",
                message=f"ATM reported cassette {cassette_no}, but it is not configured in the system layout",
                reported=f"{unit.reported_currency} {unit.reported_denomination}",
            )
        )

    if reject_retract:
        reject_high_threshold = max(1, int(reject_retract.reject_max_capacity * 0.8))
        if reject_retract.reject_count >= reject_retract.reject_max_capacity:
            issues.append(
                verification_issue(
                    cassette_no=None,
                    code="REJECT_BIN_FULL",
                    severity="critical",
                    message="Reject bin is full",
                    expected=reject_retract.reject_max_capacity,
                    reported=reject_retract.reject_count,
                )
            )
        elif reject_retract.reject_count >= reject_high_threshold:
            issues.append(
                verification_issue(
                    cassette_no=None,
                    code="REJECT_BIN_HIGH",
                    severity="warning",
                    message="Reject bin count is high",
                    expected=reject_high_threshold,
                    reported=reject_retract.reject_count,
                )
            )
        if reject_retract.retract_count > 0:
            issues.append(
                verification_issue(
                    cassette_no=None,
                    code="RETRACT_OCCURRED",
                    severity="warning",
                    message="Retract bin has notes pulled back from customer presentation",
                    expected=0,
                    reported=reject_retract.retract_count,
                )
            )
        if reject_retract.reject_status.upper() not in {"OK", "LOW"}:
            issues.append(
                verification_issue(
                    cassette_no=None,
                    code="REJECT_BIN_STATUS",
                    severity="warning",
                    message=f"Reject bin status is {reject_retract.reject_status}",
                    reported=reject_retract.reject_status,
                )
            )
        if reject_retract.retract_status.upper() not in {"OK", "LOW"}:
            issues.append(
                verification_issue(
                    cassette_no=None,
                    code="RETRACT_BIN_STATUS",
                    severity="warning",
                    message=f"Retract bin status is {reject_retract.retract_status}",
                    reported=reject_retract.retract_status,
                )
            )

    mismatch_count = sum(1 for issue in issues if issue.code in LAYOUT_VERIFICATION_ISSUES)
    warning_count = len(issues) - mismatch_count
    if mismatch_count:
        status_value = "mismatch"
    elif issues:
        status_value = "warning"
    else:
        status_value = "matched"

    return CashVerificationSummary(
        status=status_value,
        matched=status_value == "matched",
        checked_at=read_at,
        total_units=len(units),
        matched_units=matched_units,
        mismatch_count=mismatch_count,
        warning_count=warning_count,
        issues=issues,
    )


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
        notify_cash_alert_opened(db, atm, open_alert)
        return

    alert = AtmCashAlert(
        atm_id=atm.id,
        unit_no=unit_no,
        alert_type=alert_type,
        severity=severity,
        message=message,
        current_count=current_count,
        threshold_count=threshold_count,
    )
    db.add(alert)
    db.flush()
    write_audit(
        db,
        actor_type="agent",
        actor_id=atm.atm_id,
        action="cash_alert_opened",
        entity_type="atm_cash_alert",
        entity_id=atm.atm_id,
        details={"unit_no": unit_no, "alert_type": alert_type, "current_count": current_count},
    )
    notify_cash_alert_opened(db, atm, alert)


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


def normalize_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def is_stale_cash_read_command(command: AgentCommand, now: datetime) -> bool:
    if command.status == "pending":
        return now - normalize_aware(command.created_at) > READ_NOW_PENDING_TIMEOUT
    if command.status == "acknowledged":
        reference = command.acknowledged_at or command.created_at
        return now - normalize_aware(reference) > READ_NOW_ACKNOWLEDGED_TIMEOUT
    return False


def active_cash_read_command(db: Session, atm: ATM, now: datetime) -> AgentCommand | None:
    commands = (
        db.query(AgentCommand)
        .filter(
            AgentCommand.atm_id == atm.id,
            AgentCommand.command_type == "cash_read_now",
            AgentCommand.status.in_(["pending", "acknowledged"]),
        )
        .order_by(AgentCommand.created_at.asc())
        .all()
    )
    for command in commands:
        if not is_stale_cash_read_command(command, now):
            return command
        command.status = "failed"
        command.completed_at = now
        command.last_error = "Cash read request expired before the agent completed it"
    return None


def superseded_failed_cash_read_command(db: Session, atm: ATM, command: AgentCommand | None) -> bool:
    if command is None or command.status != "failed":
        return False
    latest_read = latest_cash_read_at(db, atm)
    if latest_read is None:
        return False
    command_finished_at = command.completed_at or command.acknowledged_at or command.created_at
    return normalize_aware(latest_read) > normalize_aware(command_finished_at)


def suspicious_cash_regression(
    db: Session,
    atm: ATM,
    payload: CashSnapshotRequest,
) -> tuple[bool, dict[str, Any]]:
    existing_units = {
        unit.cassette_no: unit
        for unit in db.query(AtmCashUnit).filter(AtmCashUnit.atm_id == atm.id).all()
    }
    if not existing_units:
        return False, {}

    payload_read_at = normalize_aware(payload.read_at)
    drops: list[dict[str, Any]] = []
    total_drop = 0
    latest_existing_read_at: datetime | None = None
    for unit_payload in payload.cash_units:
        existing = existing_units.get(unit_payload.cassette_no)
        if existing is None:
            continue
        existing_read_at = normalize_aware(existing.read_at)
        latest_existing_read_at = (
            existing_read_at
            if latest_existing_read_at is None or existing_read_at > latest_existing_read_at
            else latest_existing_read_at
        )
        if payload_read_at <= existing_read_at:
            return True, {
                "reason": "older_snapshot",
                "incoming_read_at": payload.read_at.isoformat(),
                "current_read_at": existing.read_at.isoformat(),
            }
        drop = int(existing.current_count) - int(unit_payload.current_count)
        if drop <= 0:
            continue
        total_drop += drop
        drops.append(
            {
                "cassette_no": unit_payload.cassette_no,
                "current_count": existing.current_count,
                "incoming_count": unit_payload.current_count,
                "drop": drop,
            }
        )

    if latest_existing_read_at is None:
        return False, {}
    elapsed_minutes = (payload_read_at - latest_existing_read_at).total_seconds() / 60
    if (
        0 <= elapsed_minutes <= SUSPICIOUS_REGRESSION_WINDOW_MINUTES
        and total_drop >= SUSPICIOUS_REGRESSION_TOTAL_DROP
    ):
        return True, {
            "reason": "suspicious_large_drop",
            "elapsed_minutes": round(elapsed_minutes, 2),
            "total_drop": total_drop,
            "drops": drops,
        }
    return False, {}


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

    is_suspicious, suspicious_details = suspicious_cash_regression(db, atm, payload)
    if is_suspicious:
        db.add(
            AgentLog(
                atm_id=atm.id,
                level="warning",
                message="Ignored suspicious cash snapshot regression",
                context={
                    "source": payload.source,
                    "read_at": payload.read_at.isoformat(),
                    **suspicious_details,
                },
            )
        )
        db.commit()
        return {"ok": True}

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
    units_by_atm_cassette = {(unit.atm_id, unit.cassette_no): unit for unit in units}
    low_cash_by_atm: dict[int, dict[str, Any]] = {}
    for alert in open_alerts:
        if alert.alert_type != "CASH_LOW":
            continue
        atm = atms_by_id.get(alert.atm_id)
        if atm is None:
            continue
        unit = units_by_atm_cassette.get((alert.atm_id, alert.unit_no))
        threshold = max(1, int(alert.threshold_count or 1))
        ratio = int(alert.current_count) / threshold
        existing = low_cash_by_atm.get(alert.atm_id)
        if existing and ratio >= existing["_ratio"]:
            continue
        low_cash_by_atm[alert.atm_id] = {
            "_ratio": ratio,
            "atm_id": atm.atm_id,
            "name": atm.name,
            "branch": atm.branch,
            "cassette_no": alert.unit_no,
            "currency": unit.expected_currency if unit else "",
            "denomination": unit.expected_denomination if unit else 0,
            "current_count": alert.current_count,
            "threshold_count": alert.threshold_count,
            "status": unit.status if unit else alert.alert_type,
            "read_at": unit.read_at if unit else alert.opened_at,
        }
    low_cash_atms = [
        {key: value for key, value in item.items() if key != "_ratio"}
        for item in sorted(
            low_cash_by_atm.values(),
            key=lambda detail: (detail["_ratio"], str(detail["atm_id"])),
        )
    ]

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
        low_cash_atms=low_cash_atms,
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
    reject_retract = (
        db.query(AtmRejectRetractStatus)
        .filter(AtmRejectRetractStatus.atm_id == atm.id)
        .first()
    )
    last_cash_read_command = (
        db.query(AgentCommand)
        .filter(AgentCommand.atm_id == atm.id, AgentCommand.command_type == "cash_read_now")
        .order_by(AgentCommand.created_at.desc())
        .first()
    )
    if superseded_failed_cash_read_command(db, atm, last_cash_read_command):
        last_cash_read_command = None
    return CashAtmDetails(
        atm=atm,
        units=units,
        reject_retract=reject_retract,
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
        verification=cash_verification_summary(atm, units, reject_retract),
        last_cash_read_command=last_cash_read_command,
    )


@router.post("/api/cash/atms/{atm_id}/read-now", response_model=AgentCommandRead, status_code=status.HTTP_202_ACCEPTED)
def request_cash_read_now(
    atm_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentCommand:
    atm = db.query(ATM).filter(ATM.atm_id == atm_id).first()
    if not atm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ATM not found")
    if not atm.cash_monitoring_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cash monitoring is disabled for this ATM")

    now = utcnow()
    existing = active_cash_read_command(db, atm, now)
    if existing:
        db.commit()
        db.refresh(existing)
        return existing

    command = AgentCommand(
        atm_id=atm.id,
        command_type="cash_read_now",
        payload={"source": "dashboard", "read_only": True},
        requested_by=current_user.username,
    )
    db.add(command)
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="cash_read_now_requested",
        entity_type="atm",
        entity_id=atm.atm_id,
        details={"command_type": command.command_type},
    )
    db.commit()
    db.refresh(command)
    return command


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
