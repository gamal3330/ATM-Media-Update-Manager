from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from ..auth import require_page
from ..database import get_db
from ..models import AgentLog, AtmJournalEvent, AuditLog, User
from ..schemas import AgentLogRead, AuditLogRead, JournalEventRead

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[AgentLogRead])
def list_agent_logs(
    level: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("logs")),
) -> list[AgentLog]:
    query = db.query(AgentLog).options(joinedload(AgentLog.atm)).order_by(AgentLog.created_at.desc())
    if level:
        query = query.filter(AgentLog.level == level)
    return query.limit(min(limit, 500)).all()


@router.get("/audit", response_model=list[AuditLogRead])
def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("logs")),
) -> list[AuditLog]:
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()


@router.get("/journal", response_model=list[JournalEventRead])
def list_journal_events(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_page("logs")),
) -> list[AtmJournalEvent]:
    return (
        db.query(AtmJournalEvent)
        .options(joinedload(AtmJournalEvent.atm))
        .order_by(AtmJournalEvent.occurred_at.desc())
        .limit(min(limit, 500))
        .all()
    )

