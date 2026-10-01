"""营销专卖模块契约：扣款户名比对、拜访定位偏差及机关字典。"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class BankOwnerMismatchRequest(BaseModel):
    """发证机关可多选；全部筛选为空时查询当前全部不符记录。"""

    issue_org_codes: list[Annotated[str, Field(min_length=1, max_length=32)]] = Field(default_factory=list, max_length=100)
    lic_no: str | None = Field(None, max_length=20, description="许可证号精确查询")
    company_name: str | None = Field(None, max_length=100, description="客户名称包含查询")
    start_date: date | None = Field(None, description="最新绑定日期起点，含当天")
    end_date: date | None = Field(None, description="最新绑定日期终点，含当天")
    sort_field: Literal["sysupdatedt", "lic_no", "issue_org_name"] | None = None
    sort_order: Literal["ascend", "descend"] | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=200)


class BankOwnerMismatchRow(BaseModel):
    """保留源记录标识用于稳定排序，页面仅展示业务字段。"""

    retailer_uuid: str | None = None
    custbank_uuid: str | None = None
    issue_org_code: str | None = None
    issue_org_name: str | None = None
    lic_no: str | None = None
    company_name: str | None = None
    manager_name: str | None = None
    bankcard_owner: str | None = None
    sysupdatedt: str | None = None


class IssuingOrganization(BaseModel):
    issue_org_code: str
    issue_org_name: str


class VisitLocationRequest(BankOwnerMismatchRequest):
    """拜访位置距离查询，按米设置阈值，日期范围必填。"""

    start_date: date
    end_date: date
    distance_meters: int = Field(200, ge=1, le=100000)
    sort_field: Literal['plan_date', 'distance_meters', 'issue_org_name'] | None = None


class VisitLocationRow(BaseModel):
    """许可证经营位置与营销签到位置及球面距离。"""

    visit_id: str | None = None
    retailer_uuid: str | None = None

    issue_org_code: str | None = None
    issue_org_name: str | None = None
    person_name: str | None = None
    plan_date: str
    cust_code: str | None = None
    cust_name: str | None = None
    longitude: float
    latitude: float
    gis_long: float
    gis_lat: float
    distance_meters: float
