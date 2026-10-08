"""上线前只读小样本检查：指定一个公司和日期，核对候选键及游标分页，不设置已核实开关。"""
import argparse
import asyncio
import json
import time
from app.services.risk_engine import fetch_events, normalize
from app.core.config import VALID_COM_IDS
from app.db.starrocks import _SessionLocal as StarSession
from sqlalchemy import text


async def check(company, day, page_size):
    started=time.monotonic()
    scope=dict(com_ids=[company],start_date=day,end_date=day,_batch_size=page_size)
    first=await fetch_events(scope)
    keys=[normalize(r)[0] for r in first]
    report=dict(company=company,day=day,first_page_sample=len(first),duplicate_sample_keys=len(keys)-len(set(keys)),
                null_monthly_plan=sum(r.get('in_monthly_plan') is None for r in first),data_cutoff='未知')
    if len(first)>page_size:
        last=first[page_size-1]
        scope['_cursor']=dict(event_time=last['event_time'],source_id=last['source_id'],is_null=int(last.get('in_monthly_plan') is None),monthly=last.get('in_monthly_plan') or '')
        second=await fetch_events(scope)
        report['next_page_first_matches_lookahead']=bool(second and normalize(second[0])[0]==keys[page_size])
        report['cross_page_duplicate']=len(set(keys[:page_size]) & {normalize(r)[0] for r in second})
    report['elapsed_seconds']=round(time.monotonic()-started,2)
    # 只输出键约束，避免将源库连接信息或业务明细写入检查日志。
    async with StarSession() as session:
        schema=(await session.execute(text('SHOW CREATE TABLE crm_mcs_cust_visit_plan'))).first()
        report['source_key_definition']=[line.strip() for line in str(schema[1]).splitlines()
                                         if any(word in line.upper() for word in ('PRIMARY KEY','UNIQUE KEY','DUPLICATE KEY'))]
    report['limitation']='仅小样本；全局唯一性与不可变性须由源表约束及维护方确认'
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    from datetime import date
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company',required=True,choices=sorted(VALID_COM_IDS))
    parser.add_argument('--date',required=True,type=date.fromisoformat)
    parser.add_argument('--page-size',type=int,choices=range(1,101),default=100)
    args=parser.parse_args()
    try:
        asyncio.run(check(args.company,str(args.date),args.page_size))
    except Exception:
        print('源库连接或查询失败；请在可访问 StarRocks 的环境重试，本次未验证源键。')
        raise SystemExit(1)
