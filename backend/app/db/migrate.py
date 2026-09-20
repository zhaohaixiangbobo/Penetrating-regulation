"""SQLite 轻量迁移：为已存在的库补齐新增列。

SQLAlchemy 的 create_all 只会建「不存在的表」，不会给「已存在的表」加列。
本模块用 PRAGMA 探测并按需 ALTER TABLE，保证老库平滑升级（幂等、可重复执行）。
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("shenji")


async def _existing_columns(conn, table: str) -> set[str]:
    rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
    return {r[1] for r in rows}


async def ensure_sqlite_schema(engine: AsyncEngine) -> None:
    """为 users 表补齐 role / external_id 列（若缺失）。"""
    async with engine.begin() as conn:
        # 表可能尚未创建（首次启动由 create_all 负责），此时跳过迁移
        table_exists = (await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ))).scalar_one_or_none()
        if not table_exists:
            return

        cols = await _existing_columns(conn, "users")
        if "role" not in cols:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'"))
            logger.info("[migrate] users.role 列已添加")
        if "external_id" not in cols:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN external_id VARCHAR(128)"))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_external_id ON users(external_id)"))
            logger.info("[migrate] users.external_id 列与唯一索引已添加")


__all__ = ["ensure_sqlite_schema"]
