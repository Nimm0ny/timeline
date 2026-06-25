import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.app.core.config import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    AUTH_SECRET_FILE,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
)
from backend.app.db.session import get_db
from backend.app.models.entities import User

bearer_scheme = HTTPBearer(auto_error=False)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def get_secret_key() -> str:
    AUTH_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if AUTH_SECRET_FILE.exists():
        return AUTH_SECRET_FILE.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    AUTH_SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"pbkdf2_sha256${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, salt_part, digest_part = encoded.split("$", 2)
        salt = _b64url_decode(salt_part)
        expected = _b64url_decode(digest_part)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(actual, expected)


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_admin": user.is_admin,
        "exp": int((datetime.now(timezone.utc) + timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS)).timestamp()),
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = hmac.new(get_secret_key().encode("utf-8"), body, hashlib.sha256).digest()
    return f"{_b64url_encode(body)}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        body_part, signature_part = token.split(".", 1)
        body = _b64url_decode(body_part)
        expected = hmac.new(get_secret_key().encode("utf-8"), body, hashlib.sha256).digest()
        provided = _b64url_decode(signature_part)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid token")
    payload = json.loads(body.decode("utf-8"))
    if payload.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def ensure_default_admin(db: Session):
    existing = db.query(User).filter(User.username == DEFAULT_ADMIN_USERNAME).first()
    if existing:
        return existing
    user = User(
        username=DEFAULT_ADMIN_USERNAME,
        password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
        is_active=True,
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_access_token(credentials.credentials)
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="账号不可用")
    return user


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
