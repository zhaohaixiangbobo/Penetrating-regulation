"""密码 hash 与 JWT 签发/校验。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRE_MIN)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """解码 JWT，失败抛 JWTError。"""
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


__all__ = ["hash_password", "verify_password",
           "create_access_token", "decode_token", "JWTError"]
