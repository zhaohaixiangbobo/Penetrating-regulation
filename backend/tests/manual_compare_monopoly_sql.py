"""只读小样本核对：页面后端接口结果与用户原始 SQL 比较，保留重复行，不打印客户信息。"""
import asyncio
import json
from collections import Counter
from decimal import Decimal
from sqlalchemy import text
from app.db.starrocks import _SessionLocal, get_engine
from app.api.marketing_monopoly import bank_owner_mismatch, visit_location
from app.schemas.marketing_monopoly import BankOwnerMismatchRequest, VisitLocationRequest

BANK = """
WITH t1 AS (
 SELECT cust_code, cust_name, sale_depart_name, sale_route_name, bankcard_owner, sysupdatedt,
 ROW_NUMBER() OVER (PARTITION BY cust_code ORDER BY sysupdatedt DESC) AS rn FROM pc_pay_custbank
), t2 AS (
 SELECT issue_org_code, issue_org_name, lic_no, company_name, manager_name
 FROM r_license_info WHERE lic_status='10'
)
SELECT issue_org_code, issue_org_name, lic_no, company_name, manager_name, bankcard_owner,
 DATE_FORMAT(sysupdatedt, '%Y-%m-%d %H:%i:%s') AS sysupdatedt
FROM t2 LEFT JOIN (SELECT * FROM t1 WHERE rn=1) x ON t2.lic_no=x.cust_code
WHERE TRIM(manager_name) <> TRIM(bankcard_owner)
 AND bankcard_owner IS NOT NULL AND bankcard_owner <> ''
"""
VISIT = """
WITH t1 AS (
 SELECT issue_org_code, issue_org_name, lic_no, company_name, manager_name, longitude, latitude
 FROM r_license_info
), t2 AS (
 SELECT issue_org_code, issue_org_name, person_name, DATE_FORMAT(plan_date,'%Y-%m-%d') AS plan_date,
 cust_code, cust_name, longitude, latitude, gis_long, gis_lat
 FROM crm_mcs_cust_visit_plan a
 LEFT JOIN t1 ON a.cust_code=t1.lic_no
 LEFT JOIN t_comm_emp_yx t ON a.cust_manager_person_uuid=t.person_uuid
 WHERE plan_date >= '2024-01-01 00:00:00' AND visit_status='03' AND deleted='0'
 AND plan_date >= :start_date AND plan_date < DATE_ADD(:end_date, INTERVAL 1 DAY)
)
SELECT t2.*, ST_Distance_Sphere(longitude,latitude,gis_long,gis_lat) AS distance_meters
FROM t2 WHERE ST_Distance_Sphere(longitude,latitude,gis_long,gis_lat) > :distance_meters
"""

async def compare(session, label, endpoint, payload, reference, params):
    reference_rows = (await session.execute(text(reference + ' LIMIT 2001'), params)).mappings().all()
    if len(reference_rows) > 2000:
        raise RuntimeError('样本超过2000条，请缩小范围')
    result = await endpoint(payload, session)
    rows = list(result.items)
    for page in range(2, (result.total + 199) // 200 + 1):
        if result.total > 2000:
            raise RuntimeError('页面样本超过2000条，请缩小范围')
        rows.extend((await endpoint(payload.model_copy(update={'page': page}), session)).items)
    # 仅比较原 SQL 的业务字段；展示用简称、距离两位小数不改变底层值。
    fields = list(reference_rows[0]) if reference_rows else []
    def key(row):
        # 数据库 Decimal 与 JSON 浮点数统一为十进制数值，去除类型和尾零差异。
        return tuple(Decimal(str(row.get(field))) if isinstance(row.get(field), (Decimal, float)) else row.get(field) for field in fields)
    expected = Counter(key(dict(row)) for row in reference_rows)
    actual = Counter(key(row.model_dump()) for row in rows)
    report = dict(case=label, original_count=len(reference_rows), page_count=result.total,
                  missing=sum((expected-actual).values()), extra=sum((actual-expected).values()))
    report['passed'] = result.total == len(reference_rows) and expected == actual
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report

async def main():
    reports = []
    async with _SessionLocal() as session:
        await session.execute(text('SET query_timeout=20'))
        reports.append(await compare(session, '扣款户名：全部日期', bank_owner_mismatch,
            BankOwnerMismatchRequest(page_size=200), BANK, {}))
        for start, end in [('2024-01-01','2024-04-02'), ('2025-09-30','2026-09-30')]:
            reports.append(await compare(session, f'扣款户名：{start}至{end}', bank_owner_mismatch,
                BankOwnerMismatchRequest(start_date=start,end_date=end,page_size=200),
                BANK + ' AND sysupdatedt >= :start_date AND sysupdatedt < DATE_ADD(:end_date, INTERVAL 1 DAY)',
                dict(start_date=start,end_date=end)))
        for threshold in [200,500]:
            params=dict(start_date='2024-01-02',end_date='2024-01-02',distance_meters=threshold)
            reports.append(await compare(session, f'定位偏差：2024-01-02，超过{threshold}米', visit_location,
                VisitLocationRequest(**params,page_size=200), VISIT, params))
    await get_engine().dispose()
    if not all(report['passed'] for report in reports):
        raise SystemExit('存在差异，需要进一步核对')

if __name__ == '__main__':
    asyncio.run(main())
