"""本地 SQLite 异步引擎（存储登录账号）。"""
from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

_settings = get_settings()

_engine = create_async_engine(_settings.SQLITE_URL, future=True)
_SessionLocal = async_sessionmaker(
    _engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_sqlite_session() -> AsyncIterator[AsyncSession]:
    async with _SessionLocal() as session:
        yield session


def get_engine():
    return _engine


def get_sessionmaker():
    return _SessionLocal
