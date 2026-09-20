"""审计线索反馈接口测试。

覆盖：提交、我的线索、管理员列表、鉴权隔离、处理流转+留痕、
附件上传/下载、附件越权、路径与类型校验。
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.api import feedback as feedback_api


@pytest.fixture(autouse=True)
def _isolate_upload_dir(tmp_path, monkeypatch):
    """把附件目录指向临时目录，避免污染 backend/data。"""
    monkeypatch.setattr(feedback_api, "UPLOAD_DIR", tmp_path / "uploads")


async def _create_clue(client: AsyncClient, header: dict, **overrides) -> dict:
    payload = {
        "title": "测试线索",
        "category": "拜访异常",
        "content": "这是一条测试线索内容",
    }
    payload.update(overrides)
    resp = await client.post("/api/feedback/clues", json=payload, headers=header)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_and_mine(client: AsyncClient, user_header: dict):
    created = await _create_clue(client, user_header, title="我的线索A")
    assert created["status"] == "pending"
    assert created["created_by"] == "user1"

    resp = await client.get("/api/feedback/clues/mine", headers=user_header)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert any(item["title"] == "我的线索A" for item in body["items"])


@pytest.mark.asyncio
async def test_create_invalid_category(client: AsyncClient, user_header: dict):
    resp = await client.post(
        "/api/feedback/clues",
        json={"title": "x", "category": "不存在类型", "content": "y"},
        headers=user_header,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_com_id(client: AsyncClient, user_header: dict):
    resp = await client.post(
        "/api/feedback/clues",
        json={"title": "x", "category": "其他", "content": "y", "com_id": "999999"},
        headers=user_header,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_all_requires_admin(client: AsyncClient, user_header: dict):
    resp = await client.get("/api/feedback/clues", headers=user_header)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_all(client: AsyncClient, user_header: dict, admin_header: dict):
    await _create_clue(client, user_header, title="给管理员看的线索")
    resp = await client.get("/api/feedback/clues", headers=admin_header)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_detail_access_control(client: AsyncClient, user_header: dict, admin_header: dict):
    created = await _create_clue(client, user_header)
    cid = created["id"]

    # owner 可看
    r1 = await client.get(f"/api/feedback/clues/{cid}", headers=user_header)
    assert r1.status_code == 200
    # admin 可看
    r2 = await client.get(f"/api/feedback/clues/{cid}", headers=admin_header)
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_other_user_cannot_access(client: AsyncClient, user_header: dict, admin_header: dict):
    # admin 创建一条线索，user1 不应看到详情
    created = await _create_clue(client, admin_header, title="管理员私有线索")
    cid = created["id"]
    resp = await client.get(f"/api/feedback/clues/{cid}", headers=user_header)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_handle_flow_and_logs(client: AsyncClient, user_header: dict, admin_header: dict):
    created = await _create_clue(client, user_header)
    cid = created["id"]

    # 普通用户不能处理
    r_forbidden = await client.patch(
        f"/api/feedback/clues/{cid}/handle",
        json={"status": "processing"},
        headers=user_header,
    )
    assert r_forbidden.status_code == 403

    # admin 置为处理中
    r1 = await client.patch(
        f"/api/feedback/clues/{cid}/handle",
        json={"status": "processing", "handle_remark": "已受理"},
        headers=admin_header,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "processing"
    assert r1.json()["handled_at"] is None  # 非 done 不写 handled_at

    # admin 置为已处理
    r2 = await client.patch(
        f"/api/feedback/clues/{cid}/handle",
        json={"status": "done", "handle_remark": "已核实并处理"},
        headers=admin_header,
    )
    assert r2.status_code == 200, r2.text
    detail = r2.json()
    assert detail["status"] == "done"
    assert detail["handled_at"] is not None
    assert detail["handled_by"] == "admin"
    # 两次处理都留痕
    assert len(detail["handle_logs"]) == 2

    # 再次离开 done，handled_at 应清空
    r3 = await client.patch(
        f"/api/feedback/clues/{cid}/handle",
        json={"status": "pending"},
        headers=admin_header,
    )
    assert r3.json()["handled_at"] is None
    assert len(r3.json()["handle_logs"]) == 3


@pytest.mark.asyncio
async def test_attachment_upload_download(client: AsyncClient, user_header: dict):
    created = await _create_clue(client, user_header)
    cid = created["id"]

    files = {"file": ("note.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    up = await client.post(
        f"/api/feedback/clues/{cid}/attachments", files=files, headers=user_header)
    assert up.status_code == 200, up.text
    att_id = up.json()["id"]
    assert up.json()["original_name"] == "note.pdf"

    # 详情中附件计数
    detail = (await client.get(f"/api/feedback/clues/{cid}", headers=user_header)).json()
    assert detail["attachment_count"] == 1
    assert len(detail["attachments"]) == 1

    # 下载
    dl = await client.get(
        f"/api/feedback/clues/{cid}/attachments/{att_id}", headers=user_header)
    assert dl.status_code == 200
    assert dl.content == b"%PDF-1.4 fake"
    assert "attachment" in dl.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_attachment_reject_bad_ext(client: AsyncClient, user_header: dict):
    created = await _create_clue(client, user_header)
    cid = created["id"]
    files = {"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    resp = await client.post(
        f"/api/feedback/clues/{cid}/attachments", files=files, headers=user_header)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_attachment_download_forbidden_for_others(
    client: AsyncClient, user_header: dict, admin_header: dict
):
    # admin 建线索并上传附件，user1 不能下载
    created = await _create_clue(client, admin_header)
    cid = created["id"]
    files = {"file": ("a.png", io.BytesIO(b"\x89PNG fake"), "image/png")}
    up = await client.post(
        f"/api/feedback/clues/{cid}/attachments", files=files, headers=admin_header)
    att_id = up.json()["id"]

    resp = await client.get(
        f"/api/feedback/clues/{cid}/attachments/{att_id}", headers=user_header)
    assert resp.status_code == 403
