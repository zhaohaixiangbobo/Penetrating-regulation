"""持久批次队列：短事务领取、租约恢复、有限重试及父任务汇总。"""
import asyncio
import contextlib
import time
import uuid
from datetime import date, timedelta
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from app.core.config import get_settings
from app.db.sqlite import get_sessionmaker
from app.models.clue import beijing_now
from app.models.risk import RiskRun, RiskBatch, RiskBatchAttempt, RiskLease, RiskItem
from app.services import risk_engine


async def make_batches(s, run):
    """创建按公司/日期分区的首页；后续页随成功提交原子生成。"""
    start=date.fromisoformat(run.scope['start_date']); end=date.fromisoformat(run.scope['end_date'])
    for company in run.scope['com_ids']:
        for offset in range((end-start).days+1):
            s.add(RiskBatch(run_id=run.id,company=company,day=str(start+timedelta(days=offset)),page=1))
    total=len(run.scope['com_ids'])*((end-start).days+1)
    run.counts=dict(batches_total=total,batches=dict(queued=total,running=0,retry_wait=0,succeeded=0,failed=0,cancelled=0),data_cutoff='数据水位未知')


async def summarize(s, run):
    batches=(await s.scalars(select(RiskBatch).where(RiskBatch.run_id==run.id))).all()
    counts={key:0 for key in ['scanned','hit','clear','unknown','quality_unknown','new_alerts','existing_alerts','closed_rematches','new','removed','common','baseline_hit']}
    for b in batches:
        if b.status=='succeeded':
            for key in counts: counts[key]+=b.counts.get(key,0)
    counts['customers']=await s.scalar(select(func.count(func.distinct(func.json_extract(RiskItem.evidence,'$.cust_code')))).where(RiskItem.run_id==run.id,RiskItem.outcome=='hit'))
    counts['managers']=await s.scalar(select(func.count(func.distinct(func.json_extract(RiskItem.evidence,'$.person_id')))).where(RiskItem.run_id==run.id,RiskItem.outcome=='hit'))
    states={key:sum(b.status==key for b in batches) for key in ['queued','running','retry_wait','succeeded','failed','cancelled']}
    reads=[b.counts['read_at'] for b in batches if b.counts.get('read_at')]
    counts.update(batches_total=len(batches),batches=states,data_cutoff='数据水位未知',read_at=max(reads,default=''),read_started_at=min(reads,default=''))
    run.counts=counts
    active=sum(states[k] for k in ['queued','running','retry_wait'])
    if run.cancel_requested and not active: run.status='cancelled'
    elif active: run.status='running'
    elif states['failed']: run.status='partial_failed' if states['succeeded'] else 'failed'
    else: run.status='succeeded'
    run.stage=f"批次 {states['succeeded']}/{len(batches)} 成功，{states['failed']} 失败，{states['retry_wait']} 等待重试"
    if run.status in ['succeeded','partial_failed','failed','cancelled']: run.ended_at=beijing_now()


async def lock_owner(s, owner):
    return (await s.execute(update(RiskLease).where(RiskLease.id==1,RiskLease.owner==owner,RiskLease.expires>time.time()).values(expires=time.time()+20))).rowcount==1


async def cancel_batch(run_id,batch_id,token,owner):
    async with get_sessionmaker()() as s:
        if not await lock_owner(s,owner): return
        b=await s.get(RiskBatch,batch_id)
        if b.token!=token or b.status!='running': return
        r=await s.get(RiskRun,run_id)
        if r.cancel_requested:
            b.status='cancelled';b.ended_at=beijing_now()
            await s.execute(update(RiskBatch).where(RiskBatch.run_id==run_id,RiskBatch.status.in_(['queued','retry_wait'])).values(status='cancelled'))
        else:
            # 全局运行暂停时保留当前批次待恢复，而非伪装为取消成功。
            b.status='queued';b.token=None
        await s.execute(update(RiskBatchAttempt).where(RiskBatchAttempt.batch_id==batch_id,RiskBatchAttempt.number==b.attempt).values(status='cancelled' if r.cancel_requested else 'interrupted',ended_at=beijing_now()))
        await summarize(s,r);await s.commit()


async def recover(s):
    """仅租约所有者接管遗留批次；成功批次始终保留。"""
    stale=(await s.scalars(select(RiskBatch).where(RiskBatch.status=='running'))).all()
    for b in stale:
        b.status='queued';b.token=None;b.error='执行器中断，已恢复待执行'
        await s.execute(update(RiskBatchAttempt).where(RiskBatchAttempt.batch_id==b.id,RiskBatchAttempt.status=='running').values(status='interrupted',error=b.error,ended_at=beijing_now()))
    risk_engine.logger.info('恢复检查：发现 %s 个中断批次，恢复为待执行（事务提交后生效）', len(stale))
    # 兼容升级前已入队、尚未分批的父任务。
    runs=(await s.scalars(select(RiskRun).where(RiskRun.status.in_(['queued','running'])))).all()
    for r in runs:
        if not await s.scalar(select(func.count()).select_from(RiskBatch).where(RiskBatch.run_id==r.id)):
            if await s.scalar(select(func.count()).select_from(RiskItem).where(RiskItem.run_id==r.id)):
                r.status='failed';r.error='历史运行已有部分结果，请创建新任务核对';continue
            await make_batches(s,r)


async def process_one(owner):
    """返回是否领取到任务；源库读取发生在领取事务提交之后。"""
    async with get_sessionmaker()() as s:
        if not await lock_owner(s,owner): return False
        cancelled=(await s.scalars(select(RiskRun).where(RiskRun.cancel_requested==True,RiskRun.status.in_(['queued','running'])))).all()
        for r in cancelled:
            await s.execute(update(RiskBatch).where(RiskBatch.run_id==r.id,RiskBatch.status.in_(['queued','retry_wait'])).values(status='cancelled',ended_at=beijing_now()))
            await summarize(s,r)
        earliest=await s.scalar(select(RiskRun.id).where(RiskRun.status.in_(['queued','running']),RiskRun.cancel_requested==False).order_by(RiskRun.created_at,RiskRun.id).limit(1))
        b=(await s.scalars(select(RiskBatch).join(RiskRun,RiskRun.id==RiskBatch.run_id).where(RiskBatch.run_id==earliest,
            RiskBatch.status.in_(['queued','retry_wait']),RiskBatch.retry_at<=time.time(),
            RiskRun.status.in_(['queued','running']),RiskRun.cancel_requested==False)
            .order_by(RiskRun.created_at,RiskBatch.id).limit(1))).first()
        if not b: await s.commit();return False
        r=await s.get(RiskRun,b.run_id)
        if r.mode=='formal' and not get_settings().RISK_SOURCE_KEY_VERIFIED:
            r.status='failed';r.error='源事件键尚未核实，正式任务已暂停，请完成上线核对后补跑'
            await s.execute(update(RiskBatch).where(RiskBatch.run_id==r.id,RiskBatch.status.in_(['queued','retry_wait'])).values(status='failed',error=r.error))
            await summarize(s,r)
            await s.commit()
            risk_engine.logger.warning('正式任务停止 run=%s：源事件键尚未核实，请完成核实后补跑',r.id)
            return True
        b.status='running';b.attempt+=1;b.token=str(uuid.uuid4());b.started_at=beijing_now();b.error=None
        r.status='running';r.started_at=r.started_at or beijing_now();r.stage=f'正在计算 {b.company} / {b.day} / 第{b.page}页'
        s.add(RiskBatchAttempt(batch_id=b.id,number=b.attempt))
        batch_id,run_id,token=b.id,b.run_id,b.token
        await s.commit()
    started = time.monotonic()
    risk_engine.logger.info('领取批次 run=%s batch=%s 公司=%s 日期=%s 页=%s 尝试=%s，开始读取源库',
                            run_id, batch_id, b.company, b.day, b.page, b.attempt)
    try:
        await risk_engine.execute_run(run_id,owner,batch_id,token)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        risk_engine.logger.exception('批次失败 batch=%s',batch_id)
        async with get_sessionmaker()() as s:
            if not await lock_owner(s,owner): return True
            b=await s.get(RiskBatch,batch_id)
            if b.token!=token or b.status!='running': return True
            transient=not isinstance(exc,(ValueError,IntegrityError))
            b.status='retry_wait' if transient and b.attempt<3 else 'failed'
            b.error=str(exc) if isinstance(exc,ValueError) else '事件键或结果约束冲突，请核实源数据' if isinstance(exc,IntegrityError) else '源连接或计算失败，请查看后台日志'
            b.retry_at=time.time()+(60 if b.attempt==1 else 300);b.ended_at=beijing_now()
            await s.execute(update(RiskBatchAttempt).where(RiskBatchAttempt.batch_id==b.id,RiskBatchAttempt.number==b.attempt).values(status=b.status,error=b.error,ended_at=b.ended_at))
            await summarize(s,await s.get(RiskRun,run_id));await s.commit()
            risk_engine.logger.warning('批次处理失败 run=%s batch=%s 状态=%s 尝试=%s 重试等待秒=%s 耗时=%.2fs',
                run_id,batch_id,b.status,b.attempt,(60 if b.attempt==1 else 300) if b.status=='retry_wait' else 0,time.monotonic()-started)
    return True


async def worker_loop():
    owner=str(uuid.uuid4());lost=asyncio.Event();hb=None;scheduler=None
    try:
        last_wait = None
        while not await risk_engine.lease(owner):
            if last_wait is None or time.monotonic()-last_wait >= 60:
                risk_engine.logger.info('等待执行租约：其他后台正在持有租约，60 秒后仍等待则再次提示')
                last_wait = time.monotonic()
            await asyncio.sleep(2)
        risk_engine.logger.info('取得执行租约 owner=%s，开始恢复未完成任务', owner)
        hb=asyncio.create_task(risk_engine.heartbeat(owner,lost))
        async with get_sessionmaker()() as s:
            if not await lock_owner(s,owner): return
            await recover(s);await s.commit()
        from app.services.risk_schedule import tick
        async def scheduling():
            while not lost.is_set():
                settings=get_settings()
                try:
                    if settings.RISK_MODULE_ENABLED and settings.RISK_RUN_ENABLED and settings.RISK_SCHEDULE_ENABLED:
                        await tick(owner)
                except Exception:
                    risk_engine.logger.exception('计划调度暂时失败，将重试')
                await asyncio.sleep(2)
        scheduler=asyncio.create_task(scheduling())
        last_idle = None
        while not lost.is_set():
            settings=get_settings()
            if settings.RISK_MODULE_ENABLED and settings.RISK_RUN_ENABLED:
                if await process_one(owner): continue
            if last_idle is None or time.monotonic()-last_idle >= 60:
                risk_engine.logger.info('后台存活：%s；定时调度=%s',
                    '等待可执行批次（空队列或等待重试）' if settings.RISK_MODULE_ENABLED and settings.RISK_RUN_ENABLED else '模块或计算开关关闭，暂停领取任务',
                    settings.RISK_SCHEDULE_ENABLED)
                last_idle = time.monotonic()
            await asyncio.sleep(2)
    finally:
        if scheduler:
            scheduler.cancel()
            with contextlib.suppress(asyncio.CancelledError): await scheduler
        if hb:
            hb.cancel()
            with contextlib.suppress(asyncio.CancelledError): await hb
        async with get_sessionmaker()() as s:
            await s.execute(update(RiskLease).where(RiskLease.id==1,RiskLease.owner==owner).values(expires=0));await s.commit()
