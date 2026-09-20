"""初始化 SQLite：建表 + 写入 admin/tjyc!2026。

用法：
    D:\\3-anaconda\\envs\\py312\\python.exe -m scripts.init_db
（在 backend 目录下执行）
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 让 python -m scripts.init_db 在 backend 目录下可用
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.migrate import ensure_sqlite_schema  # noqa: E402
from app.db.sqlite import Base, get_engine, get_sessionmaker  # noqa: E402
from app.models.clue import AuditClue  # noqa: E402,F401  (导入以注册线索相关表)
from app.models.user import User  # noqa: E402  (导入以注册模型)

DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "Tjyc!2026"
DEFAULT_ROLE = "admin"

# 需要预置的账号清单：(用户名, 密码, 角色)
# admin：默认管理员；user：默认普通用户
SEED_USERS: list[tuple[str, str, str]] = [
    (DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_ROLE),
    ("user", "Tjyc!2026", "user"),
]


async def _ensure_user(session: AsyncSession, username: str, password: str, role: str) -> None:
    """幂等确保账号存在：不存在则创建；存在但角色不符则修正。"""
    exists = (await session.execute(
        select(User).where(User.username == username))).scalar_one_or_none()
    if exists is None:
        session.add(User(username=username,
                    password_hash=hash_password(password),
                    role=role))
        await session.commit()
        print(f"[ok] 已创建用户: {username} (role={role})")
    elif getattr(exists, "role", None) != role:
        exists.role = role
        await session.commit()
        print(f"[ok] 已将 {username} 角色更新为 {role}")
    else:
        print(f"[skip] 用户 {username} 已存在")


async def init() -> None:
    # 保证 data/ 目录存在（sqlite:///./data/app.db）
    (_ROOT / "data").mkdir(exist_ok=True)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 老库平滑升级：补齐 role / external_id 列
    await ensure_sqlite_schema(engine)

    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:  # type: AsyncSession
        for username, password, role in SEED_USERS:
            await _ensure_user(session, username, password, role)


if __name__ == "__main__":
    asyncio.run(init())
