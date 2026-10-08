"""本地 SQLite 异步引擎：统一绝对路径、有限锁等待，业务表与后台共享连接策略。"""
from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from sqlalchemy.engine import make_url
from pathlib import Path

from app.core.config import get_settings

_settings = get_settings()

_url = make_url(_settings.SQLITE_URL)
if _url.database and _url.database != ':memory:' and not Path(_url.database).is_absolute():
    _url = _url.set(database=str((Path(__file__).resolve().parents[2] / _url.database).resolve()))
_engine = create_async_engine(_url, future=True, connect_args={"timeout": 5})

@event.listens_for(_engine.sync_engine, 'connect')
def sqlite_connection(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA busy_timeout=5000')
    cursor.close()
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
