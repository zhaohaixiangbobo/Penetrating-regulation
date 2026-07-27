"""StarRocks 异步引擎与 Session 依赖。"""
from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

# StarRocks 使用 MySQL 协议；pool_recycle 避免长连接被服务器踢
_engine = create_async_engine(
    _settings.STARROCKS_URL,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
    pool_pre_ping=True,
    future=True,
)

_SessionLocal = async_sessionmaker(
    _engine, expire_on_commit=False, class_=AsyncSession)


async def get_starrocks_session() -> AsyncIterator[AsyncSession]:
    async with _SessionLocal() as session:
        yield session


def get_engine():
    """暴露给测试或初始化脚本使用。"""
    return _engine
