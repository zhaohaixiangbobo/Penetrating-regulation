"""审计线索反馈相关数据模型（本地 SQLite）。

三张轻量表：
- audit_clues              线索主表（含当前最新处理状态与意见）
- audit_clue_attachments   线索附件表（与线索强绑定，权限随线索）
- audit_clue_handle_logs   处理历史留痕表（每次处理 INSERT，不覆盖历史）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.sqlite import Base

# 统一使用北京时间（UTC+8）存储 naive datetime，避免前端按字符串展示时慢 8 小时
_BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    """返回当前北京时间（去掉时区信息的 naive datetime）。"""
    return datetime.now(_BEIJING_TZ).replace(tzinfo=None)


class AuditClue(Base):
    """审计线索主表。"""

    __tablename__ = "audit_clues"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # 关联公司代码（可空），建索引便于按公司过滤
    com_id: Mapped[str | None] = mapped_column(
        String(16), index=True, nullable=True)
    involved_dept: Mapped[str | None] = mapped_column(
        String(200), nullable=True)
    involved_manager: Mapped[str | None] = mapped_column(
        String(200), nullable=True)
    involved_customer: Mapped[str | None] = mapped_column(
        String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 当前状态：pending / processing / done
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
        server_default="pending", index=True)
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=beijing_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=beijing_now, onupdate=beijing_now, nullable=False)
    # 当前最新处理意见（历史留痕见 audit_clue_handle_logs）
    handle_remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    handled_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 仅 status=done 时有值（离开 done 置空）
    handled_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)


class AuditClueAttachment(Base):
    """线索附件表：附件与线索强绑定，下载权限随线索（owner/admin）。"""

    __tablename__ = "audit_clue_attachments"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    clue_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # 原始文件名（仅用于展示与下载时的文件名）
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 服务端生成的实际存储文件名（uuid + 安全扩展名），客户端永不指定
    stored_name: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str | None] = mapped_column(
        String(128), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=beijing_now, nullable=False)


class AuditClueHandleLog(Base):
    """处理历史留痕表：管理员每次处理 INSERT 一条，不修改历史。"""

    __tablename__ = "audit_clue_handle_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    clue_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    handled_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=beijing_now, nullable=False)
