"""pytest 全局 fixture。

策略：
- 使用独立的临时 SQLite 数据库（覆盖 SQLITE_URL 环境变量）避免污染 data/app.db
- StarRocks 不真连；在需要的测试里通过 dependency_overrides 注入 fake session
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# 在导入 app 之前设置环境变量
_TMP_DIR = Path(tempfile.mkdtemp(prefix="shenji-test-"))
os.environ.setdefault("SQLITE_URL", f"sqlite+aiosqlite:///{(_TMP_DIR / 'test.db').as_posix()}")
os.environ.setdefault("JWT_SECRET", "test-secret-32bytes-xxxxxxxxxxxxxxxx")
# StarRocks 不真连；填个语法合法的占位串
os.environ.setdefault("STARROCKS_URL", "mysql+asyncmy://u:p@127.0.0.1:9030/?charset=utf8mb4")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.sqlite import Base, get_engine, get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_sqlite() -> None:
    """建表 + 插入 admin/tjyc!2026。"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        session.add(User(username="admin", password_hash=hash_password("tjyc!2026")))
        await session.commit()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient) -> str:
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "tjyc!2026"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth_header(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}
