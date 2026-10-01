"""只读业务查询公共执行器：计数、服务端分页与带行数上限的导出。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPORT_ROW_LIMIT = 100000


def build_paged_sql(inner_sql: str, order_by: str | None = None) -> tuple[str, str]:
    """计数与明细复用业务 SQL，排序由调用方的字段白名单生成。"""
    count_sql = f"SELECT count(*) AS c FROM (\n{inner_sql}\n) _t"
    order_clause = f"\nORDER BY {order_by}" if order_by else ""
    data_sql = f"SELECT * FROM (\n{inner_sql}\n) _t{order_clause}\nLIMIT :limit OFFSET :offset"
    return count_sql, data_sql


async def run_paged(
    session: AsyncSession, inner_sql: str, params: dict[str, Any],
    page: int, page_size: int, order_by: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """先计数后取当前页，统一返回字典行。"""
    count_sql, data_sql = build_paged_sql(inner_sql, order_by)
    total_row = (await session.execute(text(count_sql), params)).first()
    total = int(total_row[0]) if total_row and total_row[0] is not None else 0
    rows = (await session.execute(text(data_sql), {
        **params, "limit": page_size, "offset": (page - 1) * page_size,
    })).mappings().all()
    return total, [dict(row) for row in rows]


async def run_all(
    session: AsyncSession, inner_sql: str, params: dict[str, Any],
    order_by: str | None = None, limit: int = EXPORT_ROW_LIMIT,
) -> list[dict[str, Any]]:
    """导出相同条件下的结果，并限制单次行数。"""
    order_clause = f"\nORDER BY {order_by}" if order_by else ""
    sql = f"SELECT * FROM (\n{inner_sql}\n) _t{order_clause}\nLIMIT :export_limit"
    rows = (await session.execute(text(sql), {**params, "export_limit": limit})).mappings().all()
    return [dict(row) for row in rows]
