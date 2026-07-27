"""元数据接口（公司字典、员工列表等）。"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import COMPANIES, VALID_COM_IDS
from app.db.starrocks import get_starrocks_session
from app.deps import get_current_user
from app.schemas.common import CompanyItem, EmployeeGroup, EmployeeMember

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/companies", response_model=list[CompanyItem])
async def list_companies(_: str = Depends(get_current_user)) -> list[CompanyItem]:
    return [CompanyItem(**c) for c in COMPANIES]


@router.get("/employees", response_model=list[EmployeeGroup])
async def list_employees(
    com_ids: str = Query(..., description="逗号分隔的公司代码，不能为空"),
    _: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_starrocks_session),
) -> list[EmployeeGroup]:
    """按公司查询营业部 + 客户经理列表（用于功能3联动过滤）。"""
    ids = [i.strip() for i in com_ids.split(",") if i.strip()]
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="公司代码不能为空")
    invalid = [i for i in ids if i not in VALID_COM_IDS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"非法公司代码: {invalid}")

    safe_in = ", ".join(f"'{i}'" for i in ids)
    sql = f"""
        SELECT DISTINCT sdpt_name, person_uuid, person_name
        FROM t_comm_emp_yx
        WHERE com_id IN ({safe_in})
        ORDER BY sdpt_name, person_name
    """
    rows = (await session.execute(text(sql))).mappings().all()

    groups: dict[str, list[EmployeeMember]] = defaultdict(list)
    for r in rows:
        sdpt = r["sdpt_name"] or "未分配营业部"
        groups[sdpt].append(EmployeeMember(
            person_uuid=r["person_uuid"], person_name=r["person_name"]))

    return [EmployeeGroup(sdpt_name=k, members=v) for k, v in sorted(groups.items())]
