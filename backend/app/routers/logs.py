from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import AgentLog, AuditLog, User
from ..schemas import AgentLogRead, AuditLogRead

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[AgentLogRead])
def list_agent_logs(
    level: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AgentLog]:
    query = db.query(AgentLog).options(joinedload(AgentLog.atm)).order_by(AgentLog.created_at.desc())
    if level:
        query = query.filter(AgentLog.level == level)
    return query.limit(min(limit, 500)).all()


@router.get("/audit", response_model=list[AuditLogRead])
def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AuditLog]:
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()

