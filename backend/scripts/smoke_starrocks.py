"""StarRocks 连通性冒烟测试：SELECT 1。仅本地手动跑。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.starrocks import get_engine  # noqa: E402


async def main() -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        row = (await conn.execute(text("SELECT 1 AS v"))).first()
        print("StarRocks OK:", row)


if __name__ == "__main__":
    asyncio.run(main())
