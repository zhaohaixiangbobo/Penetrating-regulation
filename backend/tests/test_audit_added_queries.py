"""新增营销审计查询测试：接口契约及小规模内存 SQL 业务样本。

复用现有 FakeSession，另外用 SQLite 日期函数适配执行业务查询；
目标 StarRocks 方言和真实表结构仍需部署环境小范围核验。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from .test_audit import FakeSession, _FakeResult, _clear_fake, _use_fake

pytestmark = pytest.mark.asyncio

LONG_REQUEST = {"com_ids": ["11120101"], "start_date": "2024-06-01", "end_date": "2024-06-30"}
MONTH_REQUEST = {"com_ids": ["11120101"], "start_month": "2025-10-01", "end_month": "2025-10-01"}


@pytest.mark.parametrize("path,payload", [
    ("long-visit", LONG_REQUEST), ("long-visit/export", LONG_REQUEST),
    ("auto-collect-miss", MONTH_REQUEST), ("auto-collect-miss/export", MONTH_REQUEST),
])
async def test_added_queries_require_auth(client, path, payload):
    response = await client.post(f"/api/audit/{path}", json=payload)
    assert response.status_code == 401


@pytest.mark.parametrize("path,payload,detail", [
    ("long-visit", {**LONG_REQUEST, "com_ids": []}, "至少选择一个公司"),
    ("long-visit/export", {**LONG_REQUEST, "com_ids": ["invalid"]}, "非法公司代码"),
    ("long-visit", {**LONG_REQUEST, "start_date": "2023-12-31"}, "2024-01-01"),
    ("long-visit", {**LONG_REQUEST, "end_date": "2024-05-31"}, "结束日期"),
    ("long-visit", {**LONG_REQUEST, "threshold_minutes": 270}, None),
    ("long-visit/export", {**LONG_REQUEST, "threshold_minutes": 0}, None),
    ("auto-collect-miss", {**MONTH_REQUEST, "start_month": "2025-08-01"}, "2025-09-01"),
    ("auto-collect-miss/export", {**MONTH_REQUEST, "end_month": "2025-09-01"}, "结束月份"),
    ("auto-collect-miss", {**MONTH_REQUEST, "start_month": "2025-10-02", "end_month": "2025-10-02"}, "第一天"),
    ("auto-collect-miss", {**MONTH_REQUEST, "page_size": 201}, None),
])
async def test_added_queries_validate_parameters(client, auth_header, path, payload, detail):
    response = await client.post(f"/api/audit/{path}", json=payload, headers=auth_header)
    assert response.status_code == 422
    if detail:
        assert detail in response.text


@pytest.mark.parametrize("path,payload,rows,sort_sql", [
    ("long-visit", {**LONG_REQUEST, "threshold_minutes": 280, "sort_field": "visit_minutes", "sort_order": "ascend"},
     [{"visit_id": "9007199254740993", "visit_time": 18001, "cust_uuid": "c1", "person_name": "甲"}], "ORDER BY visit_time ASC"),
    ("auto-collect-miss", {**MONTH_REQUEST, "sort_field": "year_month", "sort_order": "descend"},
     [{"year_month": "202510", "cust_uuid": "c1", "mgr_id": "m1"}], "ORDER BY year_month DESC"),
])
async def test_added_queries_page_and_export_match(client, auth_header, path, payload, rows, sort_sql):
    payload = {**payload, "com_ids": ["11120101", "11120102"], "sdpt_name": "营业部甲", "person_uuid": "m1", "page": 2, "page_size": 10}
    session = FakeSession(11, rows)
    _use_fake(session)
    try:
        page = await client.post(f"/api/audit/{path}", json=payload, headers=auth_header)
        export = await client.post(f"/api/audit/{path}/export", json=payload, headers=auth_header)
    finally:
        _clear_fake()
    assert page.status_code == export.status_code == 200
    assert page.json()["page"] == 2
    assert page.json()["total"] == 11
    assert page.json()["items"] == export.json()
    if path == "long-visit":
        assert page.json()["items"][0]["visit_minutes"] == 300.02
        assert page.json()["items"][0]["visit_id"] == "9007199254740993"
    count_sql, count_params = session.executed[0]
    if path == "long-visit":
        assert count_params["threshold_seconds"] == 280 * 60
    data_sql, data_params = session.executed[1]
    export_sql, export_params = session.executed[2]
    assert "'11120101', '11120102'" in count_sql
    assert data_params["offset"] == 10 and data_params["limit"] == 10
    assert export_params["export_limit"] == 100000
    assert {k: v for k, v in data_params.items() if k not in {"limit", "offset"}} == count_params
    assert {k: v for k, v in export_params.items() if k != "export_limit"} == count_params
    assert count_params["sdpt_name"] == "营业部甲" and count_params["person_uuid"] == "m1"
    assert sort_sql in data_sql and sort_sql in export_sql


async def test_added_queries_sort_field_is_controlled(client, auth_header):
    session = FakeSession(0, [])
    _use_fake(session)
    try:
        for path, payload in [("long-visit", LONG_REQUEST), ("auto-collect-miss", MONTH_REQUEST)]:
            response = await client.post(f"/api/audit/{path}", json={**payload, "sort_field": "injected_column; DROP TABLE x", "sort_order": "injected_order"}, headers=auth_header)
            assert response.status_code == 200 and response.json()["items"] == []
    finally:
        _clear_fake()
    assert all("injected" not in sql for sql, _ in session.executed)


class SqliteAuditSession:
    """用微型样本执行生成的 SQL，日期方言转换只用于测试。"""

    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.create_function("DATE_FORMAT", 2, lambda value, fmt: datetime.fromisoformat(value).strftime(fmt.replace("%i", "%M").replace("%s", "%S")) if value else None)
        self.connection.executescript("""
          CREATE TABLE crm_mcs_cust_visit_plan (
            plan_date TEXT, cust_uuid TEXT, cust_manager_person_uuid TEXT,
            license_code TEXT, cust_name TEXT, visit_time INTEGER, visit_status TEXT, deleted TEXT,
            id INTEGER PRIMARY KEY AUTOINCREMENT
          );
          CREATE TABLE t_comm_emp_yx (person_uuid TEXT, com_id TEXT, short_name TEXT, sdpt_name TEXT, person_name TEXT);
          CREATE TABLE t_comm_employee (person_uuid TEXT, com_id TEXT, short_name TEXT, sdpt_name TEXT, person_name TEXT);
          CREATE TABLE uc_evaluation_m (evaluation_m_uuid TEXT, sysupdatedate TEXT, evaluation_type_adj TEXT, status TEXT, y_m TEXT);
          CREATE TABLE uc_evaluation_m_cust (evaluation_m_uuid TEXT, cust_uuid TEXT);
          CREATE TABLE kc_customer_yz (id TEXT, cust_code TEXT, cust_name TEXT, customer_manager_person_id TEXT);
        """)
        for table in ["t_comm_emp_yx", "t_comm_employee"]:
            self.connection.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?)", [
                ("m1", "11120101", "第一", "营业部甲", "甲"),
                ("m2", "11120102", "第二", "营业部乙", "乙"),
            ])

    async def execute(self, clause, params=None):
        sql = str(clause).replace("DATE_ADD(:end_date, INTERVAL 1 DAY)", "datetime(:end_date, '+1 day')").replace("DATE_ADD(:end_month, INTERVAL 1 MONTH)", "date(:end_month, '+1 month')")
        rows = self.connection.execute(sql, params or {}).fetchall()
        return _FakeResult(int(rows[0][0]) if "count(*) AS c" in sql else [dict(row) for row in rows])


@pytest.mark.parametrize("threshold_minutes", [260, 280, 300, 320, 340])
async def test_added_long_visit_business_boundaries(client, auth_header, threshold_minutes):
    session = SqliteAuditSession()
    threshold_seconds = threshold_minutes * 60
    records = [
        ("2024-06-30 23:59:59", "over", "m1", "L1", "客户甲", threshold_seconds + 1, "03", "0"),
        ("2024-06-01 00:00:00", "equal", "m1", "L2", "客户乙", threshold_seconds, "03", "0"),
        ("2024-06-01 00:00:00", "under", "m1", "L3", "客户丙", threshold_seconds - 1, "03", "0"),
        ("2024-07-01 00:00:00", "later", "m1", "L4", "客户丁", 19000, "03", "0"),
        ("2024-06-02 00:00:00", "deleted", "m1", "L5", "删除", 19000, "03", "1"),
        ("2024-06-02 00:00:00", "invalid", "m1", "L6", "无效", 19000, "02", "0"),
        ("2024-06-02 00:00:00", "other", "m2", "L7", "其他公司", 19000, "03", "0"),
    ]
    session.connection.executemany("INSERT INTO crm_mcs_cust_visit_plan (plan_date, cust_uuid, cust_manager_person_uuid, license_code, cust_name, visit_time, visit_status, deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", records)
    _use_fake(session)
    try:
        # 300 分钟场景省略参数，同时验证旧调用的默认值兼容。
        threshold_payload = {} if threshold_minutes == 300 else {"threshold_minutes": threshold_minutes}
        response = await client.post("/api/audit/long-visit", json={**LONG_REQUEST, **threshold_payload, "sdpt_name": "营业部甲", "person_uuid": "m1"}, headers=auth_header)
    finally:
        _clear_fake()
        session.connection.close()
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["cust_uuid"] == "over"
    assert response.json()["items"][0]["visit_minutes"] == round((threshold_seconds + 1) / 60, 2)
    assert response.json()["items"][0]["visit_id"] == "1"


async def test_added_auto_collect_business_month_and_zero_count(client, auth_header):
    session = SqliteAuditSession()
    # 相同客户重复评价应合并；计算月份早于查询月、但生效月在范围内的评价仍有效。
    evaluations = [
        ("e1", "2025-10-15", "03", "3", "2025-09", "missing", "m1"),
        ("e2", "2025-10-16", "03", "3", "2025-09", "missing", "m1"),
        ("e3", "2025-10-15", "03", "3", "2025-09", "zero_time", "m1"),
        ("e4", "2025-10-15", "03", "3", "2025-09", "invalid_visit", "m1"),
        ("e5", "2025-10-15", "04", "3", "2025-09", "full", "m1"),
        ("e6", "2025-11-01", "03", "3", "2025-09", "later", "m1"),
        ("e7", "2025-10-15", "03", "2", "2025-09", "inactive", "m1"),
        ("e8", "2025-10-15", "03", "3", "2025-08", "old_eval", "m1"),
        ("e9", "2025-10-15", "03", "3", "2025-09", "other", "m2"),
    ]
    session.connection.executemany("INSERT INTO uc_evaluation_m VALUES (?, ?, ?, ?, ?)", [e[:5] for e in evaluations])
    session.connection.executemany("INSERT INTO uc_evaluation_m_cust VALUES (?, ?)", [(e[0], e[5]) for e in evaluations])
    session.connection.executemany("INSERT INTO kc_customer_yz VALUES (?, ?, ?, ?)", list({(e[5], e[5], e[5], e[6]) for e in evaluations}))
    session.connection.executemany("INSERT INTO crm_mcs_cust_visit_plan (plan_date, cust_uuid, cust_manager_person_uuid, license_code, cust_name, visit_time, visit_status, deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
        ("2025-10-31 23:59:59", "zero_time", "m1", "L1", "零时长", 0, "03", "0"),
        ("2025-10-02", "invalid_visit", "m1", "L2", "无效拜访", 60, "02", "0"),
        ("2025-10-02", "invalid_visit", "m1", "L2", "删除拜访", 60, "03", "1"),
        ("2025-09-30", "missing", "m1", "L3", "上月拜访", 60, "03", "0"),
    ])
    _use_fake(session)
    try:
        response = await client.post("/api/audit/auto-collect-miss", json={**MONTH_REQUEST, "sdpt_name": "营业部甲", "person_uuid": "m1"}, headers=auth_header)
    finally:
        _clear_fake()
        session.connection.close()
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert {row["cust_uuid"] for row in response.json()["items"]} == {"missing", "invalid_visit"}
    assert all(row["year_month"] == "202510" for row in response.json()["items"])
