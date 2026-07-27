"""审计查询接口测试。

因为不实际连 StarRocks，我们做两件事：
1. 参数校验（com_id 白名单、日期边界）——只走到校验层
2. 用 FastAPI dependency_overrides 注入 FakeSession，验证：
   - SQL 参数正确绑定
   - 功能 3 的 tot(秒) 会被转换为 visit_minutes(分钟, 2 位小数)
   - 分页信息正确
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.sql.elements import TextClause

from app.db.starrocks import get_starrocks_session
from app.main import app

pytestmark = pytest.mark.asyncio


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | int) -> None:
        self._rows = rows

    def first(self):
        # count 查询会走这里，rows 应为 int
        return (self._rows,) if isinstance(self._rows, int) else None

    def mappings(self):
        return self

    def all(self):
        return list(self._rows) if isinstance(self._rows, list) else []


class FakeSession:
    """伪造 AsyncSession，只实现 execute。"""

    def __init__(self, count_value: int, data_rows: list[dict[str, Any]]) -> None:
        self.count_value = count_value
        self.data_rows = data_rows
        self.executed: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, clause: TextClause, params: dict[str, Any] | None = None):
        sql = str(clause)
        self.executed.append((sql, dict(params or {})))
        # 第一次是 count（包含 "count(*)" 外层），第二次是数据（含 LIMIT/OFFSET）
        if "count(*) AS c" in sql:
            return _FakeResult(self.count_value)
        return _FakeResult(self.data_rows)


def _use_fake(session: FakeSession):
    async def _dep():
        yield session

    app.dependency_overrides[get_starrocks_session] = _dep


def _clear_fake() -> None:
    app.dependency_overrides.pop(get_starrocks_session, None)


# ---------- 参数校验 ----------

async def test_short_visit_invalid_com_id(client: AsyncClient, auth_header: dict[str, str]) -> None:
    resp = await client.post(
        "/api/audit/short-visit",
        json={
            "com_id": "99999999",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
        },
        headers=auth_header,
    )
    assert resp.status_code == 422
    assert "非法公司代码" in resp.text


async def test_short_visit_date_floor(client: AsyncClient, auth_header: dict[str, str]) -> None:
    resp = await client.post(
        "/api/audit/short-visit",
        json={
            "com_id": "11120101",
            "start_date": "2023-06-01T00:00:00",
            "end_date": "2024-01-31T23:59:59",
        },
        headers=auth_header,
    )
    assert resp.status_code == 422
    assert "2024-01-01" in resp.text


async def test_full_cust_miss_month_floor(client: AsyncClient, auth_header: dict[str, str]) -> None:
    resp = await client.post(
        "/api/audit/full-cust-miss",
        json={
            "com_id": "11120101",
            "start_month": "2024-12-01",
            "end_month": "2025-03-01",
        },
        headers=auth_header,
    )
    assert resp.status_code == 422
    assert "2025-02-01" in resp.text


# ---------- 使用 FakeSession ----------

async def test_short_visit_binds_params_and_pages(client: AsyncClient, auth_header: dict[str, str]) -> None:
    fake_rows = [
        {
            "com_id": "11120101",
            "short_name": "第一",
            "cust_code": "C001",
            "license_code": "L001",
            "cust_name": "客户 A",
            "terminal_level": "档位 1",
            "person_name": "张三",
            "plan_date": "2024-06-01",
            "visit_time": 45,
        }
    ]
    session = FakeSession(count_value=123, data_rows=fake_rows)
    _use_fake(session)
    try:
        resp = await client.post(
            "/api/audit/short-visit",
            json={
                "com_id": "11120101",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T23:59:59",
                "page": 2,
                "page_size": 10,
            },
            headers=auth_header,
        )
    finally:
        _clear_fake()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 123
    assert body["page"] == 2
    assert body["page_size"] == 10
    assert body["items"][0]["cust_code"] == "C001"

    # 断言执行了 count + data 两次；data 查询附带 limit/offset
    assert len(session.executed) == 2
    _, count_params = session.executed[0]
    assert count_params["com_id"] == "11120101"
    assert count_params["start_date"] == datetime(2024, 1, 1)
    _, data_params = session.executed[1]
    assert data_params["limit"] == 10
    assert data_params["offset"] == 10  # (page-1)*page_size


async def test_daily_under_hour_converts_minutes(client: AsyncClient, auth_header: dict[str, str]) -> None:
    fake_rows = [
        {
            "v_date": "2024-06-01",
            "com_id": "11120101",
            "short_name": "第一",
            "sdpt_name": "营销部",
            "cust_manager_person_uuid": "u-1",
            "person_name": "张三",
            "tot": 1830,  # 30.5 分钟
        },
        {
            "v_date": "2024-06-02",
            "com_id": "11120101",
            "short_name": "第一",
            "sdpt_name": "营销部",
            "cust_manager_person_uuid": "u-2",
            "person_name": "李四",
            "tot": 100,  # 1.6666... -> 1.67
        },
    ]
    session = FakeSession(count_value=2, data_rows=fake_rows)
    _use_fake(session)
    try:
        resp = await client.post(
            "/api/audit/daily-under-hour",
            json={
                "com_id": "11120101",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T23:59:59",
            },
            headers=auth_header,
        )
    finally:
        _clear_fake()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    minutes = [row["visit_minutes"] for row in body["items"]]
    assert minutes == [30.5, 1.67]


async def test_full_cust_miss_binds_month(client: AsyncClient, auth_header: dict[str, str]) -> None:
    session = FakeSession(count_value=0, data_rows=[])
    _use_fake(session)
    try:
        resp = await client.post(
            "/api/audit/full-cust-miss",
            json={
                "com_id": "11120101",
                "start_month": "2025-02-01",
                "end_month": "2025-06-01",
            },
            headers=auth_header,
        )
    finally:
        _clear_fake()

    assert resp.status_code == 200
    _, count_params = session.executed[0]
    assert count_params["com_id"] == "11120101"
    assert str(count_params["start_month"]) == "2025-02-01"
    assert str(count_params["end_month"]) == "2025-06-01"


async def test_audit_requires_auth(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/audit/short-visit",
        json={"com_id": "11120101", "start_date": "2024-01-01T00:00:00", "end_date": "2024-12-31T00:00:00"},
    )
    assert resp.status_code == 401
