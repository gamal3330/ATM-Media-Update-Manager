from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from ..auth import require_page
from ..database import get_db
from ..models import ATM, AgentLog, AtmJournalEvent, AuditLog, User
from ..schemas import AgentLogRead, AuditLogRead, JournalEventRead

router = APIRouter(prefix="/api/logs", tags=["logs"])


def get_atm_primary_key(db: Session, atm_id: str | None) -> int | None:
    if not atm_id:
        return None
    return db.query(ATM.id).filter(ATM.atm_id == atm_id).scalar()


@router.get("", response_model=list[AgentLogRead])
def list_agent_logs(
    level: str | None = None,
    atm_id: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    include_journal: bool = False,
    limit: int = 100,
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
    return query.limit(min(limit, 500)).all()


@router.get("/audit", response_model=list[AuditLogRead])
def list_audit_logs(
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("logs")),
) -> list[AuditLog]:
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if from_at:
        query = query.filter(AuditLog.created_at >= from_at)
    if to_at:
        query = query.filter(AuditLog.created_at <= to_at)
    return query.limit(min(limit, 500)).all()


@router.get("/journal", response_model=list[JournalEventRead])
def list_journal_events(
    atm_id: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("logs")),
) -> list[AtmJournalEvent]:
    query = db.query(AtmJournalEvent).options(joinedload(AtmJournalEvent.atm))
    if atm_id:
        atm_pk = get_atm_primary_key(db, atm_id)
        if atm_pk is None:
            return []
        query = query.filter(AtmJournalEvent.atm_id == atm_pk)
    if from_at:
        query = query.filter(AtmJournalEvent.occurred_at >= from_at)
    if to_at:
        query = query.filter(AtmJournalEvent.occurred_at <= to_at)
    if atm_id or from_at or to_at:
        query = query.order_by(AtmJournalEvent.occurred_at.desc())
    else:
        query = query.order_by(AtmJournalEvent.received_at.desc(), AtmJournalEvent.occurred_at.desc())
    return query.limit(min(limit, 300)).all()

