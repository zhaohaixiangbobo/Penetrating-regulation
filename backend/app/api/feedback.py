"""审计线索反馈接口。

权限模型：
- 提交线索 / 我的线索：登录即可
- 线索详情 / 上传附件 / 下载附件：owner 或 admin
- 全部线索列表 / 处理：仅 admin

附件安全：stored_name 仅服务端 uuid 生成；下载按 clue_id + attachment_id 定位，
校验归属并防路径穿越；一律以下载方式响应（Content-Disposition: attachment）。
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import (APIRouter, Depends, HTTPException, Query, UploadFile,
                     status)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (ALLOWED_UPLOAD_EXTS, CLUE_STATUS_LABELS,
                             MAX_ATTACHMENTS_PER_CLUE, MAX_UPLOAD_MB,
                             UPLOAD_DIR, COMPANIES)
from app.db.sqlite import get_sqlite_session
from app.deps import Principal, get_current_principal, require_admin
from app.models.clue import (AuditClue, AuditClueAttachment,
                             AuditClueHandleLog, beijing_now)
from app.schemas.common import Paged
from app.schemas.feedback import (ClueAttachmentRow, ClueCreateRequest,
                                  ClueDetail, ClueHandleLogRow,
                                  ClueHandleRequest, ClueRow)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# com_id -> 公司简称
_COM_MAP: dict[str, str] = {c["com_id"]: c["short_name"] for c in COMPANIES}


def _status_label(status_code: str) -> str:
    return CLUE_STATUS_LABELS.get(status_code, status_code)


def _to_row(clue: AuditClue, attachment_count: int = 0) -> ClueRow:
    return ClueRow(
        id=clue.id,
        title=clue.title,
        category=clue.category,
        com_id=clue.com_id,
        short_name=_COM_MAP.get(clue.com_id or "", None),
        involved_dept=clue.involved_dept,
        involved_manager=clue.involved_manager,
        involved_customer=clue.involved_customer,
        status=clue.status,
        status_label=_status_label(clue.status),
        created_by=clue.created_by,
        created_at=clue.created_at,
        updated_at=clue.updated_at,
        handled_by=clue.handled_by,
        handled_at=clue.handled_at,
        attachment_count=attachment_count,
    )


def _ensure_can_access(clue: AuditClue, principal: Principal) -> None:
    """owner 或 admin 才能访问；否则 403。"""
    if principal.is_admin or clue.created_by == principal.username:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该线索")


async def _get_clue_or_404(session: AsyncSession, clue_id: int) -> AuditClue:
    clue = (await session.execute(
        select(AuditClue).where(AuditClue.id == clue_id))).scalar_one_or_none()
    if clue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="线索不存在")
    return clue


async def _count_map(session: AsyncSession, clue_ids: list[int]) -> dict[int, int]:
    """批量统计每条线索的附件数量。"""
    if not clue_ids:
        return {}
    rows = (await session.execute(
        select(AuditClueAttachment.clue_id, func.count(AuditClueAttachment.id))
        .where(AuditClueAttachment.clue_id.in_(clue_ids))
        .group_by(AuditClueAttachment.clue_id))).all()
    return {cid: cnt for cid, cnt in rows}


# ---------------------------------------------------------------------------
# 提交 / 我的线索（登录）
# ---------------------------------------------------------------------------
@router.post("/clues", response_model=ClueDetail)
async def create_clue(
    payload: ClueCreateRequest,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_sqlite_session),
) -> ClueDetail:
    clue = AuditClue(
        title=payload.title,
        category=payload.category,
        com_id=payload.com_id,
        involved_dept=payload.involved_dept,
        involved_manager=payload.involved_manager,
        involved_customer=payload.involved_customer,
        content=payload.content,
        status="pending",
        created_by=principal.username,
    )
    session.add(clue)
    await session.commit()
    await session.refresh(clue)
    detail = _to_row(clue).model_dump()
    detail.update(content=clue.content, handle_remark=None,
                  attachments=[], handle_logs=[])
    return ClueDetail(**detail)


# 注意：静态路径 /clues/mine 必须在动态 /clues/{clue_id} 之前声明
@router.get("/clues/mine", response_model=Paged[ClueRow])
async def list_my_clues(
    status_filter: str | None = Query(None, alias="status"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_sqlite_session),
) -> Paged[ClueRow]:
    conds = [AuditClue.created_by == principal.username]
    if status_filter:
        conds.append(AuditClue.status == status_filter)

    total = (await session.execute(
        select(func.count(AuditClue.id)).where(*conds))).scalar_one()
    rows = (await session.execute(
        select(AuditClue).where(*conds)
        .order_by(AuditClue.created_at.asc() if order == "asc" else AuditClue.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    counts = await _count_map(session, [c.id for c in rows])
    items = [_to_row(c, counts.get(c.id, 0)) for c in rows]
    return Paged[ClueRow](total=total, page=page, page_size=page_size, items=items)


# ---------------------------------------------------------------------------
# 全部线索（admin）
# ---------------------------------------------------------------------------
@router.get("/clues", response_model=Paged[ClueRow])
async def list_all_clues(
    status_filter: str | None = Query(None, alias="status"),
    com_id: str | None = Query(None),
    created_by: str | None = Query(None),
    keyword: str | None = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_sqlite_session),
) -> Paged[ClueRow]:
    conds = []
    if status_filter:
        conds.append(AuditClue.status == status_filter)
    if com_id:
        conds.append(AuditClue.com_id == com_id)
    if created_by:
        conds.append(AuditClue.created_by == created_by)
    if keyword:
        like = f"%{keyword}%"
        conds.append(AuditClue.title.like(like) | AuditClue.content.like(like))

    total = (await session.execute(
        select(func.count(AuditClue.id)).where(*conds))).scalar_one()
    rows = (await session.execute(
        select(AuditClue).where(*conds)
        .order_by(AuditClue.created_at.asc() if order == "asc" else AuditClue.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    counts = await _count_map(session, [c.id for c in rows])
    items = [_to_row(c, counts.get(c.id, 0)) for c in rows]
    return Paged[ClueRow](total=total, page=page, page_size=page_size, items=items)


# ---------------------------------------------------------------------------
# 详情（owner / admin）
# ---------------------------------------------------------------------------
@router.get("/clues/{clue_id}", response_model=ClueDetail)
async def get_clue(
    clue_id: int,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_sqlite_session),
) -> ClueDetail:
    clue = await _get_clue_or_404(session, clue_id)
    _ensure_can_access(clue, principal)

    atts = (await session.execute(
        select(AuditClueAttachment).where(AuditClueAttachment.clue_id == clue_id)
        .order_by(AuditClueAttachment.created_at.asc()))).scalars().all()
    logs = (await session.execute(
        select(AuditClueHandleLog).where(AuditClueHandleLog.clue_id == clue_id)
        .order_by(AuditClueHandleLog.created_at.asc()))).scalars().all()

    detail = _to_row(clue, len(atts)).model_dump()
    detail.update(
        content=clue.content,
        handle_remark=clue.handle_remark,
        attachments=[ClueAttachmentRow.model_validate(a) for a in atts],
        handle_logs=[ClueHandleLogRow.model_validate(l) for l in logs],
    )
    return ClueDetail(**detail)


# ---------------------------------------------------------------------------
# 处理（admin）：状态流转 + 处理记录留痕
# ---------------------------------------------------------------------------
@router.patch("/clues/{clue_id}/handle", response_model=ClueDetail)
async def handle_clue(
    clue_id: int,
    payload: ClueHandleRequest,
    principal: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_sqlite_session),
) -> ClueDetail:
    clue = await _get_clue_or_404(session, clue_id)
    from_status = clue.status
    now = beijing_now()

    clue.status = payload.status
    clue.handle_remark = payload.handle_remark
    clue.handled_by = principal.username
    # handled_at 仅在真正完成（done）时写；离开 done 则清空
    clue.handled_at = now if payload.status == "done" else None

    session.add(AuditClueHandleLog(
        clue_id=clue_id,
        from_status=from_status,
        to_status=payload.status,
        remark=payload.handle_remark,
        handled_by=principal.username,
        created_at=now,
    ))
    await session.commit()
    await session.refresh(clue)

    atts = (await session.execute(
        select(AuditClueAttachment).where(AuditClueAttachment.clue_id == clue_id)
        .order_by(AuditClueAttachment.created_at.asc()))).scalars().all()
    logs = (await session.execute(
        select(AuditClueHandleLog).where(AuditClueHandleLog.clue_id == clue_id)
        .order_by(AuditClueHandleLog.created_at.asc()))).scalars().all()
    detail = _to_row(clue, len(atts)).model_dump()
    detail.update(
        content=clue.content,
        handle_remark=clue.handle_remark,
        attachments=[ClueAttachmentRow.model_validate(a) for a in atts],
        handle_logs=[ClueHandleLogRow.model_validate(l) for l in logs],
    )
    return ClueDetail(**detail)


# ---------------------------------------------------------------------------
# 附件：上传 / 下载（owner / admin）
# ---------------------------------------------------------------------------
@router.post("/clues/{clue_id}/attachments", response_model=ClueAttachmentRow)
async def upload_attachment(
    clue_id: int,
    file: UploadFile,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_sqlite_session),
) -> ClueAttachmentRow:
    clue = await _get_clue_or_404(session, clue_id)
    _ensure_can_access(clue, principal)

    # 数量上限
    existing = (await session.execute(
        select(func.count(AuditClueAttachment.id))
        .where(AuditClueAttachment.clue_id == clue_id))).scalar_one()
    if existing >= MAX_ATTACHMENTS_PER_CLUE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"单条线索最多上传 {MAX_ATTACHMENTS_PER_CLUE} 个附件")

    # 扩展名白名单
    original_name = file.filename or "attachment"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"不支持的文件类型: {ext or '无扩展名'}")

    # 分块写盘 + 大小限制
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / stored_name
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"附件超过 {MAX_UPLOAD_MB}MB 上限")
                f.write(chunk)
    finally:
        await file.close()

    att = AuditClueAttachment(
        clue_id=clue_id,
        original_name=original_name,
        stored_name=stored_name,
        size=size,
        content_type=file.content_type,
        uploaded_by=principal.username,
    )
    session.add(att)
    await session.commit()
    await session.refresh(att)
    return ClueAttachmentRow.model_validate(att)


@router.get("/clues/{clue_id}/attachments/{attachment_id}")
async def download_attachment(
    clue_id: int,
    attachment_id: int,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_sqlite_session),
) -> FileResponse:
    clue = await _get_clue_or_404(session, clue_id)
    _ensure_can_access(clue, principal)

    att = (await session.execute(
        select(AuditClueAttachment).where(
            AuditClueAttachment.id == attachment_id,
            AuditClueAttachment.clue_id == clue_id))).scalar_one_or_none()
    if att is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")

    # 防路径穿越：只用 DB 中服务端生成的 stored_name，并校验最终路径仍在 UPLOAD_DIR 下
    base = UPLOAD_DIR.resolve()
    target = (base / att.stored_name).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="附件文件缺失")

    return FileResponse(
        path=str(target),
        media_type=att.content_type or "application/octet-stream",
        filename=att.original_name,
        content_disposition_type="attachment",
    )
