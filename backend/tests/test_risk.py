"""风险一期最小验证：规则边界、同批对比、版本、权限、去重、取消和核查闭环。"""
import asyncio
import time
import uuid
import pytest
from sqlalchemy import select, update, func
from app.core.config import get_settings
from app.db.sqlite import get_sessionmaker
from app.models.risk import RiskAlert, RiskItem, RiskLease, RiskRun, RiskVersion
from app.schemas.risk import ModelConfig
from app.services import risk_engine
from app.services.risk_rules import DEFAULT_CONFIG, evaluate

@pytest.mark.parametrize('duration,distance,outcome', [(38,438,'hit'),(60,438,'clear'),(38,200,'clear'),(None,438,'unknown'),(38,None,'unknown'),(100,None,'clear')])
def test_rule_boundaries(duration,distance,outcome):
    assert evaluate(DEFAULT_CONFIG,dict(visit_duration_seconds=duration,visit_location_distance_meters=distance))[0]==outcome

def test_any_and_n_unknown():
    values=dict(visit_duration_seconds=38,visit_location_distance_meters=None)
    assert evaluate({**DEFAULT_CONFIG,'combination':'ANY'},values)[0]=='hit'
    assert evaluate({**DEFAULT_CONFIG,'combination':'AT_LEAST_N','minimum':2},values)[0]=='unknown'
    with pytest.raises(ValueError):
        ModelConfig.model_validate({**DEFAULT_CONFIG,'combination':'AT_LEAST_N','conditions':[DEFAULT_CONFIG['conditions'][0]]*2})
    # 从N项切换回任一满足时，隐藏的旧minimum不影响单项规则。
    assert ModelConfig.model_validate({**DEFAULT_CONFIG,'combination':'ANY','minimum':2,'conditions':[DEFAULT_CONFIG['conditions'][0]]}).combination=='ANY'

def test_nullable_source_key():
    row=event('nullable')
    row['in_monthly_plan']=None
    key,_,_=risk_engine.normalize(row)
    assert key.endswith('null]')

@pytest.mark.asyncio
async def test_model_and_run_filters(client,auth_header,enabled):
    await risk_engine.bootstrap()
    # 两个版本分属发布/草稿，验证false筛选、总数、分页和完整基准列表。
    first=(await client.post('/api/risk/models',headers=auth_header,json={'name':'筛选验证%模型','config':DEFAULT_CONFIG})).json()
    mid,vid=first['model_id'],first['id']
    await client.post(f'/api/risk/versions/{vid}/publish',headers=auth_header)
    v2=(await client.post(f'/api/risk/models/{mid}/versions',headers=auth_header,json=DEFAULT_CONFIG)).json()
    async def listing(**params):
        response=await client.get('/api/risk/model-versions',headers=auth_header,params=params)
        assert response.status_code==200,response.text
        return response.json()
    all_rows=await listing(model_name='筛选验证%',page_size=1,page=2)
    assert all_rows['total']==2 and all_rows['items'][0]['id']==vid
    draft=await listing(model_name='筛选验证%',published='false',version_number=2,enabled='true')
    assert draft['total']==1 and draft['items'][0]['id']==v2['id'] and draft['items'][0]['version_count']==2
    assert len((await client.get(f'/api/risk/models/{mid}/versions',headers=auth_header)).json())==2
    body=dict(version_id=vid,mode='formal',start_date='2024-01-02',end_date='2024-01-02',com_ids=['11120101'])
    run=(await client.post('/api/risk/runs',headers=auth_header,json=body)).json()
    await client.post('/api/risk/runs/'+run['id']+'/cancel',headers=auth_header)
    await client.post('/api/risk/runs',headers=auth_header,json={**body,'version_id':v2['id'],'mode':'trial'})
    result=await client.get('/api/risk/runs',headers=auth_header,params=dict(model_name='筛选验证%',mode='formal',status='cancelled',version_number=1))
    assert result.json()['total']==1 and result.json()['items'][0]['id']==run['id']
    assert (await client.get('/api/risk/runs',headers=auth_header,params=dict(model_name='筛选验证%',status='succeeded'))).json()['total']==0
    await client.post(f'/api/risk/models/{mid}/enabled',headers=auth_header,params={'enabled':'false'})
    assert (await listing(model_name='筛选验证%',enabled='false'))['total']==2
    assert (await listing(model_name='不存在的筛选模型'))['total']==0
    assert (await client.get('/api/risk/runs',headers=auth_header,params={'status':'invalid'})).status_code==422

@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(get_settings(),'RISK_MODULE_ENABLED',True)
    monkeypatch.setattr(get_settings(),'RISK_RUN_ENABLED',True)
    monkeypatch.setattr(get_settings(),'RISK_SOURCE_KEY_VERIFIED',True)

@pytest.mark.asyncio
async def test_alert_company_filter_and_multi_action(client,auth_header,user_header,enabled,monkeypatch):
    """公司条件先过滤再分页；多条处置各自留痕，冲突项独立失败。"""
    await risk_engine.bootstrap()
    version=(await client.post('/api/risk/models',headers=auth_header,json={'name':'公司筛选与批量处置','config':DEFAULT_CONFIG})).json()
    await client.post(f"/api/risk/versions/{version['id']}/publish",headers=auth_header)
    run=(await client.post('/api/risk/runs',headers=auth_header,json=dict(version_id=version['id'],mode='formal',start_date='2024-01-02',end_date='2024-01-02',com_ids=['11120101','11120102']))).json()
    rows=[{**event(f'batch-{i}'), 'cust_name':'批量专用客户', 'com_id':company} for i,company in enumerate(['11120101','11120102','11120101'])]
    await process(run['id'],monkeypatch,rows)
    response=await client.get('/api/risk/alerts',headers=auth_header,params={'com_id':'11120101','keyword':'批量专用客户','status':'pending','page_size':1})
    assert response.status_code==200 and response.json()['total']==2 and len(response.json()['items'])==1
    second=(await client.get('/api/risk/alerts',headers=auth_header,params={'com_id':'11120102','keyword':'批量专用客户'})).json()
    assert second['total']==1 and second['items'][0]['com_id']=='11120102'
    assert (await client.get('/api/risk/alerts',headers=auth_header,params={'com_id':'不存在的公司'})).json()['total']==0
    assert (await client.get('/api/risk/alerts',headers=user_header)).status_code==403
    selected=(await client.get('/api/risk/alerts',headers=auth_header,params={'keyword':'批量专用客户'})).json()['items']
    payload=dict(action='start',note='批量开始核查')
    # 第一项提前更新，模拟用户勾选后他人处理；其余项仍独立成功。
    first=selected[0]
    await client.post(f"/api/risk/alerts/{first['id']}/actions",headers=auth_header,json={**payload,'revision':first['revision']})
    codes=[]
    for row in selected:
        result=await client.post(f"/api/risk/alerts/{row['id']}/actions",headers=auth_header,json={**payload,'revision':row['revision']})
        codes.append(result.status_code)
    assert codes==[409,200,200]
    for row in selected:
        detail=(await client.get(f"/api/risk/alerts/{row['id']}",headers=auth_header)).json()
        assert detail['status']=='investigating' and len(detail['actions'])==1

def event(key,seconds=38,distance=438):
    return dict(source_id=key,in_monthly_plan='1',event_time='2024-01-02 10:00:00',cust_code='test-customer',cust_name='测试客户',
        person_id='test-manager',person_name='测试经理',com_id='11120101',short_name='第一',companies=1,
        visit_time=seconds,distance_meters=distance,longitude=117,latitude=39,gis_long=117.01,gis_lat=39)

async def process(run_id,monkeypatch,rows):
    async def fake(_): return rows
    monkeypatch.setattr(risk_engine,'fetch_events',fake)
    owner=str(uuid.uuid4())
    async with get_sessionmaker()() as s:
        await s.execute(update(RiskLease).where(RiskLease.id==1).values(owner=owner,expires=time.time()+60))
        await s.execute(update(RiskRun).where(RiskRun.id==run_id).values(status='running'))
        await s.commit()
    await risk_engine.execute_run(run_id,owner)

@pytest.mark.asyncio
async def test_permissions_and_flags(client,auth_header,user_header,enabled,monkeypatch):
    assert (await client.get('/api/risk/models')).status_code==401
    assert (await client.get('/api/risk/models',headers=user_header)).status_code==403
    monkeypatch.setattr(get_settings(),'RISK_MODULE_ENABLED',False)
    assert (await client.get('/api/risk/models',headers=auth_header)).status_code==404
    assert (await client.get('/api/health')).status_code==200

@pytest.mark.asyncio
async def test_run_workflow(client,auth_header,user_header,enabled,monkeypatch):
    await risk_engine.bootstrap()
    m=await client.post('/api/risk/models',headers=auth_header,json={'name':'测试模型','config':DEFAULT_CONFIG})
    assert m.status_code==200,m.text
    version=m.json();base=dict(version_id=version['id'],mode='formal',start_date='2024-01-02',end_date='2024-01-02',com_ids=['11120101'])
    assert (await client.post('/api/risk/runs',headers=auth_header,json=base)).status_code==422
    assert (await client.post(f"/api/risk/versions/{version['id']}/publish",headers=auth_header)).status_code==200
    assert (await client.post('/api/risk/runs',headers=auth_header,json={**base,'end_date':'2025-03-01'})).status_code==422
    trial=(await client.post('/api/risk/runs',headers=auth_header,json={**base,'mode':'trial'})).json()
    await process(trial['id'],monkeypatch,[event('first')])
    detail=(await client.get('/api/risk/runs/'+trial['id'],headers=auth_header)).json()
    assert detail['counts']['hit']==1 and detail['counts']['new_alerts']==0
    for count in [1,0]:
        run=(await client.post('/api/risk/runs',headers=auth_header,json=base)).json()
        await process(run['id'],monkeypatch,[event('first')])
        detail=(await client.get('/api/risk/runs/'+run['id'],headers=auth_header)).json()
        assert detail['status']=='succeeded' and detail['counts']['new_alerts']==count
    async with get_sessionmaker()() as s:
        a=(await s.scalars(select(RiskAlert).where(RiskAlert.model_id==version['model_id']))).one()
        aid=a.id
    # 组合必须在同一事件成立；不同事件的短时长和偏差不能拼接。
    separate=(await client.post('/api/risk/runs',headers=auth_header,json={**base,'mode':'trial'})).json()
    await process(separate['id'],monkeypatch,[event('short-only',38,20),event('gps-only',200,438)])
    result=(await client.get('/api/risk/runs/'+separate['id'],headers=auth_header)).json()
    assert result['counts']['hit']==0
    config={**DEFAULT_CONFIG,'conditions':[{**c,'value':500 if c['indicator'].endswith('meters') else 60} for c in DEFAULT_CONFIG['conditions']]}
    v2=(await client.post(f"/api/risk/models/{version['model_id']}/versions",headers=auth_header,json=config)).json()
    comp=(await client.post('/api/risk/runs',headers=auth_header,json={**base,'version_id':v2['id'],'mode':'compare','baseline_version_id':version['id']})).json()
    await process(comp['id'],monkeypatch,[event('first')])
    compared=(await client.get('/api/risk/runs/'+comp['id'],headers=auth_header)).json()
    assert compared['counts']['removed']==1 and compared['counts']['new_alerts']==0
    async with get_sessionmaker()() as s:
        assert (await s.get(RiskVersion,version['id'])).config==DEFAULT_CONFIG
    # 核查与复核分岗，普通用户不能绕过管理员范围。
    path=f'/api/risk/alerts/{aid}/actions'
    assert (await client.post(path,headers=auth_header,json={'revision':1,'action':'start','note':'开始核查'})).status_code==200
    assert (await client.post(path,headers=auth_header,json={'revision':1,'action':'start','note':'旧版本'})).status_code==409
    assert (await client.post(path,headers=auth_header,json={'revision':2,'action':'conclude','conclusion':'confirmed','note':'存在问题'})).status_code==422
    assert (await client.post(path,headers=auth_header,json={'revision':2,'action':'conclude','conclusion':'normal','note':'核实正常'})).status_code==200
    assert (await client.post(path,headers=auth_header,json={'revision':3,'action':'approve','note':'复核通过'})).status_code==403
    from app.core.security import create_access_token
    reviewer={'Authorization':'Bearer '+create_access_token(subject='test-reviewer',extra={'role':'admin'})}
    assert (await client.post(path,headers=reviewer,json={'revision':3,'action':'approve','note':'独立复核通过'})).status_code==200
    run=(await client.post('/api/risk/runs',headers=auth_header,json=base)).json()
    await process(run['id'],monkeypatch,[event('first')])
    a=(await client.get(f'/api/risk/alerts/{aid}',headers=auth_header)).json()
    assert a['status']=='closed' and not a['recurrence'] and len(a['actions'])==3
    assert a['first_run']['version_number']==1
    # 取消在正式提交前再次校验，保留空正式结果。
    cancelled=(await client.post('/api/risk/runs',headers=auth_header,json=base)).json()
    await client.post('/api/risk/runs/'+cancelled['id']+'/cancel',headers=auth_header)
    await process(cancelled['id'],monkeypatch,[event('cancel-event')])
    async with get_sessionmaker()() as s:
        assert (await s.get(RiskRun,cancelled['id'])).status=='cancelled'
        assert await s.scalar(select(func.count()).select_from(RiskItem).where(RiskItem.run_id==cancelled['id']))==0

@pytest.mark.asyncio
async def test_invalid_keys_no_partial_publication(client,auth_header,enabled,monkeypatch):
    await risk_engine.bootstrap()
    r=(await client.post('/api/risk/runs',headers=auth_header,json=dict(version_id=1,mode='formal',start_date='2024-01-02',end_date='2024-01-02',com_ids=['11120101']))).json()
    with pytest.raises(ValueError): await process(r['id'],monkeypatch,[event('same'),event('same')])
    async with get_sessionmaker()() as s:
        assert await s.scalar(select(func.count()).select_from(RiskItem).where(RiskItem.run_id==r['id']))==0

@pytest.mark.asyncio
async def test_worker_recovers_connection_failure(monkeypatch):
    calls=[]
    async def fake_loop():
        calls.append(1)
        if len(calls)==1: raise OSError('测试临时连接故障')
        raise asyncio.CancelledError
    async def quick_sleep(_): pass
    monkeypatch.setattr(risk_engine,'_worker_loop',fake_loop)
    monkeypatch.setattr(risk_engine.asyncio,'sleep',quick_sleep)
    with pytest.raises(asyncio.CancelledError): await risk_engine.worker()
    assert len(calls)==2

@pytest.mark.asyncio
async def test_attachment_clue_link_and_dashboard(client,auth_header,user_header,enabled,monkeypatch,tmp_path):
    from app.api import risk
    from app.models.clue import AuditClue
    monkeypatch.setattr(risk,'RISK_UPLOAD',tmp_path)
    await risk_engine.bootstrap()
    run=(await client.post('/api/risk/runs',headers=auth_header,json=dict(version_id=1,mode='formal',start_date='2024-01-02',end_date='2024-01-02',com_ids=['11120101']))).json()
    await process(run['id'],monkeypatch,[event('attachment-event')])
    async with get_sessionmaker()() as s:
        a=(await s.scalars(select(RiskAlert).where(RiskAlert.event_key.contains('attachment-event')))).one()
        aid=a.id
        # 复用旧线索结构，新模块仅增加关联。
        clue=AuditClue(title='测试关联',category='other',content='风险测试线索',created_by='admin')
        s.add(clue);await s.commit();cid=clue.id
    path=f'/api/risk/alerts/{aid}'
    assert (await client.post(path+'/attachments',headers=auth_header,files={'file':('test.pdf',b'evidence','application/pdf')})).status_code==200
    d=(await client.get(path,headers=auth_header)).json()
    fid=d['attachments'][0]['id']
    assert (await client.get(path+f'/attachments/{fid}',headers=auth_header)).content==b'evidence'
    assert (await client.get(path+f'/attachments/{fid}',headers=user_header)).status_code==403
    assert (await client.post(path+f'/clues/{cid}',headers=auth_header)).status_code==200
    assert (await client.get(f'/api/risk/clues/{cid}/alerts',headers=auth_header)).json()[0]['id']==aid
    assert (await client.get('/api/risk/dashboard',headers=auth_header)).status_code==200

@pytest.mark.asyncio
async def test_rectification_and_new_event_recurrence(client,auth_header,enabled,monkeypatch):
    from datetime import datetime
    from app.core.security import create_access_token
    m=(await client.post('/api/risk/models',headers=auth_header,json={'name':'复发验证','config':DEFAULT_CONFIG})).json()
    await client.post(f"/api/risk/versions/{m['id']}/publish",headers=auth_header)
    body=dict(version_id=m['id'],mode='formal',start_date='2024-01-02',end_date='2024-01-02',com_ids=['11120101'])
    r=(await client.post('/api/risk/runs',headers=auth_header,json=body)).json()
    await process(r['id'],monkeypatch,[event('old-recurrence')])
    async with get_sessionmaker()() as s:
        a=(await s.scalars(select(RiskAlert).where(RiskAlert.model_id==m['model_id']))).one()
        aid=a.id
    path=f'/api/risk/alerts/{aid}/actions'
    await client.post(path,headers=auth_header,json=dict(revision=1,action='start',note='开始核查'))
    assert (await client.post(path,headers=auth_header,json=dict(revision=2,action='conclude',conclusion='confirmed',note='已核实问题',measures='完成整改后提交复核'))).json()['status']=='rectifying'
    assert (await client.post(path,headers=auth_header,json=dict(revision=3,action='submit_rectification',note='整改完成，提交证据'))).json()['status']=='reviewing'
    reviewer={'Authorization':'Bearer '+create_access_token(subject='test-reviewer',extra={'role':'admin'})}
    assert (await client.post(path,headers=reviewer,json=dict(revision=4,action='approve',note='复核整改通过'))).json()['status']=='closed'
    async with get_sessionmaker()() as s:
        await s.execute(update(RiskAlert).where(RiskAlert.id==aid).values(closed_at=datetime(2024,1,1)))
        await s.commit()
    r=(await client.post('/api/risk/runs',headers=auth_header,json=body)).json()
    await process(r['id'],monkeypatch,[event('new-recurrence')])
    async with get_sessionmaker()() as s:
        a=(await s.scalars(select(RiskAlert).where(RiskAlert.model_id==m['model_id'],RiskAlert.id!=aid))).one()
        assert a.recurrence and a.prior_alert_id==aid and a.status=='pending'
