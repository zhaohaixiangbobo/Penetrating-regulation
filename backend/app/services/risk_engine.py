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
from app.models.risk import RiskModel, RiskVersion, RiskRun, RiskItem, RiskAlert, RiskOccurrence, RiskLease
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
    """按已核对的源主键(id,plan_date,in_monthly_plan)读取；字典先归一，避免关联扩行。"""
    keys = ','.join(f':company_{i}' for i in range(len(scope['com_ids'])))
    params = {f'company_{i}':v for i,v in enumerate(scope['com_ids'])}
    params.update(start=scope['start_date'], end=scope['end_date'], cap=MAX_EVENTS+1)
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
 DATE_FORMAT(a.plan_date,'%Y-%m-%d %H:%i:%s') event_time,
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
SELECT * FROM source ORDER BY event_time, source_id, in_monthly_plan LIMIT :cap
"""
    async with StarSession() as s:
        await s.execute(text('SET query_timeout=30'))
        rows = (await asyncio.wait_for(s.execute(text(sql),params),40)).mappings().all()
    if len(rows)>MAX_EVENTS:
        raise ValueError('范围超过5000次拜访，请缩小日期或公司范围后运行；本次结果未发布')
    return [dict(r) for r in rows]

def normalize(row):
    """只将已验证可用的数据用于判断，证据另保留原始字段。"""
    data = {k:float(v) if isinstance(v,Decimal) else v for k,v in row.items()}
    if not data.get('source_id') or not data.get('event_time'):
        raise ValueError('拜访源键缺失，无法可靠去重；请先核对源数据')
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
        if not await lease(owner):
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

async def execute_run(run_id, owner):
    async with get_sessionmaker()() as s:
        run = await s.get(RiskRun,run_id)
        scope, config, baseline, mode = run.scope, run.snapshot, run.baseline, run.mode
    rows = await fetch_events(scope)
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
        items.append(RiskItem(run_id=run_id,event_key=key,outcome=outcome,baseline_outcome=old,evidence=data,reasons=reasons))
    counts.update(customers=len(customers-{None}),managers=len(managers-{None}))
    if not await allowed(run_id,owner):
        await finish_error(run_id,owner,'cancelled','任务已取消或运行开关关闭')
        return
    async with get_sessionmaker()() as s:
        # 原子发布：先取得写锁并校验租约，再次读取取消状态；失败则整批回滚。
        lock=await s.execute(update(RiskLease).where(RiskLease.id==1,RiskLease.owner==owner,
            RiskLease.expires>time.time()).values(expires=time.time()+60))
        if not lock.rowcount: return
        run=await s.get(RiskRun,run_id)
        if run.cancel_requested or run.status!='running':
            run.status='cancelled';run.stage='已取消';run.ended_at=beijing_now()
            await s.commit();return
        s.add_all(items)
        await s.flush()
        if mode=='formal':
            for item in items:
                if item.outcome!='hit': continue
                alert=(await s.execute(select(RiskAlert).where(RiskAlert.model_id==run.model_id,RiskAlert.event_key==item.event_key))).scalar_one_or_none()
                if alert:
                    counts['existing_alerts']+=1
                    counts['closed_rematches']+=int(alert.status=='closed')
                    alert.latest_item_id=item.id;alert.last_seen=beijing_now()
                else:
                    d=item.evidence
                    prior=(await s.execute(select(RiskAlert).where(RiskAlert.model_id==run.model_id,
                        RiskAlert.cust_code==d.get('cust_code'),RiskAlert.person_id==d.get('person_id'),
                        RiskAlert.status=='closed',RiskAlert.closed_at<__import__('datetime').datetime.fromisoformat(d['event_time']))
                        .order_by(RiskAlert.closed_at.desc()).limit(1))).scalar_one_or_none()
                    alert=RiskAlert(model_id=run.model_id,model_name=run.model_name,event_key=item.event_key,
                        first_item_id=item.id,latest_item_id=item.id,cust_code=d.get('cust_code'),cust_name=d.get('cust_name'),
                        person_id=d.get('person_id'),person_name=d.get('person_name'),com_id=d.get('com_id'),
                        short_name=d.get('short_name'),event_time=d['event_time'],prior_alert_id=prior.id if prior else None,
                        recurrence=bool(prior and prior.conclusion=='confirmed'))
                    s.add(alert);await s.flush();counts['new_alerts']+=1
                s.add(RiskOccurrence(alert_id=alert.id,item_id=item.id))
        run.counts=counts;run.status='succeeded';run.stage='运行完成';run.ended_at=beijing_now()
        await s.commit()

async def _worker_loop():
    """租约到期才能接管，重启遗留任务明确失败，重试由用户发起。"""
    owner=str(uuid.uuid4())
    current=None
    try:
        while True:
            if not get_settings().RISK_RUN_ENABLED or not await lease(owner):
                await asyncio.sleep(2);continue
            async with get_sessionmaker()() as s:
                # 拿到全局租约后，残留 running 任务来自已退出的旧运行器。
                await s.execute(update(RiskRun).where(RiskRun.status=='running').values(status='failed',
                    error='运行器中断，结果未发布，请重新运行',stage='运行中断',ended_at=beijing_now()))
                run=(await s.execute(select(RiskRun).where(RiskRun.status=='queued').order_by(RiskRun.created_at).limit(1))).scalar_one_or_none()
                if run:
                    run.status='running';run.stage='正在读取并计算拜访指标（最多5000条）';run.started_at=beijing_now();current=run.id
                await s.commit()
            if not current:
                await asyncio.sleep(2);continue
            lost=asyncio.Event();hb=asyncio.create_task(heartbeat(owner,lost))
            try:
                await execute_run(current,owner)
            except asyncio.CancelledError:
                await finish_error(current,owner,'failed','服务停止，运行未完成，请重新运行')
                raise
            except Exception as exc:
                logger.exception('risk run failed %s',current)
                # 数据库驱动原始异常可能包含连接细节，只在服务日志记录。
                detail=str(exc) if isinstance(exc,ValueError) else '计算失败，请检查数据连接或服务日志后重试'
                await finish_error(current,owner,'failed',detail)
            finally:
                hb.cancel()
                with contextlib.suppress(asyncio.CancelledError): await hb
                current=None
    finally:
        async with get_sessionmaker()() as s:
            await s.execute(update(RiskLease).where(RiskLease.id==1,RiskLease.owner==owner).values(expires=0))
            await s.commit()

async def worker():
    """短暂连接故障后恢复取任务，防止后台任务静默退出而永久积压队列。"""
    while True:
        try:
            await _worker_loop()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('风险运行器暂时中断，2秒后重新取得租约')
            await asyncio.sleep(2)
