"""端到端验证：登录 + 3 个审计接口跑真实 StarRocks。

用法：
  cd d:\\2-code\\shenji\\backend
  D:\\3-anaconda\\envs\\py312\\python.exe -m scripts.verify_apis

不真起 uvicorn，通过 httpx.ASGITransport 直接调 FastAPI in-process。
"""
from __future__ import annotations

import asyncio
import json

from httpx import ASGITransport, AsyncClient

from app.main import create_app


def _dump(tag: str, resp) -> None:
    print(f"\n=== {tag} [{resp.status_code}] ===")
    try:
        data = resp.json()
    except Exception:
        print(resp.text[:500])
        return
    if isinstance(data, dict) and "items" in data:
        print(
            f"total = {data.get('total')}, page = {data.get('page')}, size = {data.get('page_size')}")
        for i, row in enumerate(data.get("items", [])[:3], start=1):
            print(f"  #{i}: {json.dumps(row, ensure_ascii=False)}")
    else:
        print(json.dumps(data, ensure_ascii=False)[:500])


async def main() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # 1) 登录拿 token
        r = await c.post("/api/auth/login", json={"username": "admin", "password": "tjyc!2026"})
        _dump("login", r)
        r.raise_for_status()
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        # 2) 功能 1
        r = await c.post(
            "/api/audit/short-visit",
            json={
                "com_ids": ["11120101"],
                "start_date": "2024-01-01",
                "end_date": "2025-12-31",
                "page": 1,
                "page_size": 3,
            },
            headers=h,
        )
        _dump("short-visit / 11120101 / 2024-2025", r)

        # 3) 功能 2
        r = await c.post(
            "/api/audit/full-cust-miss",
            json={
                "com_ids": ["11120101"],
                "start_month": "2025-02-01",
                "end_month": "2025-06-01",
                "page": 1,
                "page_size": 3,
            },
            headers=h,
        )
        _dump("full-cust-miss / 11120101 / 2025-02..06", r)

        # 4) 功能 3
        r = await c.post(
            "/api/audit/daily-under-hour",
            json={
                "com_ids": ["11120101"],
                "start_date": "2024-01-01",
                "end_date": "2025-12-31",
                "page": 1,
                "page_size": 3,
            },
            headers=h,
        )
        _dump("daily-under-hour / 11120101 / 2024-2025", r)


if __name__ == "__main__":
    asyncio.run(main())
