"""登录与鉴权相关测试。"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_login_success(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "tjyc!2026"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"
    assert body["access_token"]
    assert body["token_type"] == "bearer"


async def test_login_wrong_password(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


async def test_login_unknown_user(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert resp.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_ok(client: AsyncClient, auth_header: dict[str, str]) -> None:
    resp = await client.get("/api/auth/me", headers=auth_header)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"
    # 角色随 /me 一并返回（conftest 建的 admin 未显式设角色，取默认 user）
    assert body["role"] in {"admin", "user"}


async def test_bad_token(client: AsyncClient) -> None:
    resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


async def test_companies_requires_token(client: AsyncClient) -> None:
    resp = await client.get("/api/meta/companies")
    assert resp.status_code == 401


async def test_companies_ok(client: AsyncClient, auth_header: dict[str, str]) -> None:
    resp = await client.get("/api/meta/companies", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 13
    assert {c["com_id"] for c in data} >= {"11120101", "11120203"}
