"""审计查询接口：5 个基于 StarRocks 的查询及对应导出。

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import VALID_COM_IDS
from app.db.query import EXPORT_ROW_LIMIT, build_paged_sql, run_all as _run_all, run_paged as _run_paged
from app.db.starrocks import get_starrocks_session
from app.deps import get_current_user
from app.schemas.common import (
    AutoCollectMissRequest,
    AutoCollectMissRow,
    AuditQueryRequest,
    DailyUnderHourRequest,
    DailyUnderHourRow,
    FullCustMissRow,
    LongVisitRequest,
    LongVisitRow,
    MonthlyQueryRequest,
    Paged,
    ShortVisitQueryRequest,
    ShortVisitRow,
)

router = APIRouter(prefix="/api/audit",
                   tags=["audit"], dependencies=[Depends(get_current_user)])


# ============ 辅助工具 ============

MIN_DATE = date(2024, 1, 1)
MIN_MONTH = date(2025, 9, 1)


# 拜访时长阈值白名单（秒/分钟共用同一组可选值），防止非法值
VALID_VISIT_THRESHOLDS = {40, 50, 60, 70, 80, 90}


def _validate_threshold(value: int) -> None:
    if value not in VALID_VISIT_THRESHOLDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"非法阈值: {value}，仅支持 {sorted(VALID_VISIT_THRESHOLDS)}",
        )


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
  AND visit_time < :threshold_seconds
  AND com_id IN ({com_id_in}){extra_where}
"""


# ============ 功能 2 SQL ============
# 依据 database.md 业务逻辑：
# - y_m 是评价"计算月份"（哪个月的全商品评价），仅用于过滤有效数据范围（固定下限 2025-09）
# - sysupdatedate 是评价"生效日期"，决定客户纳入全商品管理的起始月
# - 业务含义：查询评价生效月份（sqdate）内无拜访的全商品客户
# - y_m >= '2025-09' 为固定最小值（全商品评价从2025年9月开始），不随查询区间动态变化
#   若改为 y_m >= :start_ym，会误排除 y_m 早于查询区间但 sysupdatedate 在区间内的记录
# - 许可证发生歇业、停业整顿、收回、注销后，从最早决定月份起不再生成缺访异常

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
    DATE_FORMAT(a.sysupdatedate, '%Y%m') AS year_month,
    cust_uuid,
    cust_code,
    cust_name,
    customer_manager_person_id AS mgr_id,
    DATE_FORMAT(a.sysupdatedate, '%Y-%m-01') AS sqdate
  FROM uc_evaluation_m a
  LEFT JOIN uc_evaluation_m_cust b ON a.evaluation_m_uuid = b.evaluation_m_uuid
  LEFT JOIN kc_customer_yz c ON b.cust_uuid = c.id
  WHERE evaluation_type_adj = '04'
    AND a.status = '3'
    AND y_m >= '2025-09'
),
bg AS (
  SELECT
    lic_no,
    MIN(DATE_FORMAT(decide_date, '%Y-%m-01')) AS decide_month
  FROM tstg_zmglpt_std_l_rlic_handle_main
  WHERE handle_result IN ('02', '05')
    AND apply_type IN ('07', '10', '12', '18')
    AND decide_date >= :license_change_floor
  GROUP BY lic_no
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
    bg.decide_month,
    coalesce(sl, 0) AS sl
  FROM list
  LEFT JOIN bf ON list.cust_uuid = bf.cust_uuid AND list.sqdate = bf.op_month
  LEFT JOIN bg ON list.cust_code = bg.lic_no
  LEFT JOIN t_comm_employee d ON list.mgr_id = d.person_uuid
)
SELECT DISTINCT year_month, short_name, sdpt_name, person_name, cust_code, cust_name
FROM zh
WHERE sl = 0
  AND com_id IN ({com_id_in})
  AND sqdate >= :start_month
  AND sqdate < DATE_ADD(:end_month, INTERVAL 1 MONTH)
  AND (decide_month IS NULL OR sqdate < decide_month){extra_where}
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
HAVING sum(visit_time) < :threshold_seconds
"""


# ============ 接口实现 ============


# 功能 1 排序字段白名单（防 SQL 注入）
_SHORT_VISIT_SORT_FIELDS = {"plan_date", "visit_time"}

# 功能 2 / 功能 3 排序字段白名单
_FULL_CUST_MISS_SORT_FIELDS = {"year_month"}
_DAILY_UNDER_HOUR_SORT_FIELDS = {"v_date"}

# ---------- SQL 构建器（分页查询与导出共用） ----------


def _build_short_visit_query(payload: ShortVisitQueryRequest) -> tuple[str, dict[str, Any], str]:
    _validate_com_ids(payload.com_ids)
    _validate_date_range(payload.start_date, payload.end_date)
    _validate_threshold(payload.threshold_seconds)

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
        "threshold_seconds": payload.threshold_seconds,
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
        # 许可证终止类流程必须从业务固定起点扫描，不能随查询起始月缩窄。
        "license_change_floor": str(MIN_MONTH),
        **extra_params,
    }
    return sql, params, order_by


def _build_daily_under_hour_query(payload: DailyUnderHourRequest) -> tuple[str, dict[str, Any], str]:
    _validate_com_ids(payload.com_ids)
    _validate_date_range(payload.start_date, payload.end_date)
    _validate_threshold(payload.threshold_minutes)

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
        "threshold_seconds": payload.threshold_minutes * 60,
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


# ---------- 功能 4 / 5：单次超长拜访、自动信息采集户缺访 ----------

_SQL_LONG_VISIT_TMPL = """
SELECT
  CAST(cms.id AS VARCHAR) AS visit_id,
  DATE_FORMAT(cms.plan_date, '%Y-%m-%d') AS v_date,
  DATE_FORMAT(cms.plan_date, '%Y-%m-%d %H:%i:%s') AS visit_timestamp,
  emp.com_id, emp.short_name, emp.sdpt_name,
  cms.cust_manager_person_uuid, emp.person_name,
  cms.cust_uuid, cms.license_code, cms.cust_name, cms.visit_time
FROM crm_mcs_cust_visit_plan cms
LEFT JOIN t_comm_emp_yx emp ON cms.cust_manager_person_uuid = emp.person_uuid
WHERE cms.plan_date >= :start_date
  AND cms.plan_date < DATE_ADD(:end_date, INTERVAL 1 DAY)
  AND cms.visit_status = '03'
  AND cms.deleted = '0'
  AND cms.visit_time > :threshold_seconds
  AND emp.com_id IN ({com_id_in}){extra_where}
"""

_SQL_AUTO_COLLECT_MISS_TMPL = """
WITH bf AS (
  SELECT cust_uuid, DATE_FORMAT(plan_date, '%Y-%m-01') AS op_month, COUNT(*) AS sl
  FROM crm_mcs_cust_visit_plan
  WHERE plan_date >= :start_month
    AND plan_date < DATE_ADD(:end_month, INTERVAL 1 MONTH)
    AND visit_status = '03' AND deleted = '0'
  GROUP BY cust_uuid, DATE_FORMAT(plan_date, '%Y-%m-01')
),
list AS (
  SELECT DATE_FORMAT(a.sysupdatedate, '%Y%m') AS year_month,
    b.cust_uuid, cust_code, cust_name, customer_manager_person_id AS mgr_id,
    DATE_FORMAT(a.sysupdatedate, '%Y-%m-01') AS sqdate
  FROM uc_evaluation_m a
  LEFT JOIN uc_evaluation_m_cust b ON a.evaluation_m_uuid = b.evaluation_m_uuid
  LEFT JOIN kc_customer_yz c ON b.cust_uuid = c.id
  WHERE evaluation_type_adj = '03' AND a.status = '3' AND y_m >= '2025-09'
)
SELECT DISTINCT list.year_month, d.com_id, d.short_name, d.sdpt_name,
  d.person_name, list.cust_uuid, list.mgr_id, list.cust_code, list.cust_name
FROM list
LEFT JOIN bf ON list.cust_uuid = bf.cust_uuid AND list.sqdate = bf.op_month
LEFT JOIN t_comm_employee d ON list.mgr_id = d.person_uuid
WHERE COALESCE(bf.sl, 0) = 0
  AND list.sqdate >= :start_month
  AND list.sqdate < DATE_ADD(:end_month, INTERVAL 1 MONTH)
  AND d.com_id IN ({com_id_in}){extra_where}
"""


def _build_long_visit_query(payload: LongVisitRequest) -> tuple[str, dict[str, Any], str]:
    """所选分钟阈值转为秒数比较，等于阈值的记录通过规则。"""
    _validate_com_ids(payload.com_ids)
    _validate_date_range(payload.start_date, payload.end_date)
    extra_where = ""
    params: dict[str, Any] = {
        "start_date": str(payload.start_date), "end_date": str(payload.end_date),
        "threshold_seconds": payload.threshold_minutes * 60,
    }
    if payload.sdpt_name:
        extra_where += "\n  AND emp.sdpt_name = :sdpt_name"
        params["sdpt_name"] = payload.sdpt_name
    if payload.person_uuid:
        extra_where += "\n  AND cms.cust_manager_person_uuid = :person_uuid"
        params["person_uuid"] = payload.person_uuid
    # 使用原始秒数排序，保持分钟展示舍入前的正确先后关系。
    sort_columns = {"v_date": "v_date", "visit_minutes": "visit_time"}
    column = sort_columns.get(payload.sort_field or "", "v_date")
    direction = "ASC" if payload.sort_order == "ascend" else "DESC"
    order_by = f"{column} {direction}, visit_timestamp DESC, com_id, cust_manager_person_uuid, cust_uuid, license_code, visit_time, cust_name, visit_id"
    sql = _SQL_LONG_VISIT_TMPL.format(com_id_in=_safe_in(payload.com_ids), extra_where=extra_where)
    return sql, params, order_by


def _build_auto_collect_miss_query(payload: AutoCollectMissRequest) -> tuple[str, dict[str, Any], str]:
    """按评价生效月检查有效拜访次数，评价计算月保持固定业务起点。"""
    _validate_com_ids(payload.com_ids)
    _validate_month_range(payload.start_month, payload.end_month)
    if payload.start_month.day != 1 or payload.end_month.day != 1:
        raise HTTPException(status_code=422, detail="月份参数必须为每月第一天")
    extra_where = ""
    params: dict[str, Any] = {
        "start_month": str(payload.start_month), "end_month": str(payload.end_month),
    }
    if payload.sdpt_name:
        extra_where += "\n  AND d.sdpt_name = :sdpt_name"
        params["sdpt_name"] = payload.sdpt_name
    if payload.person_uuid:
        extra_where += "\n  AND list.mgr_id = :person_uuid"
        params["person_uuid"] = payload.person_uuid
    direction = "DESC" if payload.sort_field == "year_month" and payload.sort_order == "descend" else "ASC"
    order_by = f"year_month {direction}, com_id, sdpt_name, person_name, cust_code, cust_uuid, mgr_id, cust_name"
    sql = _SQL_AUTO_COLLECT_MISS_TMPL.format(com_id_in=_safe_in(payload.com_ids), extra_where=extra_where)
    return sql, params, order_by


def _long_visit_rows_to_items(rows: list[dict[str, Any]]) -> list[LongVisitRow]:
    """分页和导出共用分钟转换，保留两位小数。"""
    return [LongVisitRow(**{
        **row,
        "visit_minutes": round(float(row["visit_time"]) / 60, 2) if row.get("visit_time") is not None else None,
    }) for row in rows]


@router.post("/long-visit", response_model=Paged[LongVisitRow])
async def audit_long_visit(
    payload: LongVisitRequest, session: AsyncSession = Depends(get_starrocks_session),
) -> Paged[LongVisitRow]:
    """单次有效拜访超过所选分钟阈值，默认 300 分钟。"""
    sql, params, order_by = _build_long_visit_query(payload)
    total, rows = await _run_paged(session, sql, params, payload.page, payload.page_size, order_by)
    return Paged[LongVisitRow](total=total, page=payload.page, page_size=payload.page_size, items=_long_visit_rows_to_items(rows))


@router.post("/long-visit/export", response_model=list[LongVisitRow])
async def audit_long_visit_export(
    payload: LongVisitRequest, session: AsyncSession = Depends(get_starrocks_session),
) -> list[LongVisitRow]:
    """按相同条件和顺序导出超长拜访。"""
    sql, params, order_by = _build_long_visit_query(payload)
    return _long_visit_rows_to_items(await _run_all(session, sql, params, order_by))


@router.post("/auto-collect-miss", response_model=Paged[AutoCollectMissRow])
async def audit_auto_collect_miss(
    payload: AutoCollectMissRequest, session: AsyncSession = Depends(get_starrocks_session),
) -> Paged[AutoCollectMissRow]:
    """自动信息采集户评价生效月零有效拜访。"""
    sql, params, order_by = _build_auto_collect_miss_query(payload)
    total, rows = await _run_paged(session, sql, params, payload.page, payload.page_size, order_by)
    return Paged[AutoCollectMissRow](total=total, page=payload.page, page_size=payload.page_size, items=[AutoCollectMissRow(**row) for row in rows])


@router.post("/auto-collect-miss/export", response_model=list[AutoCollectMissRow])
async def audit_auto_collect_miss_export(
    payload: AutoCollectMissRequest, session: AsyncSession = Depends(get_starrocks_session),
) -> list[AutoCollectMissRow]:
    """导出采集户缺访，按提供的 SQL 使用有效拜访次数口径。"""
    sql, params, order_by = _build_auto_collect_miss_query(payload)
    return [AutoCollectMissRow(**row) for row in await _run_all(session, sql, params, order_by)]
