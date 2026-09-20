"""审计线索反馈相关 Pydantic Schemas。

Paged 泛型继续从 common.py 复用，本文件只放线索反馈专属模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import CLUE_CATEGORIES, VALID_COM_IDS

# 线索类型 / 状态字面量（与 config 常量保持一致）
CategoryLiteral = Literal["拜访异常", "资料造假", "违规经营", "其他"]
StatusLiteral = Literal["pending", "processing", "done"]


class ClueCreateRequest(BaseModel):
    """普通用户/管理员提交线索的请求体。"""

    title: str = Field(..., min_length=1, max_length=200)
    category: CategoryLiteral
    com_id: Optional[str] = Field(None, max_length=16)
    involved_dept: Optional[str] = Field(None, max_length=200)
    involved_manager: Optional[str] = Field(None, max_length=200)
    involved_customer: Optional[str] = Field(None, max_length=200)
    content: str = Field(..., min_length=1, max_length=10000)

    @field_validator("com_id")
    @classmethod
    def _check_com_id(cls, v: Optional[str]) -> Optional[str]:
        # 允许为空；非空时必须命中公司白名单
        if v in (None, ""):
            return None
        if v not in VALID_COM_IDS:
            raise ValueError(f"非法公司代码: {v}")
        return v

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        if v not in CLUE_CATEGORIES:
            raise ValueError(f"非法线索类型: {v}")
        return v


class ClueHandleRequest(BaseModel):
    """管理员处理线索的请求体。"""

    status: StatusLiteral
    handle_remark: Optional[str] = Field(None, max_length=5000)


class ClueAttachmentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_name: str
    size: int
    content_type: Optional[str] = None
    uploaded_by: str
    created_at: datetime


class ClueHandleLogRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: Optional[str] = None
    to_status: str
    remark: Optional[str] = None
    handled_by: str
    created_at: datetime


class ClueRow(BaseModel):
    """线索列表行（不含附件与处理记录明细）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    com_id: Optional[str] = None
    short_name: Optional[str] = None
    involved_dept: Optional[str] = None
    involved_manager: Optional[str] = None
    involved_customer: Optional[str] = None
    status: str
    status_label: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    handled_by: Optional[str] = None
    handled_at: Optional[datetime] = None
    attachment_count: int = 0


class ClueDetail(ClueRow):
    """线索详情：在列表行基础上补充全文、附件与处理记录。"""

    content: str
    handle_remark: Optional[str] = None
    attachments: list[ClueAttachmentRow] = Field(default_factory=list)
    handle_logs: list[ClueHandleLogRow] = Field(default_factory=list)
