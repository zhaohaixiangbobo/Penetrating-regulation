"""风险运行器：持久队列、租约防并发、限量读取、快照对比和事务归并。"""
import asyncio
import contextlib
import json
import logging
import time
import uuid
from decimal import Decimal
from sqlalchemy import select, update, text
from sqlalchemy.dialects.sqlite import insert
from app.core.config import get_settings
from app.db.sqlite import get_sessionmaker
from app.db.starrocks import _SessionLocal as StarSession
from app.models.clue import beijing_now
from app.models.risk import RiskModel, RiskVersion, RiskRun, RiskItem, RiskAlert, RiskOccurrence, RiskLease, RiskBatch, RiskBatchAttempt
from app.services.risk_rules import DEFAULT_CONFIG, evaluate

logger = logging.getLogger('shenji.risk')
MAX_EVENTS = 5000

async def bootstrap():
    """固定编号种子使用幂等插入，发布版本始终保持原配置。"""
    async with get_sessionmaker()() as s:
        await s.execute(insert(RiskLease).values(id=1,owner='',expires=0).on_conflict_do_nothing())
        await s.execute(insert(RiskModel).values(id=1,name='拜访履职异常',enabled=True,created_at=beijing_now()).on_conflict_do_nothing())
        await s.execute(insert(RiskVersion).values(id=1,model_id=1,number=1,config=DEFAULT_CONFIG,
            published=True,created_by='system',created_at=beijing_now(),published_at=beijing_now()).on_conflict_do_nothing())
        await s.commit()

async def fetch_events(scope: dict):
    """按候选复合键读取；源表为 DUPLICATE KEY，正式使用须另行核实唯一性和稳定性。"""
    keys = ','.join(f':company_{i}' for i in range(len(scope['com_ids'])))
    params = {f'company_{i}':v for i,v in enumerate(scope['com_ids'])}
    page_size = scope.get('_batch_size', MAX_EVENTS)
    params.update(start=scope['start_date'], end=scope['end_date'], cap=page_size+1)
    cursor = scope.get('_cursor')
    cursor_filter = ''
    if cursor:
        params.update(cursor)
        cursor_filter = """WHERE (event_time > :event_time OR
          (event_time = :event_time AND source_id > :source_id) OR
          (event_time = :event_time AND source_id = :source_id AND
           ((:is_null = 1 AND in_monthly_plan IS NOT NULL) OR
            (:is_null = 0 AND in_monthly_plan > :monthly))))"""

    sql = f"""
WITH lic AS (
 SELECT lic_no, COUNT(*) AS matches, MAX(longitude) longitude, MAX(latitude) latitude,
 MAX(issue_org_name) issue_org_name, MAX(company_name) company_name
 FROM r_license_info GROUP BY lic_no
), emp AS (
 SELECT person_uuid, MAX(person_name) person_name, MAX(com_id) com_id,
 MAX(short_name) short_name, COUNT(DISTINCT com_id) companies
 FROM t_comm_emp_yx GROUP BY person_uuid
), source AS (
 SELECT CAST(a.id AS VARCHAR) source_id, CAST(a.in_monthly_plan AS VARCHAR) in_monthly_plan,
 CAST(a.plan_date AS VARCHAR) event_time,
 a.cust_code, a.cust_name, a.cust_manager_person_uuid person_id,
 e.person_name, e.com_id, e.short_name, e.companies,
 a.visit_time, l.longitude, l.latitude, a.gis_long, a.gis_lat, l.matches,
 l.issue_org_name, l.company_name,
 CASE WHEN l.matches=1 AND l.longitude BETWEEN -180 AND 180 AND l.latitude BETWEEN -90 AND 90
 AND a.gis_long BETWEEN -180 AND 180 AND a.gis_lat BETWEEN -90 AND 90
 AND (l.longitude<>0 OR l.latitude<>0) AND (a.gis_long<>0 OR a.gis_lat<>0)
 THEN ST_Distance_Sphere(l.longitude,l.latitude,a.gis_long,a.gis_lat) ELSE NULL END distance_meters
 FROM crm_mcs_cust_visit_plan a
 JOIN emp e ON a.cust_manager_person_uuid=e.person_uuid
 LEFT JOIN lic l ON a.cust_code=l.lic_no
 WHERE a.visit_status='03' AND a.deleted='0' AND a.plan_date>=:start
 AND a.plan_date<DATE_ADD(:end, INTERVAL 1 DAY) AND e.com_id IN ({keys})
)
SELECT * FROM source {cursor_filter} ORDER BY event_time, source_id, CASE WHEN in_monthly_plan IS NULL THEN 0 ELSE 1 END, in_monthly_plan LIMIT :cap
"""
    async def read_page():
        async with StarSession() as s:
            await s.execute(text('SET query_timeout=30'))
            return (await s.execute(text(sql),params)).mappings().all()
    # 连接建立、会话设置与查询合计受应用超时约束。
    rows = await asyncio.wait_for(read_page(),40)
    if '_batch_size' not in scope and len(rows)>MAX_EVENTS:
        raise ValueError('范围超过5000次拜访，请缩小日期或公司范围后运行；本次结果未发布')
    return [dict(r) for r in rows]

def normalize(row):
    """只将已验证可用的数据用于判断，证据另保留原始字段。"""
    data = {k:float(v) if isinstance(v,Decimal) else v for k,v in row.items()}
    if not data.get('source_id') or not data.get('event_time'):
        raise ValueError('拜访源键缺失，无法可靠去重；请先核对源数据')
    # 统一时间文本并保留非零微秒；旧秒精度记录的事件键保持稳定。
    data['event_time']=__import__('datetime').datetime.fromisoformat(str(data['event_time'])).isoformat(sep=' ')
    if data.get('companies',1)!=1:
        raise ValueError('人员关联到多个公司，需先核实组织归属')
    # 源表复合键允许 in_monthly_plan 为 NULL；用 JSON null 保留真实键值。
    key = json.dumps([data['source_id'],data['event_time'],data.get('in_monthly_plan')],ensure_ascii=False)
    duration = data.get('visit_time')
    if duration is not None:
        try: duration = float(duration)
        except (TypeError,ValueError): duration = None
    values = dict(visit_duration_seconds=duration,visit_location_distance_meters=data.get('distance_meters'))
    return key, data, values

async def lease(owner):
    async with get_sessionmaker()() as s:
        changed = await s.execute(update(RiskLease).where(RiskLease.id==1,
            (RiskLease.owner==owner)|(RiskLease.expires<time.time())).values(owner=owner,expires=time.time()+20))
        await s.commit()
        return changed.rowcount==1

async def heartbeat(owner, lost):
    while True:
        await asyncio.sleep(4)
        try:
            renewed=await lease(owner)
        except Exception:
            logger.exception('租约心跳失败，停止当前所有者领取任务')
            lost.set()
            return
        if not renewed:
            lost.set()
            return

async def allowed(run_id, owner):
    if not get_settings().RISK_MODULE_ENABLED or not get_settings().RISK_RUN_ENABLED:
        return False
    async with get_sessionmaker()() as s:
        r = await s.get(RiskRun,run_id)
        l = await s.get(RiskLease,1)
        return bool(r and r.status=='running' and not r.cancel_requested and l and l.owner==owner and l.expires>time.time())

async def finish_error(run_id, owner, status, reason):
    async with get_sessionmaker()() as s:
        # 写入租约校验同时取得SQLite写锁，失去租约的进程无法提交运行状态。
        locked = await s.execute(update(RiskLease).where(RiskLease.id==1,RiskLease.owner==owner,
            RiskLease.expires>time.time()).values(expires=time.time()+20))
        if locked.rowcount:
            await s.execute(update(RiskRun).where(RiskRun.id==run_id,RiskRun.status=='running').values(
                status=status,stage='已取消' if status=='cancelled' else '运行失败',error=reason,ended_at=beijing_now()))
            await s.commit()

async def execute_run(run_id, owner, batch_id=None, token=None):
    async with get_sessionmaker()() as s:
        run = await s.get(RiskRun,run_id)
        scope, config, baseline, mode = run.scope, run.snapshot, run.baseline, run.mode
        batch = await s.get(RiskBatch, batch_id) if batch_id else None
        if batch:
            scope = {**scope, 'start_date': batch.day, 'end_date': batch.day, 'com_ids': [batch.company],
                     '_batch_size': scope.get('batch_size', get_settings().RISK_BATCH_SIZE), '_cursor': batch.cursor}
    rows = await fetch_events(scope)
    more = bool(batch and len(rows) > scope['_batch_size'])
    # 额外一行用于判断是否有下一页，并检查跨页边界的重复源键。
    if more and normalize(rows[scope['_batch_size']-1])[0] == normalize(rows[scope['_batch_size']])[0]:
        raise ValueError('分页边界存在重复事件键，停止本批发布')
    if batch: rows = rows[:scope['_batch_size']]
    items, seen = [], set()
    counts = dict(scanned=len(rows),hit=0,clear=0,unknown=0,quality_unknown=0,new_alerts=0,existing_alerts=0,
                  closed_rematches=0,new=0,removed=0,common=0,baseline_hit=0,customers=0,managers=0,
                  data_cutoff='源系统未提供可验证同步水位',read_at=beijing_now().isoformat())
    customers,managers=set(),set()
    for row in rows:
        key,data,values=normalize(row)
        if key in seen:
            raise ValueError('源事件键重复，已停止发布；请先核对数据唯一性')
        seen.add(key)
        outcome,reasons=evaluate(config,values)
        old = evaluate(baseline,values)[0] if baseline else None
        counts[outcome]+=1
        counts['quality_unknown'] += int(any(r['outcome']=='unknown' for r in reasons))
        if outcome=='hit':
            customers.add(data.get('cust_code'))
            managers.add(data.get('person_id'))
        if baseline:
            counts['baseline_hit']+=int(old=='hit')
            counts['new']+=int(outcome=='hit' and old!='hit')
            counts['removed']+=int(outcome!='hit' and old=='hit')
            counts['common']+=int(outcome=='hit' and old=='hit')
        items.append(RiskItem(run_id=run_id,batch_id=batch_id,event_key=key,outcome=outcome,baseline_outcome=old,evidence=data,reasons=reasons))
    counts.update(customers=len(customers-{None}),managers=len(managers-{None}))
    if not await allowed(run_id,owner):
        if batch_id:
            from app.services.risk_jobs import cancel_batch
            await cancel_batch(run_id,batch_id,token,owner)
            return
        await finish_error(run_id,owner,'cancelled','任务已取消或运行开关关闭')
        return
    async with get_sessionmaker()() as s:
        # 原子发布：先取得写锁并校验租约，再次读取取消状态；失败则整批回滚。
        lock=await s.execute(update(RiskLease).where(RiskLease.id==1,RiskLease.owner==owner,
            RiskLease.expires>time.time()).values(expires=time.time()+60))
        if not lock.rowcount: return
        run=await s.get(RiskRun,run_id)
        if run.cancel_requested or run.status!='running':
            if batch_id:
                await s.rollback()
                from app.services.risk_jobs import cancel_batch
                await cancel_batch(run_id,batch_id,token,owner)
            else:
                run.status='cancelled';run.stage='已取消';run.ended_at=beijing_now()
                await s.commit()
            return
        current_batch = await s.get(RiskBatch, batch_id) if batch_id else None
        if current_batch and (current_batch.status != 'running' or current_batch.token != token): return
        s.add_all(items)
        await s.flush()
        if mode=='formal':
            hit_items=[i for i in items if i.outcome=='hit']
            keys=[i.event_key for i in hit_items]
            existing={a.event_key:a for a in (await s.scalars(select(RiskAlert).where(RiskAlert.model_version_id==run.version_id,RiskAlert.event_key.in_(keys)))).all()} if keys else {}
            # 批量加载背景事项与现有事项，减少写事务内逐行查询。
            closed=(await s.scalars(select(RiskAlert).where(RiskAlert.model_id==run.model_id,RiskAlert.status=='closed',
                RiskAlert.cust_code.in_({i.evidence.get('cust_code') for i in hit_items})).order_by(RiskAlert.closed_at.desc()))).all() if hit_items else []
            links=[]
            for item in hit_items:
                alert=existing.get(item.event_key)
                if alert:
                    counts['existing_alerts']+=1;counts['closed_rematches']+=int(alert.status=='closed')
                    alert.latest_item_id=item.id;alert.last_seen=beijing_now()
                else:
                    d=item.evidence
                    prior=next((a for a in closed if a.event_key!=item.event_key and a.cust_code==d.get('cust_code') and a.person_id==d.get('person_id') and a.closed_at<__import__('datetime').datetime.fromisoformat(d['event_time'])),None)
                    alert=RiskAlert(model_id=run.model_id,model_version_id=run.version_id,model_name=run.model_name,event_key=item.event_key,
                        first_item_id=item.id,latest_item_id=item.id,cust_code=d.get('cust_code'),cust_name=d.get('cust_name'),
                        person_id=d.get('person_id'),person_name=d.get('person_name'),com_id=d.get('com_id'),
                        short_name=d.get('short_name'),event_time=d['event_time'],prior_alert_id=prior.id if prior else None,
                        recurrence=bool(prior and prior.conclusion=='confirmed'))
                    s.add(alert);counts['new_alerts']+=1
                links.append((alert,item))
            await s.flush()
            s.add_all([RiskOccurrence(alert_id=a.id,item_id=i.id) for a,i in links])
        if current_batch:
            current_batch.counts=counts;current_batch.status='succeeded';current_batch.ended_at=beijing_now()
            attempt=(await s.scalars(select(RiskBatchAttempt).where(RiskBatchAttempt.batch_id==batch_id, RiskBatchAttempt.number==current_batch.attempt))).one()
            attempt.status='succeeded';attempt.ended_at=beijing_now()
            if more:
                last=rows[-1]
                s.add(RiskBatch(run_id=run_id,company=current_batch.company,day=current_batch.day,page=current_batch.page+1,
                    cursor=dict(event_time=last['event_time'],source_id=last['source_id'],is_null=int(last.get('in_monthly_plan') is None),monthly=last.get('in_monthly_plan') or '')))
            await s.flush()
            from app.services.risk_jobs import summarize
            await summarize(s, run)
        else:
            run.counts=counts;run.status='succeeded';run.stage='运行完成';run.ended_at=beijing_now()
        await s.commit()
        # 仅在本地事务提交后输出完成信息，避免把回滚结果记为成功。
        logger.info('结果已提交 run=%s batch=%s 扫描=%s 命中=%s 新增预警=%s 父任务状态=%s 进度=%s',
                    run_id,batch_id,counts.get('scanned',0),counts.get('hit',0),
                    counts.get('new_alerts',0),run.status,run.stage)

async def _worker_loop():
    from app.services.risk_jobs import worker_loop
    await worker_loop()


async def worker():
    """独立后台进程遇到暂时故障后恢复；取消信号正常退出。"""
    while True:
        try:
            await _worker_loop()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('风险运行器暂时中断，2秒后重新取得租约')
            await asyncio.sleep(2)
