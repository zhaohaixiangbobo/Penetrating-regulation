"""营销专卖查询：扣款户名核对、拜访签到与许可证经营位置距离核对。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.query import run_all, run_paged
from app.db.starrocks import get_starrocks_session
from app.deps import get_current_user
from app.schemas.common import Paged
from app.schemas.marketing_monopoly import BankOwnerMismatchRequest, BankOwnerMismatchRow, IssuingOrganization
from app.schemas.marketing_monopoly import VisitLocationRequest, VisitLocationRow

router = APIRouter(prefix="/api/marketing-monopoly", tags=["marketing-monopoly"], dependencies=[Depends(get_current_user)])

_ISSUING_ORGS_SQL = """
SELECT issue_org_code, MAX(issue_org_name) AS issue_org_name
FROM r_license_info
WHERE lic_status = '10' AND issue_org_code IS NOT NULL AND TRIM(issue_org_code) <> ''
GROUP BY issue_org_code
ORDER BY issue_org_name, issue_org_code
"""

_SQL_BANK_OWNER_MISMATCH = """
WITH latest_bank AS (
  SELECT custbank_uuid, cust_code, bankcard_owner, sysupdatedt,
    ROW_NUMBER() OVER (
      PARTITION BY cust_code ORDER BY sysupdatedt DESC, custbank_uuid DESC
    ) AS rn
  FROM pc_pay_custbank
)
SELECT lic.retailer_uuid, bank.custbank_uuid,
  lic.issue_org_code, lic.issue_org_name, lic.lic_no, lic.company_name,
  lic.manager_name, bank.bankcard_owner,
  DATE_FORMAT(bank.sysupdatedt, '%Y-%m-%d %H:%i:%s') AS sysupdatedt
FROM r_license_info lic
JOIN latest_bank bank ON lic.lic_no = bank.cust_code AND bank.rn = 1
WHERE lic.lic_status = '10'
  AND TRIM(lic.manager_name) <> TRIM(bank.bankcard_owner)
  AND bank.bankcard_owner IS NOT NULL AND TRIM(bank.bankcard_owner) <> ''
{extra_where}
"""


def build_bank_owner_mismatch_query(payload: BankOwnerMismatchRequest) -> tuple[str, dict[str, Any], str]:
    """先选最新记录，再执行姓名比对和日期筛选，避免历史记录回流。"""
    if (payload.start_date is None) != (payload.end_date is None):
        raise HTTPException(status_code=422, detail="绑定日期的起止日期需同时提供")
    if payload.start_date and payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="结束日期应晚于或等于起始日期")
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if payload.issue_org_codes:
        # 发证机关使用专卖字典，全部值通过绑定参数传入。
        keys = []
        for index, code in enumerate(dict.fromkeys(payload.issue_org_codes)):
            key = f"issue_org_{index}"
            keys.append(f":{key}")
            params[key] = code
        clauses.append(f"AND lic.issue_org_code IN ({', '.join(keys)})")
    if payload.lic_no and payload.lic_no.strip():
        clauses.append("AND lic.lic_no = :lic_no")
        params["lic_no"] = payload.lic_no.strip()
    if payload.company_name and payload.company_name.strip():
        # INSTR 按输入文字查找，百分号和下划线按普通字符处理。
        clauses.append("AND INSTR(lic.company_name, :company_name) > 0")
        params["company_name"] = payload.company_name.strip()
    if payload.start_date:
        clauses.extend([
            "AND bank.sysupdatedt >= :start_date",
            "AND bank.sysupdatedt < DATE_ADD(:end_date, INTERVAL 1 DAY)",
        ])
        params.update(start_date=str(payload.start_date), end_date=str(payload.end_date))
    column = payload.sort_field or "sysupdatedt"
    direction = "ASC" if payload.sort_order == "ascend" else "DESC"
    order_by = f"{column} {direction}, issue_org_code, lic_no, retailer_uuid, custbank_uuid"
    return _SQL_BANK_OWNER_MISMATCH.format(extra_where="\n  ".join(clauses)), params, order_by


@router.get("/issuing-organizations", response_model=list[IssuingOrganization])
async def issuing_organizations(session: AsyncSession = Depends(get_starrocks_session)) -> list[IssuingOrganization]:
    """有效许可证中的发证机关列表，与查询使用相同机关代码。"""
    # 营销专卖各页面统一使用有效许可证中的机关字典。
    rows = (await session.execute(text(_ISSUING_ORGS_SQL))).mappings().all()
    return [IssuingOrganization(issue_org_code=row["issue_org_code"], issue_org_name=row["issue_org_name"] or row["issue_org_code"]) for row in rows]


@router.post("/bank-owner-mismatch", response_model=Paged[BankOwnerMismatchRow])
async def bank_owner_mismatch(
    payload: BankOwnerMismatchRequest, session: AsyncSession = Depends(get_starrocks_session),
) -> Paged[BankOwnerMismatchRow]:
    """查询最新扣款户名与有效许可证持证人姓名不一致的记录。"""
    sql, params, order_by = build_bank_owner_mismatch_query(payload)
    total, rows = await run_paged(session, sql, params, payload.page, payload.page_size, order_by)
    return Paged[BankOwnerMismatchRow](total=total, page=payload.page, page_size=payload.page_size, items=[BankOwnerMismatchRow(**row) for row in rows])


@router.post("/bank-owner-mismatch/export", response_model=list[BankOwnerMismatchRow])
async def bank_owner_mismatch_export(
    payload: BankOwnerMismatchRequest, session: AsyncSession = Depends(get_starrocks_session),
) -> list[BankOwnerMismatchRow]:
    """导出同一筛选和排序下的结果，沿用公共导出行数上限。"""
    sql, params, order_by = build_bank_owner_mismatch_query(payload)
    return [BankOwnerMismatchRow(**row) for row in await run_all(session, sql, params, order_by)]


def build_visit_location_query(payload: VisitLocationRequest) -> tuple[str, dict[str, Any], str]:
    """有效拜访与许可证关联，球面距离按原始米值严格大于阈值筛选。"""
    if payload.start_date.isoformat() < '2024-01-01' or payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail='拜访日期须从2024-01-01起，结束日期应晚于或等于开始日期')
    clauses = []
    params = dict(start_date=str(payload.start_date), end_date=str(payload.end_date), distance_meters=payload.distance_meters)
    for index, code in enumerate(dict.fromkeys(payload.issue_org_codes)):
        params[f'org_{index}'] = code
    if payload.issue_org_codes:
        clauses.append('AND lic.issue_org_code IN (' + ', '.join(f':org_{i}' for i in range(len(set(payload.issue_org_codes)))) + ')')
    if payload.lic_no and payload.lic_no.strip():
        clauses.append('AND a.cust_code = :lic_no')
        params['lic_no'] = payload.lic_no.strip()
    if payload.company_name and payload.company_name.strip():
        clauses.append('AND INSTR(a.cust_name, :company_name) > 0')
        params['company_name'] = payload.company_name.strip()
    sql = """
WITH locations AS (
 SELECT CAST(a.id AS VARCHAR) AS visit_id, lic.retailer_uuid, lic.issue_org_code, lic.issue_org_name, t.person_name,
 DATE_FORMAT(a.plan_date, '%Y-%m-%d') AS plan_date, a.cust_code, a.cust_name,
 lic.longitude, lic.latitude, a.gis_long, a.gis_lat,
 ST_Distance_Sphere(lic.longitude, lic.latitude, a.gis_long, a.gis_lat) AS distance_meters
 FROM crm_mcs_cust_visit_plan a
 LEFT JOIN r_license_info lic ON a.cust_code = lic.lic_no
 LEFT JOIN t_comm_emp_yx t ON a.cust_manager_person_uuid = t.person_uuid
 WHERE a.plan_date >= :start_date AND a.plan_date < DATE_ADD(:end_date, INTERVAL 1 DAY)
 AND a.visit_status = '03' AND a.deleted = '0'
 {filters}
)
SELECT * FROM locations WHERE distance_meters > :distance_meters
""".format(filters='\n'.join(clauses))
    field = payload.sort_field
    direction = 'ASC' if payload.sort_order == 'ascend' else 'DESC'
    order = (f'{field} {direction}, ' if field else '') + 'issue_org_code, person_name, plan_date, cust_code, visit_id, retailer_uuid'
    return sql, params, order


@router.post('/visit-location', response_model=Paged[VisitLocationRow])
async def visit_location(payload: VisitLocationRequest, session: AsyncSession = Depends(get_starrocks_session)):
    """分页查询拜访定位偏差。"""
    sql, params, order = build_visit_location_query(payload)
    total, rows = await run_paged(session, sql, params, payload.page, payload.page_size, order)
    return Paged[VisitLocationRow](total=total, page=payload.page, page_size=payload.page_size, items=[VisitLocationRow(**row) for row in rows])


@router.post('/visit-location/export', response_model=list[VisitLocationRow])
async def visit_location_export(payload: VisitLocationRequest, session: AsyncSession = Depends(get_starrocks_session)):
    """以相同条件导出定位偏差，沿用公共行数上限。"""
    sql, params, order = build_visit_location_query(payload)
    return [VisitLocationRow(**row) for row in await run_all(session, sql, params, order)]
