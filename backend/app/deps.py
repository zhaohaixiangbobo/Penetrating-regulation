"""登录依赖：从 Authorization 头解析 JWT，提供用户名与角色。"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from app.core.security import JWTError, decode_token


@dataclass
class Principal:
    """当前登录主体：用户名 + 角色（admin / user）。"""

    username: str
    role: str = "user"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _decode_authorization(authorization: str | None) -> dict:
    """校验 Authorization 头并解码 JWT，返回 payload。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供有效 token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"token 无效: {exc}") from exc
    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token 缺少 subject")
    return payload


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """仅返回用户名（向后兼容：作为各业务接口的登录门禁）。"""
    return _decode_authorization(authorization)["sub"]


def get_current_principal(authorization: str | None = Header(default=None)) -> Principal:
    """返回完整登录主体（含角色），供需要区分权限的接口使用。"""
    payload = _decode_authorization(authorization)
    return Principal(username=payload["sub"], role=payload.get("role") or "user")


def require_admin(principal: Principal = Depends(get_current_principal)) -> Principal:
    """管理员专用依赖：非 admin 角色返回 403。"""
    if not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return principal


CurrentUser = Depends(get_current_user)
CurrentPrincipal = Depends(get_current_principal)
RequireAdmin = Depends(require_admin)
