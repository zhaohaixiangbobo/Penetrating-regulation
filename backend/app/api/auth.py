"""登录与用户信息接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.db.sqlite import get_sqlite_session
from app.deps import get_current_user
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
    token = create_access_token(subject=user.username)
    return LoginResponse(access_token=token, username=user.username)


@router.get("/me", response_model=MeResponse)
async def me(username: str = Depends(get_current_user)) -> MeResponse:
    return MeResponse(username=username)
