from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AgentUpdateTarget


def mark_stale_agent_update_targets(
    db: Session,
    *,
    package_id: int | None = None,
    atm_id: int | None = None,
    now: datetime | None = None,
) -> int:
    stale_after_minutes = max(1, settings.agent_update_stale_after_minutes)
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(minutes=stale_after_minutes)

    query = db.query(AgentUpdateTarget).filter(AgentUpdateTarget.status.in_(["downloading", "applying"]))
    if package_id is not None:
        query = query.filter(AgentUpdateTarget.agent_package_id == package_id)
    if atm_id is not None:
        query = query.filter(AgentUpdateTarget.atm_id == atm_id)

    targets = query.filter(
        or_(
            AgentUpdateTarget.last_progress_at < cutoff,
            and_(AgentUpdateTarget.last_progress_at.is_(None), AgentUpdateTarget.last_checked_at < cutoff),
            and_(
                AgentUpdateTarget.last_progress_at.is_(None),
                AgentUpdateTarget.last_checked_at.is_(None),
                AgentUpdateTarget.assigned_at < cutoff,
            ),
        )
    ).all()

    for target in targets:
        target.status = "failed"
        target.progress_phase = "failed"
        target.progress_message = "Agent update timed out before completion"
        target.last_error = "Agent update timed out before completion"
        target.completed_at = current_time

    return len(targets)
