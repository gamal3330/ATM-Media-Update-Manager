from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..database import get_db
from ..models import User
from ..page_permissions import ALL_PAGE_IDS, SYSTEM_ADMIN_ROLES, normalize_allowed_pages
from ..schemas import PagePermissionRead, UserCreate, UserRead, UserUpdate
from ..services.audit_service import write_audit

router = APIRouter(prefix="/api/users", tags=["users"])

PAGE_LABELS = {
    "dashboard": "لوحة التحكم",
    "atms": "الصرافات",
    "upload": "رفع الحزمة",
    "packages": "التحديثات",
    "cash": "مراقبة النقد",
    "agent-downloads": "Agent Downloads",
    "logs": "السجلات",
    "settings": "الإعدادات",
    "users": "إدارة المستخدمين",
}


def active_admin_count(db: Session) -> int:
    return db.query(User).filter(User.role.in_(SYSTEM_ADMIN_ROLES), User.is_active.is_(True)).count()


@router.get("/pages", response_model=list[PagePermissionRead])
def list_pages(current_user: User = Depends(require_admin)) -> list[PagePermissionRead]:
    return [PagePermissionRead(id=page_id, label=PAGE_LABELS[page_id]) for page_id in ALL_PAGE_IDS]


@router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[User]:
    return db.query(User).order_by(User.username.asc()).all()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> User:
    username = payload.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        allowed_pages=normalize_allowed_pages(payload.role, payload.allowed_pages),
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="user_created",
        entity_type="user",
        entity_id=user.username,
        details={"role": user.role, "allowed_pages": user.allowed_pages, "is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    changes = payload.model_dump(exclude_unset=True)
    if "username" in changes:
        username = changes["username"].strip()
        existing = db.query(User).filter(User.username == username, User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
        user.username = username

    next_role = changes.get("role", user.role)
    if user.id == current_user.id and next_role not in SYSTEM_ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove admin role from yourself")
    if user.id == current_user.id and changes.get("is_active") is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")
    if user.role in SYSTEM_ADMIN_ROLES and user.is_active and next_role not in SYSTEM_ADMIN_ROLES and active_admin_count(db) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last active admin")

    if "password" in changes and changes["password"]:
        user.password_hash = hash_password(changes["password"])
    if "role" in changes:
        user.role = next_role
    if "is_active" in changes:
        if user.role in SYSTEM_ADMIN_ROLES and changes["is_active"] is False and active_admin_count(db) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate the last active admin")
        user.is_active = changes["is_active"]

    if "allowed_pages" in changes or "role" in changes:
        requested_pages = changes.get("allowed_pages", user.allowed_pages)
        user.allowed_pages = normalize_allowed_pages(user.role, requested_pages)

    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="user_updated",
        entity_type="user",
        entity_id=user.username,
        details={
            key: value for key, value in changes.items() if key != "password"
        },
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Response:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")
    if user.role in SYSTEM_ADMIN_ROLES and user.is_active and active_admin_count(db) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate the last active admin")

    user.is_active = False
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="user_deactivated",
        entity_type="user",
        entity_id=user.username,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
