"""北京时间计划计算、冻结快照与幂等触发；停机只补最近一轮并记录遗漏。"""
import uuid
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func
from app.core.config import get_settings
from app.models.clue import beijing_now
from app.db.sqlite import get_sessionmaker
from app.models.risk import RiskSchedule, RiskScheduleRevision, RiskTrigger, RiskRun, RiskModel, RiskVersion
from app.services.risk_jobs import make_batches, lock_owner


def next_fire(config, after):
    candidate=after.replace(hour=config['hour'],minute=config['minute'],second=0,microsecond=0)
    if candidate<=after: candidate+=timedelta(days=1)
    if config['frequency']=='weekly': candidate+=timedelta(days=(config['weekday']-candidate.weekday())%7)
    return candidate


def scope_for(config, fire_at):
    end=fire_at.date()-timedelta(days=1)
    return dict(start_date=str(end-timedelta(days=config['lookback_days']-1)),end_date=str(end),
                com_ids=config['com_ids'],batch_size=config['batch_size'])


async def enqueue(s, config, actor, fire_at, source='schedule', schedule_id=None, revision=None):
    settings=get_settings()
    if not settings.RISK_RUN_ENABLED: raise ValueError('当前已暂停模型运行')
    if not settings.RISK_SOURCE_KEY_VERIFIED: raise ValueError('源事件键尚未完成上线核实，自动正式运行暂不可启用')
    version=await s.get(RiskVersion,config['version_id'])
    model=await s.get(RiskModel,version.model_id) if version else None
    if not version or not version.published or not model or not model.enabled: raise ValueError('计划模型需启用且版本已发布')
    pending=await s.scalar(select(func.count()).select_from(RiskRun).where(RiskRun.status.in_(['queued','running'])))
    if pending>=settings.RISK_MAX_PENDING_RUNS: raise ValueError('待执行任务达到积压上限，请先处理已有任务')
    scope={**scope_for(config,fire_at),'source':source,'schedule_id':schedule_id,'schedule_revision':revision,
           'scheduled_fire_at':fire_at.isoformat(),'timezone':'Asia/Shanghai','schedule_snapshot':config,
           'source_key_policy':'plan_date/id/in_monthly_plan:v1','data_cutoff':'数据水位未知'}
    run=RiskRun(id=str(uuid.uuid4()),model_id=model.id,version_id=version.id,model_name=model.name,version_number=version.number,
                mode='formal',snapshot=version.config,scope=scope,created_by=actor)
    s.add(run);await s.flush();await make_batches(s,run)
    return run


async def tick(owner, now=None):
    now=now or beijing_now()
    messages=[]
    async with get_sessionmaker()() as s:
        if not await lock_owner(s,owner): return
        plans=(await s.scalars(select(RiskSchedule).where(RiskSchedule.enabled==True,RiskSchedule.next_fire<=now))).all()
        for plan in plans:
            config=plan.config
            latest=now.replace(hour=config['hour'],minute=config['minute'],second=0,microsecond=0)
            if latest>now: latest-=timedelta(days=1)
            if config['frequency']=='weekly': latest-=timedelta(days=(latest.weekday()-config['weekday'])%7)
            # 一条遗漏范围摘要即可保留停机证据，避免长时间停机生成成千上万行。
            if plan.next_fire<latest:
                if not await s.scalar(select(RiskTrigger.id).where(RiskTrigger.schedule_id==plan.id,RiskTrigger.fire_at==plan.next_fire)):
                    s.add(RiskTrigger(schedule_id=plan.id,revision=plan.revision,fire_at=plan.next_fire,status='missed',
                        note=f'停机遗漏区间 {plan.next_fire.isoformat()} 至 {latest.isoformat()}（不含末次），请按需补算'))
            if not await s.scalar(select(RiskTrigger.id).where(RiskTrigger.schedule_id==plan.id,RiskTrigger.fire_at==latest)):
                try:
                    run=await enqueue(s,config,f'schedule:{plan.id}',latest,schedule_id=plan.id,revision=plan.revision)
                    s.add(RiskTrigger(schedule_id=plan.id,revision=plan.revision,fire_at=latest,status='queued',run_id=run.id))
                    messages.append(f'定时计划已入队 schedule={plan.id} revision={plan.revision} run={run.id} 计划时间={latest}')
                    plan.note=None
                except ValueError as exc:
                    plan.enabled=False;plan.note=str(exc);plan.revision+=1;plan.updated_by='system';plan.updated_at=now
                    messages.append(f'定时计划已暂停 schedule={plan.id} 原因={exc}')
                    s.add(RiskScheduleRevision(schedule_id=plan.id,revision=plan.revision,snapshot={**config,'enabled':False,'reason':str(exc)},actor='system'))
                    s.add(RiskTrigger(schedule_id=plan.id,revision=plan.revision,fire_at=latest,status='blocked',note=str(exc)))
            plan.next_fire=next_fire(config,latest)
        await s.commit()
        for message in messages:
            logging.getLogger('shenji.risk').info(message)
