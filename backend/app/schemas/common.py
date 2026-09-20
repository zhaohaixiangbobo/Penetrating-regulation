"""Pydantic Schemas。"""
from __future__ import annotations

from datetime import date
from typing import Generic, List, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str = "user"


class MeResponse(BaseModel):
    username: str
    role: str = "user"


class CompanyItem(BaseModel):
    com_id: str
    short_name: str


class AuditQueryRequest(BaseModel):
    """功能 1 / 功能 3 查询参数。"""

    com_ids: list[str] = Field(..., description="公司代码列表（支持多选）")
    start_date: date = Field(..., description="起始日期（含）")
    end_date: date = Field(..., description="结束日期（含）")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=200)


class DailyUnderHourRequest(AuditQueryRequest):
    """功能 3 查询参数，扩展可选的营业部/客户经理过滤与排序。"""

    sdpt_name: str | None = Field(None, description="营业部名称（可选）")
    person_uuid: str | None = Field(None, description="客户经理 UUID（可选）")
    sort_field: str | None = Field(None, description="排序字段：v_date")
    sort_order: str | None = Field(None, description="排序方向：ascend / descend")


class ShortVisitQueryRequest(AuditQueryRequest):
    """功能 1 查询参数，扩展客户经理筛选与排序。"""

    person_name: str | None = Field(None, description="客户经理姓名（可选，模糊匹配）")
    sort_field: str | None = Field(
        None, description="排序字段：plan_date / visit_time")
    sort_order: str | None = Field(None, description="排序方向：ascend / descend")


class MonthlyQueryRequest(BaseModel):
    """功能 2 查询参数（按月）。"""

    com_ids: list[str] = Field(..., description="公司代码列表（支持多选）")
    start_month: date = Field(...,
                              description="起始月份 (YYYY-MM-01)，最早 2025-02-01")
    end_month: date = Field(..., description="结束月份 (YYYY-MM-01)")
    sdpt_name: str | None = Field(None, description="营业部名称（可选）")
    person_uuid: str | None = Field(None, description="客户经理 UUID（可选）")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=200)
    sort_field: str | None = Field(None, description="排序字段：year_month")
    sort_order: str | None = Field(None, description="排序方向：ascend / descend")


class ShortVisitRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    com_id: str | None = None
    short_name: str | None = None
    license_code: str | None = None
    cust_name: str | None = None
    sdpt_name: str | None = None
    person_name: str | None = None
    plan_date: str | None = None
    visit_time: int | None = None


class FullCustMissRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year_month: str | None = None
    short_name: str | None = None
    cust_code: str | None = None
    cust_name: str | None = None
    sdpt_name: str | None = None
    person_name: str | None = None


class DailyUnderHourRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    v_date: str | None = None
    com_id: str | None = None
    short_name: str | None = None
    sdpt_name: str | None = None
    cust_manager_person_uuid: str | None = None
    person_name: str | None = None
    visit_minutes: float | None = None


class EmployeeMember(BaseModel):
    person_uuid: str
    person_name: str


class EmployeeGroup(BaseModel):
    sdpt_name: str
    members: list[EmployeeMember]


class Paged(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: List[T]
