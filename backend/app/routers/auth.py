from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, verify_password
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

    token = create_access_token(user.username, {"role": user.role, "allowed_pages": user.allowed_pages})
    write_audit(
        db,
        actor_type="user",
        actor_id=user.username,
        action="login_success",
        entity_type="user",
        entity_id=str(user.id),
    )
    db.commit()
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
