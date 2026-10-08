"""风险模块管理员试点接口：版本、运行、预警、证据、核查和统计。"""
import uuid
from typing import Literal
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings, UPLOAD_DIR, ALLOWED_UPLOAD_EXTS, MAX_UPLOAD_MB
from app.db.sqlite import get_sqlite_session
from app.deps import require_admin, get_current_principal, Principal
from app.models.clue import AuditClue, beijing_now
from app.models.risk import RiskModel, RiskVersion, RiskRun, RiskItem, RiskAlert, RiskOccurrence, RiskAction, RiskClueLink, RiskAttachment, RiskBatch, RiskBatchAttempt
from app.schemas.risk import CreateModel, ModelConfig, RunRequest, ActionRequest
from app.services.risk_rules import INDICATORS

router=APIRouter(prefix='/api/risk',tags=['risk'])

async def guard(principal: Principal=Depends(require_admin)):
    if not get_settings().RISK_MODULE_ENABLED:
        raise HTTPException(404,'风险模块已停用')
    return principal

def dump(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns}

async def get_or_404(s, cls, key):
    row=await s.get(cls,key)
    if row is None: raise HTTPException(404,'记录不存在')
    return row

async def paged(s, cls, conditions, page, page_size):
    total=await s.scalar(select(func.count()).select_from(cls).where(*conditions))
    # UUID仅作标识，运行列表按触发时间展示，避免随机编号打乱最近任务。
    ordering=[cls.created_at.desc(),cls.id.desc()] if cls is RiskRun else [cls.id.desc()]
    rows=(await s.scalars(select(cls).where(*conditions).order_by(*ordering).offset((page-1)*page_size).limit(page_size))).all()
    return dict(total=total,page=page,page_size=page_size,items=[dump(r) for r in rows])

@router.get('/capabilities')
async def capabilities(p:Principal=Depends(get_current_principal)):
    return dict(enabled=get_settings().RISK_MODULE_ENABLED and p.is_admin,
        run_enabled=get_settings().RISK_RUN_ENABLED and p.is_admin,admin_only=True,scheduled=get_settings().RISK_SCHEDULE_ENABLED)

@router.get('/indicators',dependencies=[Depends(guard)])
async def indicators(): return INDICATORS

@router.get('/models',dependencies=[Depends(guard)])
async def models(s:AsyncSession=Depends(get_sqlite_session)):
    all_models=(await s.scalars(select(RiskModel).order_by(RiskModel.id))).all()
    versions=(await s.scalars(select(RiskVersion).order_by(RiskVersion.number.desc()))).all()
    return [dict(**dump(m),versions=[dump(v) for v in versions if v.model_id==m.id]) for m in all_models]

@router.post('/models')
async def create_model(body:CreateModel,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    m=RiskModel(name=body.name.strip())
    if not m.name: raise HTTPException(422,'请输入模型名称')
    s.add(m);await s.flush()
    v=RiskVersion(model_id=m.id,number=1,config=body.config.model_dump(),created_by=p.username)
    s.add(v);await s.commit();await s.refresh(v)
    return dump(v)

@router.get('/model-versions',dependencies=[Depends(guard)])
async def model_versions(model_name:str|None=None,published:bool|None=None,enabled:bool|None=None,
    version_number:int|None=Query(None,ge=1),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=200),
    s:AsyncSession=Depends(get_sqlite_session)):
    """先筛选再分页；版本数量独立统计，筛选草稿也可对比已发布版本。"""
    filters=[]
    if model_name and model_name.strip(): filters.append(RiskModel.name.contains(model_name.strip(),autoescape=True))
    if published is not None: filters.append(RiskVersion.published==published)
    if enabled is not None: filters.append(RiskModel.enabled==enabled)
    if version_number is not None: filters.append(RiskVersion.number==version_number)
    joined=select(RiskVersion,RiskModel).join(RiskModel,RiskModel.id==RiskVersion.model_id).where(*filters)
    total=await s.scalar(select(func.count()).select_from(joined.subquery()))
    rows=(await s.execute(joined.order_by(RiskModel.id.desc(),RiskVersion.number.desc())
        .offset((page-1)*page_size).limit(page_size))).all()
    ids={m.id for _,m in rows}
    counts=dict((await s.execute(select(RiskVersion.model_id,func.count()).where(RiskVersion.model_id.in_(ids))
        .group_by(RiskVersion.model_id))).all()) if ids else {}
    return dict(total=total,items=[dict(**dump(v),model_name=m.name,enabled=m.enabled,version_count=counts[m.id]) for v,m in rows])

@router.get('/models/{model_id}/versions',dependencies=[Depends(guard)])
async def versions_for_model(model_id:int,s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,RiskModel,model_id)
    return [dump(v) for v in (await s.scalars(select(RiskVersion).where(RiskVersion.model_id==model_id)
        .order_by(RiskVersion.number.desc()))).all()]

@router.post('/models/{model_id}/versions')
async def new_version(model_id:int,body:ModelConfig,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,RiskModel,model_id)
    number=(await s.scalar(select(func.max(RiskVersion.number)).where(RiskVersion.model_id==model_id)) or 0)+1
    v=RiskVersion(model_id=model_id,number=number,config=body.model_dump(),created_by=p.username)
    s.add(v)
    try: await s.commit()
    except IntegrityError:
        await s.rollback();raise HTTPException(409,'版本已被其他操作新增，请刷新后重试')
    await s.refresh(v);return dump(v)

@router.post('/versions/{version_id}/publish')
async def publish(version_id:int,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    v=await get_or_404(s,RiskVersion,version_id)
    ModelConfig.model_validate(v.config)
    if not v.published:
        v.published=True;v.published_at=beijing_now();await s.commit()
    return dict(id=v.id,published=True)

@router.post('/models/{model_id}/enabled')
async def enable(model_id:int,enabled:bool,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    m=await get_or_404(s,RiskModel,model_id);m.enabled=enabled;await s.commit()
    return dict(enabled=enabled)

@router.post('/runs')
async def create_run(body:RunRequest,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    if not get_settings().RISK_RUN_ENABLED: raise HTTPException(409,'当前已暂停模型运行')
    v=await get_or_404(s,RiskVersion,body.version_id)
    m=await get_or_404(s,RiskModel,v.model_id)
    if not m.enabled: raise HTTPException(409,'该模型已停用')
    if body.mode=='formal' and not v.published: raise HTTPException(422,'正式运行需使用已发布版本')
    if body.mode=='formal' and not get_settings().RISK_SOURCE_KEY_VERIFIED:
        raise HTTPException(409,'源事件键尚未核实，正式运行暂不可用；可先试算')
    if await s.scalar(select(func.count()).select_from(RiskRun).where(RiskRun.status.in_(['queued','running'])))>=get_settings().RISK_MAX_PENDING_RUNS:
        raise HTTPException(409,'任务积压达到上限，请稍后重试')
    baseline=None
    if body.mode=='compare':
        b=await get_or_404(s,RiskVersion,body.baseline_version_id)
        if b.model_id!=m.id: raise HTTPException(422,'基准与候选必须属于同一模型')
        baseline=b.config
    run=RiskRun(id=str(uuid.uuid4()),model_id=m.id,version_id=v.id,model_name=m.name,version_number=v.number,
        mode=body.mode,snapshot=v.config,baseline=baseline,scope=dict(start_date=str(body.start_date),
        end_date=str(body.end_date),com_ids=list(dict.fromkeys(body.com_ids)),baseline_version_id=body.baseline_version_id,batch_size=get_settings().RISK_BATCH_SIZE,source='manual',data_cutoff='数据水位未知'),created_by=p.username)
    s.add(run);await s.flush()
    from app.services.risk_jobs import make_batches
    await make_batches(s,run)
    await s.commit();await s.refresh(run)
    return dump(run)

@router.get('/runs',dependencies=[Depends(guard)])
async def runs(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=200),model_name:str|None=None,
    version_number:int|None=Query(None,ge=1),mode:Literal['trial','formal','compare']|None=None,
    status:Literal['queued','running','succeeded','failed','partial_failed','cancelled']|None=None,s:AsyncSession=Depends(get_sqlite_session)):
    filters=[]
    if model_name and model_name.strip(): filters.append(RiskRun.model_name.contains(model_name.strip(),autoescape=True))
    if version_number is not None: filters.append(RiskRun.version_number==version_number)
    if mode is not None: filters.append(RiskRun.mode==mode)
    if status is not None: filters.append(RiskRun.status==status)
    return await paged(s,RiskRun,filters,page,page_size)

@router.get('/runs/{run_id}',dependencies=[Depends(guard)])
async def run_detail(run_id:str,s:AsyncSession=Depends(get_sqlite_session)):
    return dump(await get_or_404(s,RiskRun,run_id))

@router.post('/runs/{run_id}/cancel',dependencies=[Depends(guard)])
async def cancel(run_id:str,s:AsyncSession=Depends(get_sqlite_session)):
    r=await get_or_404(s,RiskRun,run_id)
    await s.execute(update(RiskRun).where(RiskRun.id==run_id,RiskRun.status.in_(['queued','running'])).values(cancel_requested=True))
    await s.execute(update(RiskRun).where(RiskRun.id==run_id,RiskRun.status=='queued').values(status='cancelled',stage='已取消',ended_at=beijing_now()))
    await s.execute(update(RiskBatch).where(RiskBatch.run_id==run_id,RiskBatch.status.in_(['queued','retry_wait'])).values(status='cancelled',ended_at=beijing_now()))
    await s.refresh(r)
    if r.cancel_requested:
        from app.services.risk_jobs import summarize
        await summarize(s,r)
    await s.commit();await s.refresh(r);return dump(r)

@router.get('/runs/{run_id}/batches',dependencies=[Depends(guard)])
async def batch_list(run_id:str,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=200),s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,RiskRun,run_id)
    return await paged(s,RiskBatch,[RiskBatch.run_id==run_id],page,page_size)

@router.get('/batches/{batch_id}/attempts',dependencies=[Depends(guard)])
async def attempts(batch_id:int,s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,RiskBatch,batch_id)
    return [dump(r) for r in (await s.scalars(select(RiskBatchAttempt).where(RiskBatchAttempt.batch_id==batch_id).order_by(RiskBatchAttempt.number))).all()]

@router.post('/runs/{run_id}/retry',dependencies=[Depends(guard)])
async def retry_failed(run_id:str,s:AsyncSession=Depends(get_sqlite_session)):
    if not get_settings().RISK_RUN_ENABLED: raise HTTPException(409,'当前已暂停模型运行')
    r=await get_or_404(s,RiskRun,run_id)
    if r.mode=='formal' and not get_settings().RISK_SOURCE_KEY_VERIFIED: raise HTTPException(409,'请先核实源事件键')
    changed=await s.execute(update(RiskRun).where(RiskRun.id==run_id,RiskRun.status.in_(['failed','partial_failed'])).values(status='queued',error=None,ended_at=None,cancel_requested=False,stage='等待失败批次补跑'))
    if not changed.rowcount: raise HTTPException(409,'只可补跑失败或部分失败的任务')
    rows=await s.execute(update(RiskBatch).where(RiskBatch.run_id==run_id,RiskBatch.status=='failed').values(status='queued',retry_at=0,error=None,token=None))
    if not rows.rowcount: raise HTTPException(409,'没有可补跑批次，历史任务请新建运行')
    await s.commit();await s.refresh(r);return dump(r)

@router.get('/runs/{run_id}/items',dependencies=[Depends(guard)])
async def run_items(run_id:str,kind:str='hit',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=200),s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,RiskRun,run_id)
    filters=[RiskItem.run_id==run_id]
    if kind in ['hit','clear','unknown']: filters.append(RiskItem.outcome==kind)
    elif kind=='new': filters.extend([RiskItem.outcome=='hit',RiskItem.baseline_outcome!='hit'])
    elif kind=='removed': filters.extend([RiskItem.outcome!='hit',RiskItem.baseline_outcome=='hit'])
    elif kind!='all': raise HTTPException(422,'结果分类无效')
    return await paged(s,RiskItem,filters,page,page_size)

@router.get('/alerts',dependencies=[Depends(guard)])
async def alerts(status:str|None=None,keyword:str|None=None,com_id:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=200),s:AsyncSession=Depends(get_sqlite_session)):
    filters=[]
    if status: filters.append(RiskAlert.status==status)
    if com_id: filters.append(RiskAlert.com_id==com_id)
    if keyword: filters.append(RiskAlert.cust_name.contains(keyword,autoescape=True)|RiskAlert.cust_code.contains(keyword,autoescape=True))
    return await paged(s,RiskAlert,filters,page,page_size)

@router.get('/alerts/{alert_id}',dependencies=[Depends(guard)])
async def alert_detail(alert_id:int,s:AsyncSession=Depends(get_sqlite_session)):
    alert=await get_or_404(s,RiskAlert,alert_id)
    first=await get_or_404(s,RiskItem,alert.first_item_id)
    run=await get_or_404(s,RiskRun,first.run_id)
    occurrences=(await s.scalars(select(RiskItem).join(RiskOccurrence,RiskOccurrence.item_id==RiskItem.id)
        .where(RiskOccurrence.alert_id==alert_id).order_by(RiskItem.id))).all()
    history=(await s.scalars(select(RiskAlert).where(RiskAlert.model_id==alert.model_id,
        RiskAlert.cust_code==alert.cust_code,RiskAlert.person_id==alert.person_id,RiskAlert.id!=alert_id)
        .order_by(RiskAlert.event_time.desc()).limit(20))).all()
    clues=(await s.scalars(select(AuditClue).join(RiskClueLink,RiskClueLink.clue_id==AuditClue.id)
        .where(RiskClueLink.alert_id==alert_id))).all()
    version_count=await s.scalar(select(func.count(func.distinct(RiskRun.version_id))).select_from(RiskOccurrence)
        .join(RiskItem,RiskItem.id==RiskOccurrence.item_id).join(RiskRun,RiskRun.id==RiskItem.run_id).where(RiskOccurrence.alert_id==alert_id))
    return dict(**dump(alert),historical_cross_version=bool(version_count>1),first_evidence=dump(first),first_run=dump(run),
        occurrences=[dump(o) for o in occurrences],history=[dump(h) for h in history],
        actions=[dump(a) for a in (await s.scalars(select(RiskAction).where(RiskAction.alert_id==alert_id).order_by(RiskAction.id))).all()],
        attachments=[dump(a) for a in (await s.scalars(select(RiskAttachment).where(RiskAttachment.alert_id==alert_id))).all()],
        clues=[dict(id=c.id,title=c.title,status=c.status) for c in clues])

@router.post('/alerts/{alert_id}/actions')
async def action(alert_id:int,body:ActionRequest,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    a=await get_or_404(s,RiskAlert,alert_id)
    if a.revision!=body.revision: raise HTTPException(409,'记录已更新，请刷新详情后重试')
    old=a.status;target=old;conclusion=a.conclusion
    if body.action=='start' and old=='pending': target='investigating'
    elif body.action=='conclude' and old=='investigating':
        if not body.conclusion: raise HTTPException(422,'请选择核查结论')
        conclusion=body.conclusion
        if conclusion in ['confirmed','data_quality']:
            if not body.measures or not body.measures.strip(): raise HTTPException(422,'请填写整改或数据修正要求')
            target='rectifying'
        elif conclusion=='insufficient': target='investigating'
        else: target='reviewing'
    elif body.action=='submit_rectification' and old=='rectifying': target='reviewing'
    elif body.action=='approve' and old=='reviewing':
        if p.username==a.assigned_to: raise HTTPException(403,'复核需由另一位管理员完成')
        target='closed'
    elif body.action=='return' and old=='reviewing': target='investigating'
    elif body.action=='reopen' and old=='closed': target='investigating'
    elif body.action=='supplement': pass
    else: raise HTTPException(422,'当前状态不能执行该操作')
    values=dict(status=target,conclusion=conclusion,revision=a.revision+1)
    if body.action in ['start','conclude','reopen']: values['assigned_to']=p.username
    if body.action=='approve': values.update(reviewed_by=p.username,closed_at=beijing_now())
    if body.action=='reopen': values.update(closed_at=None,reviewed_by=None)
    changed=await s.execute(update(RiskAlert).where(RiskAlert.id==alert_id,RiskAlert.revision==body.revision).values(**values))
    if changed.rowcount!=1: raise HTTPException(409,'记录已更新，请刷新后重试')
    s.add(RiskAction(alert_id=alert_id,action=body.action,from_status=old,to_status=target,
        conclusion=conclusion,note=body.note,measures=body.measures,actor=p.username))
    await s.commit();return dict(status=target,revision=body.revision+1)

@router.post('/alerts/{alert_id}/clues/{clue_id}',dependencies=[Depends(guard)])
async def link_clue(alert_id:int,clue_id:int,s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,RiskAlert,alert_id);await get_or_404(s,AuditClue,clue_id)
    from sqlalchemy.dialects.sqlite import insert
    await s.execute(insert(RiskClueLink).values(alert_id=alert_id,clue_id=clue_id).on_conflict_do_nothing())
    await s.commit();return dict(linked=True)

@router.get('/clues/{clue_id}/alerts',dependencies=[Depends(guard)])
async def linked_alerts(clue_id:int,s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,AuditClue,clue_id)
    return [dump(a) for a in (await s.scalars(select(RiskAlert).join(RiskClueLink,RiskClueLink.alert_id==RiskAlert.id).where(RiskClueLink.clue_id==clue_id))).all()]

RISK_UPLOAD=UPLOAD_DIR.parent/'risk'

@router.post('/alerts/{alert_id}/attachments')
async def upload(alert_id:int,file:UploadFile,p:Principal=Depends(guard),s:AsyncSession=Depends(get_sqlite_session)):
    await get_or_404(s,RiskAlert,alert_id)
    name=Path(file.filename or 'attachment').name
    suffix=Path(name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTS: raise HTTPException(422,'附件类型不支持')
    if await s.scalar(select(func.count()).select_from(RiskAttachment).where(RiskAttachment.alert_id==alert_id))>=5:
        raise HTTPException(422,'每条预警最多5个附件')
    data=await file.read(MAX_UPLOAD_MB*1024*1024+1)
    if len(data)>MAX_UPLOAD_MB*1024*1024: raise HTTPException(422,'附件超过10MB')
    RISK_UPLOAD.mkdir(parents=True,exist_ok=True)
    stored=uuid.uuid4().hex+suffix;path=RISK_UPLOAD/stored
    path.write_bytes(data)
    try:
        a=RiskAttachment(alert_id=alert_id,original_name=name,stored_name=stored,size=len(data),actor=p.username)
        s.add(a);await s.commit()
    except Exception:
        path.unlink(missing_ok=True);raise
    return dict(uploaded=True)

@router.get('/alerts/{alert_id}/attachments/{attachment_id}',dependencies=[Depends(guard)])
async def download(alert_id:int,attachment_id:int,s:AsyncSession=Depends(get_sqlite_session)):
    a=await get_or_404(s,RiskAttachment,attachment_id)
    path=(RISK_UPLOAD/a.stored_name).resolve()
    if a.alert_id!=alert_id or path.parent!=RISK_UPLOAD.resolve() or not path.is_file(): raise HTTPException(404,'附件不存在')
    return FileResponse(path,filename=a.original_name,media_type='application/octet-stream')

@router.get('/dashboard',dependencies=[Depends(guard)])
async def dashboard(s:AsyncSession=Depends(get_sqlite_session)):
    statuses=dict((await s.execute(select(RiskAlert.status,func.count()).group_by(RiskAlert.status))).all())
    conclusions=dict((await s.execute(select(RiskAlert.conclusion,func.count()).where(RiskAlert.conclusion.is_not(None)).group_by(RiskAlert.conclusion))).all())
    models=(await s.execute(select(RiskAlert.model_name,func.count()).group_by(RiskAlert.model_name))).all()
    trends=(await s.execute(select(func.date(RiskAlert.first_seen),func.count()).group_by(func.date(RiskAlert.first_seen)).order_by(func.date(RiskAlert.first_seen).desc()).limit(30))).all()
    closed=await s.scalar(select(func.count()).select_from(RiskAlert).where(RiskAlert.status=='closed'))
    confirmed=await s.scalar(select(func.count()).select_from(RiskAlert).where(RiskAlert.status=='closed',RiskAlert.conclusion=='confirmed'))
    return dict(statuses=statuses,conclusions=conclusions,models=[dict(name=n,total=c) for n,c in models],
        trends=[dict(date=d,total=c) for d,c in reversed(trends)],closed=closed,confirmed=confirmed,
        confirmed_rate=round(confirmed/closed*100,1) if closed else None,
        failed_runs=await s.scalar(select(func.count()).select_from(RiskRun).where(RiskRun.status.in_(['failed','partial_failed']))))
