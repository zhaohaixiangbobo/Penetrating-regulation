"""管理员计划管理：版本校验、修订留痕、触发预览和立即执行。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.risk import guard, dump, get_or_404
from app.deps import Principal
from app.core.config import get_settings
from app.db.sqlite import get_sqlite_session
from app.models.clue import beijing_now
from app.models.risk import RiskSchedule, RiskScheduleRevision, RiskTrigger, RiskVersion, RiskModel, RiskLease
from app.schemas.risk import ScheduleRequest
from app.services.risk_schedule import next_fire, scope_for, enqueue

router=APIRouter(prefix='/api/risk',tags=['risk schedules'])


async def check(s, body):
    version=await get_or_404(s,RiskVersion,body.version_id)
    model=await get_or_404(s,RiskModel,version.model_id)
    if not version.published or not model.enabled: raise HTTPException(422,'请选择已启用模型的已发布版本')
    if body.enabled and not get_settings().RISK_SOURCE_KEY_VERIFIED: raise HTTPException(409,'源事件键尚未核实，可先保存暂停的计划')


@router.get('/worker',dependencies=[Depends(guard)])
async def worker_state(s:AsyncSession=Depends(get_sqlite_session)):
    import time
    lease=await s.get(RiskLease,1)
    settings=get_settings()
    return dict(alive=bool(lease and lease.expires>time.time()),schedule_enabled=settings.RISK_SCHEDULE_ENABLED,
                run_enabled=settings.RISK_RUN_ENABLED,source_key_verified=settings.RISK_SOURCE_KEY_VERIFIED,data_cutoff='数据水位未知')


@router.get('/schedules',dependencies=[Depends(guard)])
async def listing(name:str|None=None,enabled:bool|None=None,version_id:int|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=200),s:AsyncSession=Depends(get_sqlite_session)):
    filters=[]
    if name: filters.append(RiskSchedule.name.contains(name.strip(),autoescape=True))
    if enabled is not None: filters.append(RiskSchedule.enabled==enabled)
    if version_id is not None: filters.append(func.json_extract(RiskSchedule.config,'$.version_id')==version_id)
    rows=(await s.scalars(select(RiskSchedule).where(*filters).order_by(RiskSchedule.id.desc()).offset((page-1)*page_size).limit(page_size))).all()
    return dict(total=await s.scalar(select(func.count()).select_from(RiskSchedule).where(*filters)),items=[dump(r) for r in rows])


@router.post('/schedules/preview',dependencies=[Depends(guard)])
async def preview(body:ScheduleRequest):
    result=[];current=beijing_now();config=body.model_dump()
    for _ in range(5):
        current=next_fire(config,current);result.append(dict(fire_at=current.isoformat(),**scope_for(config,current)))
    return result


@router.post('/schedules')
async def create(body:ScheduleRequest,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    await check(s,body);config=body.model_dump(exclude={'revision','enabled','name'})
    plan=RiskSchedule(name=body.name,enabled=body.enabled,config=config,next_fire=next_fire(config,beijing_now()),updated_by=p.username)
    s.add(plan);await s.flush()
    s.add(RiskScheduleRevision(schedule_id=plan.id,revision=1,snapshot=body.model_dump(),actor=p.username))
    await s.commit();return dump(plan)


@router.put('/schedules/{plan_id}')
async def edit(plan_id:int,body:ScheduleRequest,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    await check(s,body);plan=await get_or_404(s,RiskSchedule,plan_id)
    config=body.model_dump(exclude={'revision','enabled','name'})
    # CAS 使并发编辑与后台暂停不会互相覆盖。
    revision=plan.revision+1
    changed=await s.execute(update(RiskSchedule).where(RiskSchedule.id==plan_id,RiskSchedule.revision==body.revision).values(
        name=body.name,enabled=body.enabled,revision=revision,config=config,next_fire=next_fire(config,beijing_now()),updated_by=p.username,updated_at=beijing_now(),note=None))
    if not changed.rowcount: raise HTTPException(409,'计划已更新，请刷新重试')
    s.add(RiskScheduleRevision(schedule_id=plan_id,revision=revision,snapshot=body.model_dump(),actor=p.username))
    await s.commit();await s.refresh(plan);return dump(plan)


@router.post('/schedules/{plan_id}/run')
async def run_now(plan_id:int,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    plan=await get_or_404(s,RiskSchedule,plan_id)
    try: run=await enqueue(s,plan.config,p.username,beijing_now(),source='schedule_manual',schedule_id=plan.id,revision=plan.revision)
    except ValueError as exc: raise HTTPException(409,str(exc))
    await s.commit();return dump(run)


@router.get('/schedules/{plan_id}/history',dependencies=[Depends(guard)])
async def history(plan_id:int,s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,RiskSchedule,plan_id)
    revisions=(await s.scalars(select(RiskScheduleRevision).where(RiskScheduleRevision.schedule_id==plan_id).order_by(RiskScheduleRevision.id.desc()).limit(100))).all()
    triggers=(await s.scalars(select(RiskTrigger).where(RiskTrigger.schedule_id==plan_id).order_by(RiskTrigger.fire_at.desc()).limit(100))).all()
    return dict(revisions=[dump(r) for r in revisions],triggers=[dump(r) for r in triggers])
