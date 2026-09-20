"""登录与用户信息接口。

- /login          ：本地账号密码登录，签发带 role 的 JWT
- /me             ：返回当前用户名与角色
- /sso/login      ：4A/OIDC 单点登录入口（预留，AUTH_MODE=oidc 时跳转身份平台）
- /sso/callback   ：4A/OIDC 回调（预留，换取用户身份后签发本系统 JWT）
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_provider import get_auth_provider
from app.core.security import create_access_token, verify_password
from app.db.sqlite import get_sqlite_session
from app.deps import Principal, get_current_principal
from app.models.user import User
from app.schemas.common import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_sqlite_session)) -> LoginResponse:
    stmt = select(User).where(User.username == payload.username)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在，请联系管理员开通账号")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="密码错误，请重新输入")
    role = user.role or "user"
    # 将角色写入 JWT，业务接口据此做权限判断
    token = create_access_token(subject=user.username, extra={"role": role})
    return LoginResponse(access_token=token, username=user.username, role=role)


@router.get("/me", response_model=MeResponse)
async def me(principal: Principal = Depends(get_current_principal)) -> MeResponse:
    return MeResponse(username=principal.username, role=principal.role)


# ---------------------------------------------------------------------------
# 4A / OIDC 单点登录（预留）
#   AUTH_MODE=local 时这两个接口返回 400（未启用 SSO）；
#   AUTH_MODE=oidc  时 /sso/login 跳转 4A 授权页，回调换身份的逻辑待甲方文档落地。
# ---------------------------------------------------------------------------
@router.get("/sso/login")
async def sso_login() -> RedirectResponse:
    provider = get_auth_provider()
    # TODO(4A): state 应写入服务端会话/缓存以做 CSRF 校验，此处先用随机串占位
    state = uuid.uuid4().hex
    url = provider.build_authorize_url(state=state)
    return RedirectResponse(url=url)


@router.get("/sso/callback")
async def sso_callback(code: str, state: str) -> dict:
    provider = get_auth_provider()
    # 换取用户信息（OIDC 实现落地前返回 501 占位）
    info = await provider.exchange_code(code=code, state=state)
    role = info.get("role") or "user"
    token = create_access_token(subject=info["username"], extra={"role": role})
    return {"access_token": token, "token_type": "bearer",
            "username": info["username"], "role": role}
