import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import ATM, User
from .page_permissions import normalize_allowed_pages


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return f"pbkdf2_sha256${_b64url_encode(salt)}${_b64url_encode(derived)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_b64, derived_b64 = password_hash.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(derived_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
        return hmac.compare_digest(actual, expected)
    except ValueError:
        return False


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)

    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(
            settings.jwt_secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
        ).digest()
        provided = _b64url_decode(signature_b64)
        if not hmac.compare_digest(expected, provided):
            raise ValueError("invalid signature")
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("token expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    payload = decode_access_token(authorization.split(" ", 1)[1])
    username = payload.get("sub")
    user = db.query(User).filter(User.username == username, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def get_agent_atm(
    x_atm_id: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ATM:
    if not x_atm_id or not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing agent credentials")

    atm = db.query(ATM).filter(ATM.atm_id == x_atm_id).first()
    if not atm or not hmac.compare_digest(atm.api_key_hash, hash_api_key(x_api_key)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credentials")
    return atm


def ensure_admin_user(db: Session) -> None:
    if db.query(User).count() > 0:
        for user in db.query(User).all():
            normalized = normalize_allowed_pages(user.role, user.allowed_pages)
            if user.allowed_pages != normalized:
                user.allowed_pages = normalized
        db.commit()
        return
    user = User(
        username=settings.admin_username,
        password_hash=hash_password(settings.admin_password),
        role="admin",
        allowed_pages=normalize_allowed_pages("admin", None),
        is_active=True,
    )
    db.add(user)
    db.commit()
