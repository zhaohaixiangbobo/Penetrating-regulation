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
from app.db.sqlite import Base, get_engine, get_sessionmaker  # noqa: E402
from app.models.user import User  # noqa: E402  (导入以注册模型)

DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "tjyc!2026"


async def init() -> None:
    # 保证 data/ 目录存在（sqlite:///./data/app.db）
    (_ROOT / "data").mkdir(exist_ok=True)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:  # type: AsyncSession
        exists = (await session.execute(select(User).where(User.username == DEFAULT_USER))).scalar_one_or_none()
        if exists is None:
            session.add(User(username=DEFAULT_USER, password_hash=hash_password(DEFAULT_PASSWORD)))
            await session.commit()
            print(f"[ok] 已创建默认用户: {DEFAULT_USER}")
        else:
            print(f"[skip] 用户 {DEFAULT_USER} 已存在")


if __name__ == "__main__":
    asyncio.run(init())
