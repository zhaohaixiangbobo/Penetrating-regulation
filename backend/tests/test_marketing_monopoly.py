"""营销专卖最小测试：鉴权、参数、分页导出一致性及最新绑卡比对边界。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from .test_audit import FakeSession, _FakeResult, _clear_fake, _use_fake

pytestmark = pytest.mark.asyncio
BASE_URL = "/api/marketing-monopoly"


async def test_shared_issuing_organizations(client, auth_header):
    """营销专卖共用有效许可证机关字典，兼容旧页面请求时也保持一致。"""
    session = FakeSession(1, [{"issue_org_code": "ORG1", "issue_org_name": "机关一"}])
    _use_fake(session)
    try:
        response = await client.get(BASE_URL + '/issuing-organizations', headers=auth_header)
        legacy = await client.get(BASE_URL + '/issuing-organizations?include_inactive=true', headers=auth_header)
    finally:
        _clear_fake()
    assert response.status_code == legacy.status_code == 200
    assert response.json() == legacy.json()
    assert all("lic_status = '10'" in sql for sql, _ in session.executed)


@pytest.mark.parametrize("method,path", [
    ("GET", "/issuing-organizations"),
    ("POST", "/bank-owner-mismatch"),
    ("POST", "/bank-owner-mismatch/export"),
])
async def test_monopoly_requires_auth(client, method, path):
    response = await client.request(method, BASE_URL + path, **({"json": {}} if method == "POST" else {}))
    assert response.status_code == 401


@pytest.mark.parametrize("payload", [
    {"start_date": "2026-09-01"},
    {"end_date": "2026-09-30"},
    {"start_date": "2026-09-30", "end_date": "2026-09-01"},
    {"page": 0},
    {"page_size": 201},
    {"sort_field": "lic_no; DROP TABLE r_license_info"},
    {"issue_org_codes": [""]},
])
async def test_monopoly_validates_parameters(client, auth_header, payload):
    response = await client.post(BASE_URL + "/bank-owner-mismatch", json=payload, headers=auth_header)
    assert response.status_code == 422


async def test_monopoly_query_export_share_filters_and_sort(client, auth_header):
    session = FakeSession(12, [{"retailer_uuid": "r1", "custbank_uuid": "b1", "lic_no": "001", "manager_name": "甲", "bankcard_owner": "乙"}])
    payload = {
        "issue_org_codes": ["ORG1", "quote'org"], "lic_no": "001", "company_name": "%客户",
        "start_date": "2026-09-01", "end_date": "2026-09-30",
        "sort_field": "lic_no", "sort_order": "ascend", "page": 2, "page_size": 10,
    }
    _use_fake(session)
    try:
        query = await client.post(BASE_URL + "/bank-owner-mismatch", json=payload, headers=auth_header)
        export = await client.post(BASE_URL + "/bank-owner-mismatch/export", json=payload, headers=auth_header)
    finally:
        _clear_fake()
    assert query.status_code == export.status_code == 200
    assert query.json()["items"] == export.json()
    assert query.json()["total"] == 12 and query.json()["page"] == 2
    count_sql, count_params = session.executed[0]
    data_sql, data_params = session.executed[1]
    export_sql, export_params = session.executed[2]
    assert data_params["limit"] == data_params["offset"] == 10
    assert export_params["export_limit"] == 100000
    assert {k: v for k, v in data_params.items() if k not in {"limit", "offset"}} == count_params
    assert {k: v for k, v in export_params.items() if k != "export_limit"} == count_params
    assert "quote'org" not in count_sql and count_params["issue_org_1"] == "quote'org"
    assert count_params["company_name"] == "%客户"
    assert "ORDER BY lic_no ASC" in data_sql and "ORDER BY lic_no ASC" in export_sql


class BankSqliteSession:
    """微型样本直接执行窗口函数查询；日期函数适配仅用于测试。"""

    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.create_function("DATE_FORMAT", 2, lambda value, fmt: datetime.fromisoformat(value).strftime(fmt.replace("%i", "%M").replace("%s", "%S")) if value else None)
        self.connection.executescript("""
            CREATE TABLE pc_pay_custbank (custbank_uuid TEXT, cust_code TEXT, bankcard_owner TEXT, sysupdatedt TEXT);
            CREATE TABLE r_license_info (retailer_uuid TEXT, issue_org_code TEXT, issue_org_name TEXT, lic_no TEXT, company_name TEXT, manager_name TEXT, lic_status TEXT);
        """)
        self.connection.executemany("INSERT INTO r_license_info VALUES (?, ?, ?, ?, ?, ?, ?)", [
            (f"r-{code}", "ORG2" if code == "I" else "ORG1", "机关二" if code == "I" else "机关一", code,
             "百分%客户" if code == "B" else f"客户{code}", None if code == "H" else "持证甲", "20" if code == "G" else "10")
            for code in "ABCDEFGHIJK"
        ])
        self.connection.executemany("INSERT INTO pc_pay_custbank VALUES (?, ?, ?, ?)", [
            ("A1", "A", "旧户名", "2026-08-01"), ("A2", "A", "持证甲", "2026-09-02"),
            ("B1", "B", "持证甲", "2026-08-01"), ("B2", "B", "最新乙", "2026-09-03"),
            ("C1", "C", "  持证甲  ", "2026-09-02"),
            ("D1", "D", "旧户名", "2026-08-01"), ("D2", "D", None, "2026-09-02"),
            ("E1", "E", "   ", "2026-09-02"),
            ("G1", "G", "其他户名", "2026-09-02"), ("H1", "H", "其他户名", "2026-09-02"),
            ("I1", "I", "不同姓名", "2026-09-30 23:59:59"),
            ("J1", "J", "旧户名", "2026-09-01"), ("J2", "J", "新户名", "2026-10-01 00:00:00"),
            ("K1", "K", "持证甲", "2026-09-01"), ("K2", "K", "同时间乙", "2026-09-01"),
        ])

    async def execute(self, clause, params=None):
        sql = str(clause).replace("DATE_ADD(:end_date, INTERVAL 1 DAY)", "datetime(:end_date, '+1 day')")
        rows = self.connection.execute(sql, params or {}).fetchall()
        return _FakeResult(int(rows[0][0]) if "count(*) AS c" in sql else [dict(row) for row in rows])


@pytest.mark.parametrize("payload,expected", [
    ({}, {"B", "I", "J", "K"}),
    ({"start_date": "2026-09-01", "end_date": "2026-09-30"}, {"B", "I", "K"}),
    ({"issue_org_codes": ["ORG2"]}, {"I"}),
    ({"lic_no": " B "}, {"B"}),
    ({"company_name": "%"}, {"B"}),
    ({"lic_no": "A"}, set()),
])
async def test_monopoly_latest_binding_business_rules(client, auth_header, payload, expected):
    session = BankSqliteSession()
    _use_fake(session)
    try:
        response = await client.post(BASE_URL + "/bank-owner-mismatch", json=payload, headers=auth_header)
    finally:
        _clear_fake()
        session.connection.close()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == len(expected)
    assert {row["lic_no"] for row in body["items"]} == expected
    for row in body["items"]:
        if row["lic_no"] in {"B", "J", "K"}:
            assert row["custbank_uuid"] == row["lic_no"] + "2"


async def test_monopoly_issuing_organization_dictionary(client, auth_header):
    session = BankSqliteSession()
    _use_fake(session)
    try:
        response = await client.get(BASE_URL + "/issuing-organizations", headers=auth_header)
    finally:
        _clear_fake()
        session.connection.close()
    assert response.status_code == 200
    assert {row["issue_org_code"] for row in response.json()} == {"ORG1", "ORG2"}
    assert len(response.json()) == 2
