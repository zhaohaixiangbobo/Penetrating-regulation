"""只读小样本核对：风险指标与直接 SQL 同事件组合比对，仅输出汇总。"""
import argparse
import asyncio
import json
from sqlalchemy import text
from app.db.starrocks import _SessionLocal, get_engine
from app.schemas.risk import RunRequest
from app.services.risk_engine import fetch_events, normalize
from app.services.risk_rules import DEFAULT_CONFIG, evaluate

# 独立使用原始拜访、人员和许可证直接关联，核对同事件组合与距离。
SQL = """
SELECT CAST(a.id AS VARCHAR) source_id,
 DATE_FORMAT(a.plan_date,'%Y-%m-%d %H:%i:%s') event_time,
 CAST(a.in_monthly_plan AS VARCHAR) in_monthly_plan,
 a.visit_time, ST_Distance_Sphere(l.longitude,l.latitude,a.gis_long,a.gis_lat) distance_meters
FROM crm_mcs_cust_visit_plan a
JOIN t_comm_emp_yx e ON a.cust_manager_person_uuid=e.person_uuid
JOIN r_license_info l ON a.cust_code=l.lic_no
WHERE a.visit_status='03' AND a.deleted='0' AND e.com_id=:company
AND a.plan_date>=:start AND a.plan_date<DATE_ADD(:end,INTERVAL 1 DAY)
AND l.longitude BETWEEN -180 AND 180 AND l.latitude BETWEEN -90 AND 90
AND a.gis_long BETWEEN -180 AND 180 AND a.gis_lat BETWEEN -90 AND 90
AND (l.longitude<>0 OR l.latitude<>0) AND (a.gis_long<>0 OR a.gis_lat<>0)
LIMIT 5001
"""

async def main(args):
    valid=RunRequest(version_id=1,start_date=args.start,end_date=args.end,com_ids=[args.company])
    scope=dict(start_date=str(valid.start_date),end_date=str(valid.end_date),com_ids=valid.com_ids)
    rows=await fetch_events(scope)
    async with _SessionLocal() as s:
        await s.execute(text('SET query_timeout=30'))
        direct=(await s.execute(text(SQL),dict(company=args.company,start=args.start,end=args.end))).mappings().all()
    assert len(direct)<=5000,'样本超过5000条，请缩小范围'
    actual={}; expected={}
    for row in rows:
        key,data,values=normalize(row)
        # 多许可证资料本身属于不可判断，另行报告，不强行与扩行结果比较。
        if row.get('matches')==1:
            actual[key]=values
    for row in direct:
        key,_,values=normalize(dict(row))
        assert key not in expected,'直接关联扩行，请先核实资料唯一性'
        expected[key]=values
    distance_pairs=0
    for key,values in actual.items():
        if values['visit_location_distance_meters'] is not None:
            assert key in expected,'直接SQL缺少模型事件'
            assert abs(float(values['visit_location_distance_meters'])-float(expected[key]['visit_location_distance_meters']))<0.001
            distance_pairs+=1
    hit={key for key,v in actual.items() if evaluate(DEFAULT_CONFIG,v)[0]=='hit'}
    reference={key for key,v in expected.items() if v['visit_duration_seconds'] is not None and 0<=v['visit_duration_seconds']<60 and v['visit_location_distance_meters']>200}
    assert hit==reference,'组合命中事件存在差异'
    print(json.dumps(dict(company=args.company,start=args.start,end=args.end,scanned=len(rows),
        matched_coordinates=distance_pairs,model_hits=len(hit),sql_hits=len(reference),
        gps_over_200=sum(v['visit_location_distance_meters'] is not None and v['visit_location_distance_meters']>200 for v in actual.values()),passed=True),ensure_ascii=False))
    await get_engine().dispose()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company',default='11120101')
    parser.add_argument('--start',default='2026-09-01')
    parser.add_argument('--end',default='2026-09-07')
    asyncio.run(main(parser.parse_args()))
