from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from ..auth import create_access_token, generate_session_id, get_current_user, hash_session_id, verify_password
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, TokenResponse, UserRead
from ..services.audit_service import write_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == payload.username, User.is_active.is_(True)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        write_audit(
            db,
            actor_type="user",
            actor_id=payload.username,
            action="login_failed",
            entity_type="user",
            entity_id=payload.username,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    session_id = generate_session_id()
    previous_session_active = bool(user.active_session_hash)
    user.active_session_hash = hash_session_id(session_id)
    user.active_session_started_at = datetime.now(timezone.utc)
    token = create_access_token(
        user.username,
        {"sid": session_id, "role": user.role, "allowed_pages": user.allowed_pages},
    )
    write_audit(
        db,
        actor_type="user",
        actor_id=user.username,
        action="login_success",
        entity_type="user",
        entity_id=str(user.id),
        details={"previous_session_invalidated": previous_session_active},
    )
    db.commit()
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    session_id = ""
    if authorization and authorization.lower().startswith("bearer "):
        from ..auth import decode_access_token

        session_id = str(decode_access_token(authorization.split(" ", 1)[1]).get("sid") or "")
    if session_id and current_user.active_session_hash == hash_session_id(session_id):
        current_user.active_session_hash = None
        current_user.active_session_started_at = None
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="logout",
        entity_type="user",
        entity_id=str(current_user.id),
    )
    db.commit()
    return {"ok": True}
