"""登录依赖：从 Authorization 头解析 JWT。"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from app.core.security import JWTError, decode_token


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供有效 token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"token 无效: {exc}") from exc
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 缺少 subject")
    return sub


CurrentUser = Depends(get_current_user)
