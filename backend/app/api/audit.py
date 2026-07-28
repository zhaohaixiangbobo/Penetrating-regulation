"""审计查询接口：3 个基于 StarRocks 的查询。

所有查询：
- com_ids 已白名单校验，IN 子句安全拼接
- 分页：外层 LIMIT/OFFSET；用子查询算 COUNT
- start_date/end_date 为 date 类型，结束日期做 +1 天处理确保全天覆盖
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import VALID_COM_IDS
from app.db.starrocks import get_starrocks_session
from app.deps import get_current_user
from app.schemas.common import (
    AuditQueryRequest,
    DailyUnderHourRequest,
    DailyUnderHourRow,
    FullCustMissRow,
    MonthlyQueryRequest,
    Paged,
    ShortVisitQueryRequest,
    ShortVisitRow,
)

router = APIRouter(prefix="/api/audit",
                   tags=["audit"], dependencies=[Depends(get_current_user)])


# ============ 辅助工具 ============

MIN_DATE = date(2024, 1, 1)
MIN_MONTH = date(2025, 2, 1)


def _validate_com_ids(ids: Sequence[str]) -> None:
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="至少选择一个公司")
    invalid = [i for i in ids if i not in VALID_COM_IDS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"非法公司代码: {invalid}")


def _safe_in(ids: Sequence[str]) -> str:
    """构造 SQL IN 括号内容（ids 已通过白名单校验，安全拼接）。"""
    return ", ".join(f"'{i}'" for i in ids)


def _validate_date_range(start: date, end: date, floor: date = MIN_DATE) -> None:
    if start < floor:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"起始日期不能早于 {floor.isoformat()}",
        )
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="结束日期必须晚于起始日期")


def _validate_month_range(start: date, end: date, floor: date = MIN_MONTH) -> None:
    if start < floor:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"起始月份不能早于 {floor.isoformat()}",
        )
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="结束月份必须晚于起始月份")


def build_paged_sql(inner_sql: str, order_by: str | None = None) -> tuple[str, str]:
    """将业务 SQL 包一层用于计数 + 一层用于分页。"""
    count_sql = f"SELECT count(*) AS c FROM (\n{inner_sql}\n) _t"
    order_clause = f"\nORDER BY {order_by}" if order_by else ""
    data_sql = f"SELECT * FROM (\n{inner_sql}\n) _t{order_clause}\nLIMIT :limit OFFSET :offset"
    return count_sql, data_sql


async def _run_paged(
    session: AsyncSession,
    inner_sql: str,
    params: dict[str, Any],
    page: int,
    page_size: int,
    order_by: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    count_sql, data_sql = build_paged_sql(inner_sql, order_by=order_by)
    limit = page_size
    offset = (page - 1) * page_size

    total_row = (await session.execute(text(count_sql), params)).first()
    total = int(total_row[0]) if total_row and total_row[0] is not None else 0

    rows = (await session.execute(text(data_sql), {**params, "limit": limit, "offset": offset})).mappings().all()
    return total, [dict(r) for r in rows]


# ============ 功能 1 SQL ============

_SQL_SHORT_VISIT_TMPL = """
SELECT
  com_id,
  short_name,
  license_code,
  cust_name,
  sdpt_name,
  person_name,
  DATE_FORMAT(plan_date, '%Y-%m-%d') AS plan_date,
  visit_time
FROM crm_mcs_cust_visit_plan a
LEFT JOIN t_comm_emp_yx t ON a.cust_manager_person_uuid = t.person_uuid
WHERE plan_date >= :start_date
  AND plan_date < DATE_ADD(:end_date, INTERVAL 1 DAY)
  AND visit_status = '03'
  AND deleted = '0'
  AND visit_time < 60
  AND com_id IN ({com_id_in}){extra_where}
"""


# ============ 功能 2 SQL ============
# 依据 database.md 最新版本：
# - 客户经理直接取自评价客户表的 customer_manager_person_id（评价时点归属，无需窗口函数回溯）
# - 公司/营业部/姓名来自经理所属的 t_comm_employee
# - list 限制 a.status = '3'（已生效评价）且 y_m >= 起始月份（减少扫描）
# - 月份标识与范围过滤均基于 y_m（评价月份），而非 sysupdatedate（记录更新时间）
#   sysupdatedate 是最后修改时间，与评价归属月份不一致，用它过滤会丢失早期评价记录

_SQL_FULL_CUST_MISS_TMPL = """
WITH bf AS (
  SELECT cust_uuid, DATE_FORMAT(plan_date, '%Y-%m-01') AS op_month, count(*) AS sl
  FROM crm_mcs_cust_visit_plan
  WHERE plan_date >= :start_month
    AND plan_date < DATE_ADD(:end_month, INTERVAL 1 MONTH)
    AND visit_status = '03'
    AND deleted = '0'
  GROUP BY cust_uuid, DATE_FORMAT(plan_date, '%Y-%m-01')
),
list AS (
  SELECT
    REPLACE(y_m, '-', '') AS year_month,
    cust_uuid,
    cust_code,
    cust_name,
    customer_manager_person_id AS mgr_id,
    CONCAT(y_m, '-01') AS sqdate
  FROM uc_evaluation_m a
  LEFT JOIN uc_evaluation_m_cust b ON a.evaluation_m_uuid = b.evaluation_m_uuid
  LEFT JOIN kc_customer_yz c ON b.cust_uuid = c.id
  WHERE evaluation_type_adj = '04'
    AND a.status = '3'
    AND y_m >= :start_ym
),
zh AS (
  SELECT
    d.com_id,
    d.short_name,
    list.cust_uuid,
    cust_code,
    cust_name,
    mgr_id,
    sqdate,
    year_month,
    d.sdpt_name,
    d.person_name,
    coalesce(sl, 0) AS sl
  FROM list
  LEFT JOIN bf ON list.cust_uuid = bf.cust_uuid AND list.sqdate = bf.op_month
  LEFT JOIN t_comm_employee d ON list.mgr_id = d.person_uuid
)
SELECT DISTINCT year_month, short_name, sdpt_name, person_name, cust_code, cust_name
FROM zh
WHERE sl = 0
  AND com_id IN ({com_id_in})
  AND sqdate >= :start_month
  AND sqdate < DATE_ADD(:end_month, INTERVAL 1 MONTH){extra_where}
"""


# ============ 功能 3 SQL 模板 ============
# {com_id_in}  安全 IN 子句（白名单校验后拼接）
# {extra_where} 可选追加的 AND 子句（营业部/客户经理过滤）

_SQL_DAILY_UNDER_HOUR_TMPL = """
SELECT
  substr(plan_date, 1, 10) AS v_date,
  com_id,
  short_name,
  sdpt_name,
  cust_manager_person_uuid,
  person_name,
  sum(visit_time) AS tot
FROM crm_mcs_cust_visit_plan cms
LEFT JOIN t_comm_emp_yx emp ON cms.cust_manager_person_uuid = emp.person_uuid
WHERE plan_date >= :start_date
  AND plan_date < DATE_ADD(:end_date, INTERVAL 1 DAY)
  AND visit_status = '03'
  AND deleted = '0'
  AND com_id IN ({com_id_in}){extra_where}
GROUP BY
  substr(plan_date, 1, 10),
  com_id,
  short_name,
  sdpt_name,
  cust_manager_person_uuid,
  person_name
HAVING sum(visit_time) < 3600
"""


# ============ 接口实现 ============


# 功能 1 排序字段白名单（防 SQL 注入）
_SHORT_VISIT_SORT_FIELDS = {"plan_date", "visit_time"}

# 功能 2 / 功能 3 排序字段白名单
_FULL_CUST_MISS_SORT_FIELDS = {"year_month"}
_DAILY_UNDER_HOUR_SORT_FIELDS = {"v_date"}

# 导出行数上限（防止一次性拉取过大结果集）
EXPORT_ROW_LIMIT = 100000


async def _run_all(
    session: AsyncSession,
    inner_sql: str,
    params: dict[str, Any],
    order_by: str | None = None,
    limit: int = EXPORT_ROW_LIMIT,
) -> list[dict[str, Any]]:
    """导出用：不分页，直接取全部结果（带安全上限）。"""
    order_clause = f"\nORDER BY {order_by}" if order_by else ""
    data_sql = f"SELECT * FROM (\n{inner_sql}\n) _t{order_clause}\nLIMIT :export_limit"
    rows = (await session.execute(text(data_sql), {**params, "export_limit": limit})).mappings().all()
    return [dict(r) for r in rows]


# ---------- SQL 构建器（分页查询与导出共用） ----------


def _build_short_visit_query(payload: ShortVisitQueryRequest) -> tuple[str, dict[str, Any], str]:
    _validate_com_ids(payload.com_ids)
    _validate_date_range(payload.start_date, payload.end_date)

    # 可选：客户经理姓名模糊筛选
    extra_where = ""
    extra_params: dict[str, Any] = {}
    if payload.person_name:
        extra_where += "\n  AND t.person_name LIKE :person_name"
        extra_params["person_name"] = f"%{payload.person_name}%"

    # 动态排序（白名单校验），默认按拜访日期倒序
    order_by = "plan_date DESC, license_code"
    if payload.sort_field in _SHORT_VISIT_SORT_FIELDS:
        direction = "DESC" if payload.sort_order == "descend" else "ASC"
        order_by = f"{payload.sort_field} {direction}"

    sql = _SQL_SHORT_VISIT_TMPL.format(
        com_id_in=_safe_in(payload.com_ids),
        extra_where=extra_where,
    )
    params = {
        "start_date": str(payload.start_date),
        "end_date": str(payload.end_date),
        **extra_params,
    }
    return sql, params, order_by


def _build_full_cust_miss_query(payload: MonthlyQueryRequest) -> tuple[str, dict[str, Any], str]:
    _validate_com_ids(payload.com_ids)
    _validate_month_range(payload.start_month, payload.end_month)

    # 可选：营业部 / 客户经理过滤（基于评价时点的客户归属经理）
    extra_where = ""
    extra_params: dict[str, Any] = {}
    if payload.sdpt_name:
        extra_where += "\n  AND sdpt_name = :sdpt_name"
        extra_params["sdpt_name"] = payload.sdpt_name
    if payload.person_uuid:
        extra_where += "\n  AND mgr_id = :person_uuid"
        extra_params["person_uuid"] = payload.person_uuid

    # 动态排序（白名单校验），默认按月份升序
    order_by = "year_month, cust_code"
    if payload.sort_field in _FULL_CUST_MISS_SORT_FIELDS:
        direction = "DESC" if payload.sort_order == "descend" else "ASC"
        order_by = f"{payload.sort_field} {direction}, cust_code"

    sql = _SQL_FULL_CUST_MISS_TMPL.format(
        com_id_in=_safe_in(payload.com_ids),
        extra_where=extra_where,
    )
    params = {
        "start_month": str(payload.start_month),
        "end_month": str(payload.end_month),
        # y_m 为 'YYYY-MM' 字符串列，用于减少评价表扫描范围
        "start_ym": payload.start_month.strftime("%Y-%m"),
        **extra_params,
    }
    return sql, params, order_by


def _build_daily_under_hour_query(payload: DailyUnderHourRequest) -> tuple[str, dict[str, Any], str]:
    _validate_com_ids(payload.com_ids)
    _validate_date_range(payload.start_date, payload.end_date)

    # 构建可选过滤子句（营业部 / 客户经理）
    extra_where = ""
    extra_params: dict[str, Any] = {}
    if payload.sdpt_name:
        extra_where += "\n  AND sdpt_name = :sdpt_name"
        extra_params["sdpt_name"] = payload.sdpt_name
    if payload.person_uuid:
        extra_where += "\n  AND cms.cust_manager_person_uuid = :person_uuid"
        extra_params["person_uuid"] = payload.person_uuid

    # 动态排序（白名单校验），默认按日期倒序
    order_by = "v_date DESC, person_name"
    if payload.sort_field in _DAILY_UNDER_HOUR_SORT_FIELDS:
        direction = "DESC" if payload.sort_order == "descend" else "ASC"
        order_by = f"{payload.sort_field} {direction}, person_name"

    sql = _SQL_DAILY_UNDER_HOUR_TMPL.format(
        com_id_in=_safe_in(payload.com_ids),
        extra_where=extra_where,
    )
    params = {
        "start_date": str(payload.start_date),
        "end_date": str(payload.end_date),
        **extra_params,
    }
    return sql, params, order_by


def _duh_rows_to_items(rows: list[dict[str, Any]]) -> list[DailyUnderHourRow]:
    """tot(秒) -> visit_minutes(分钟, 2 位小数)。"""
    items: list[DailyUnderHourRow] = []
    for r in rows:
        tot = r.get("tot")
        minutes = round(float(tot) / 60.0, 2) if tot is not None else None
        items.append(
            DailyUnderHourRow(
                v_date=r.get("v_date"),
                com_id=r.get("com_id"),
                short_name=r.get("short_name"),
                sdpt_name=r.get("sdpt_name"),
                cust_manager_person_uuid=r.get("cust_manager_person_uuid"),
                person_name=r.get("person_name"),
                visit_minutes=minutes,
            )
        )
    return items


# ---------- 分页查询接口 ----------


@router.post("/short-visit", response_model=Paged[ShortVisitRow])
async def audit_short_visit(
    payload: ShortVisitQueryRequest,
    session: AsyncSession = Depends(get_starrocks_session),
) -> Paged[ShortVisitRow]:
    """功能 1：拜访时长 < 1 分钟 (60 秒) 的记录。"""
    sql, params, order_by = _build_short_visit_query(payload)
    total, rows = await _run_paged(
        session, sql, params,
        page=payload.page, page_size=payload.page_size, order_by=order_by,
    )
    return Paged[ShortVisitRow](
        total=total,
        page=payload.page,
        page_size=payload.page_size,
        items=[ShortVisitRow(**r) for r in rows],
    )


@router.post("/full-cust-miss", response_model=Paged[FullCustMissRow])
async def audit_full_cust_miss(
    payload: MonthlyQueryRequest,
    session: AsyncSession = Depends(get_starrocks_session),
) -> Paged[FullCustMissRow]:
    """功能 2：全商品客户当月无拜访。"""
    sql, params, order_by = _build_full_cust_miss_query(payload)
    total, rows = await _run_paged(
        session, sql, params,
        page=payload.page, page_size=payload.page_size, order_by=order_by,
    )
    return Paged[FullCustMissRow](
        total=total,
        page=payload.page,
        page_size=payload.page_size,
        items=[FullCustMissRow(**r) for r in rows],
    )


@router.post("/daily-under-hour", response_model=Paged[DailyUnderHourRow])
async def audit_daily_under_hour(
    payload: DailyUnderHourRequest,
    session: AsyncSession = Depends(get_starrocks_session),
) -> Paged[DailyUnderHourRow]:
    """功能 3：客户经理单日拜访时长汇总 < 60 分钟 (3600 秒)。"""
    sql, params, order_by = _build_daily_under_hour_query(payload)
    total, rows = await _run_paged(
        session, sql, params,
        page=payload.page, page_size=payload.page_size, order_by=order_by,
    )
    return Paged[DailyUnderHourRow](
        total=total,
        page=payload.page,
        page_size=payload.page_size,
        items=_duh_rows_to_items(rows),
    )


# ---------- 导出接口（全量，最多 EXPORT_ROW_LIMIT 行） ----------


@router.post("/short-visit/export", response_model=list[ShortVisitRow])
async def audit_short_visit_export(
    payload: ShortVisitQueryRequest,
    session: AsyncSession = Depends(get_starrocks_session),
) -> list[ShortVisitRow]:
    """功能 1 导出：当前筛选条件下的全部短拜访记录。"""
    sql, params, order_by = _build_short_visit_query(payload)
    rows = await _run_all(session, sql, params, order_by=order_by)
    return [ShortVisitRow(**r) for r in rows]


@router.post("/full-cust-miss/export", response_model=list[FullCustMissRow])
async def audit_full_cust_miss_export(
    payload: MonthlyQueryRequest,
    session: AsyncSession = Depends(get_starrocks_session),
) -> list[FullCustMissRow]:
    """功能 2 导出：当前筛选条件下的全部缺访客户。"""
    sql, params, order_by = _build_full_cust_miss_query(payload)
    rows = await _run_all(session, sql, params, order_by=order_by)
    return [FullCustMissRow(**r) for r in rows]


@router.post("/daily-under-hour/export", response_model=list[DailyUnderHourRow])
async def audit_daily_under_hour_export(
    payload: DailyUnderHourRequest,
    session: AsyncSession = Depends(get_starrocks_session),
) -> list[DailyUnderHourRow]:
    """功能 3 导出：当前筛选条件下的全部不足 60 分钟记录。"""
    sql, params, order_by = _build_daily_under_hour_query(payload)
    rows = await _run_all(session, sql, params, order_by=order_by)
    return _duh_rows_to_items(rows)
