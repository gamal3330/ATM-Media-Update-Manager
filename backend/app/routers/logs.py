from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, case, cast, func, or_
from sqlalchemy.orm import Session, joinedload

from ..auth import require_any_page, require_page
from ..database import get_db
from ..models import ATM, AgentLog, AtmJournalEvent, AuditLog, User
from ..schemas import AgentLogRead, AuditLogRead, JournalEventRead, JournalWithdrawalSummaryRead

router = APIRouter(prefix="/api/logs", tags=["logs"])


def get_atm_primary_key(db: Session, atm_id: str | None) -> int | None:
    if not atm_id:
        return None
    return db.query(ATM.id).filter(ATM.atm_id == atm_id).scalar()


def resolve_page_window(limit: int, page: int, page_size: int | None, maximum: int) -> tuple[int, int]:
    size = page_size if page_size is not None else limit
    size = max(1, min(size, maximum))
    offset = (max(1, page) - 1) * size
    return offset, size


def apply_journal_filters(
    query,
    *,
    atm_pk: int | None = None,
    branch: str | None = None,
    search: str | None = None,
    event_type: str | None = None,
    transaction_type: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
):
    if branch or search:
        query = query.join(ATM)
    if atm_pk is not None:
        query = query.filter(AtmJournalEvent.atm_id == atm_pk)
    if branch:
        query = query.filter(ATM.branch == branch)
    if event_type:
        query = query.filter(AtmJournalEvent.event_type == event_type)
    if transaction_type:
        query = query.filter(AtmJournalEvent.transaction_type == transaction_type)
    if from_at:
        query = query.filter(AtmJournalEvent.occurred_at >= from_at)
    if to_at:
        query = query.filter(AtmJournalEvent.occurred_at <= to_at)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ATM.atm_id.ilike(pattern),
                ATM.name.ilike(pattern),
                ATM.branch.ilike(pattern),
                ATM.vpn_ip.ilike(pattern),
                AtmJournalEvent.transaction_serial.ilike(pattern),
                AtmJournalEvent.rrn.ilike(pattern),
                AtmJournalEvent.stan.ilike(pattern),
                AtmJournalEvent.auth_code.ilike(pattern),
                AtmJournalEvent.card_masked.ilike(pattern),
                AtmJournalEvent.currency.ilike(pattern),
                cast(AtmJournalEvent.amount, String).ilike(pattern),
            )
        )
    return query


@router.get("", response_model=list[AgentLogRead])
def list_agent_logs(
    level: str | None = None,
    atm_id: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    include_journal: bool = False,
    limit: int = 100,
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("logs")),
) -> list[AgentLog]:
    query = db.query(AgentLog).options(joinedload(AgentLog.atm)).order_by(AgentLog.created_at.desc())
    if not include_journal:
        query = query.filter(~AgentLog.message.like("Journal %"))
    if level:
        query = query.filter(AgentLog.level == level)
    if atm_id:
        atm_pk = get_atm_primary_key(db, atm_id)
        if atm_pk is None:
            return []
        query = query.filter(AgentLog.atm_id == atm_pk)
    if from_at:
        query = query.filter(AgentLog.created_at >= from_at)
    if to_at:
        query = query.filter(AgentLog.created_at <= to_at)
    offset, size = resolve_page_window(limit, page, page_size, 500)
    return query.offset(offset).limit(size).all()


@router.get("/audit", response_model=list[AuditLogRead])
def list_audit_logs(
    atm_id: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = 100,
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("logs")),
) -> list[AuditLog]:
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if atm_id:
        query = query.filter(AuditLog.entity_type == "atm", AuditLog.entity_id == atm_id)
    if from_at:
        query = query.filter(AuditLog.created_at >= from_at)
    if to_at:
        query = query.filter(AuditLog.created_at <= to_at)
    offset, size = resolve_page_window(limit, page, page_size, 500)
    return query.offset(offset).limit(size).all()


@router.get("/journal", response_model=list[JournalEventRead])
def list_journal_events(
    atm_id: str | None = None,
    branch: str | None = None,
    search: str | None = None,
    event_type: str | None = None,
    transaction_type: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = 100,
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_page("journal", "reports")),
) -> list[AtmJournalEvent]:
    query = db.query(AtmJournalEvent).options(joinedload(AtmJournalEvent.atm))
    atm_pk = None
    if atm_id:
        atm_pk = get_atm_primary_key(db, atm_id)
        if atm_pk is None:
            return []
    query = apply_journal_filters(
        query,
        atm_pk=atm_pk,
        branch=branch,
        search=search,
        event_type=event_type,
        transaction_type=transaction_type,
        from_at=from_at,
        to_at=to_at,
    )
    if atm_id or from_at or to_at:
        query = query.order_by(AtmJournalEvent.occurred_at.desc())
    else:
        query = query.order_by(AtmJournalEvent.received_at.desc(), AtmJournalEvent.occurred_at.desc())
    offset, size = resolve_page_window(limit, page, page_size, 300)
    return query.offset(offset).limit(size).all()


@router.get("/journal/withdrawals/summary", response_model=JournalWithdrawalSummaryRead)
def summarize_withdrawal_journal_events(
    atm_id: str | None = None,
    branch: str | None = None,
    search: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_page("journal", "reports")),
) -> JournalWithdrawalSummaryRead:
    atm_pk = None
    if atm_id:
        atm_pk = get_atm_primary_key(db, atm_id)
        if atm_pk is None:
            return JournalWithdrawalSummaryRead()

    completed_expr = AtmJournalEvent.details_json["completed"].as_boolean() == True  # noqa: E712
    base_query = apply_journal_filters(
        db.query(AtmJournalEvent),
        atm_pk=atm_pk,
        branch=branch,
        search=search,
        event_type="TRANSACTION_END",
        transaction_type="WID",
        from_at=from_at,
        to_at=to_at,
    )

    total, completed = base_query.with_entities(
        func.count(AtmJournalEvent.id),
        func.coalesce(func.sum(case((completed_expr, 1), else_=0)), 0),
    ).one()
    total = int(total or 0)
    completed = int(completed or 0)

    currency_expr = func.coalesce(AtmJournalEvent.currency, "YER")
    currency_amounts = (
        base_query.filter(completed_expr, AtmJournalEvent.amount.isnot(None))
        .with_entities(
            currency_expr.label("currency"),
            func.coalesce(func.sum(AtmJournalEvent.amount), 0).label("amount"),
        )
        .group_by(currency_expr)
        .all()
    )

    return JournalWithdrawalSummaryRead(
        total=total,
        completed=completed,
        incomplete=max(total - completed, 0),
        amount_by_currency={currency: int(amount or 0) for currency, amount in currency_amounts if currency},
    )

