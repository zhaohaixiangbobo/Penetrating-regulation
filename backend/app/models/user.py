"""本地登录账号模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.sqlite import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 角色：admin / user（默认普通用户），用于权限划分
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user", server_default="user")
    # 4A/OIDC 预留：外部统一身份平台的唯一账号 ID，用于本地账号与 4A 账号映射
    external_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False)
