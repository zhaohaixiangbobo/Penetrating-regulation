"""定时与分批最小验证：游标、恢复、版本隔离、本地迁移和触发冻结。"""
import sqlite3
import time
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select, update, func
from app.core.config import get_settings
from app.db.sqlite import get_sessionmaker
from app.db.risk_migrate import _upgrade
from app.models.risk import RiskLease, RiskBatch, RiskRun, RiskItem, RiskAlert, RiskSchedule
from app.services import risk_engine, risk_jobs, risk_schedule
from app.services.risk_rules import DEFAULT_CONFIG


@pytest.fixture
def enabled(monkeypatch):
    for key in ['RISK_MODULE_ENABLED','RISK_RUN_ENABLED','RISK_SOURCE_KEY_VERIFIED']:
        monkeypatch.setattr(get_settings(),key,True)
    monkeypatch.setattr(get_settings(),'RISK_BATCH_SIZE',2)


def source(i):
    return dict(source_id=str(i),in_monthly_plan=None,event_time='2024-01-02 00:00:00',cust_code='same-customer',cust_name='分批客户',
                person_id='one-manager',person_name='经理',com_id='11120101',short_name='第一',companies=1,visit_time=30,distance_meters=400)


async def setup_run(client,auth_header):
    await risk_engine.bootstrap()
    v=(await client.post('/api/risk/models',headers=auth_header,json={'name':'分批测试','config':DEFAULT_CONFIG})).json()
    await client.post(f"/api/risk/versions/{v['id']}/publish",headers=auth_header)
    body=dict(version_id=v['id'],mode='formal',start_date='2024-01-02',end_date='2024-01-02',com_ids=['11120101'])
    r=(await client.post('/api/risk/runs',headers=auth_header,json=body)).json()
    async with get_sessionmaker()() as s:
        await s.execute(update(RiskLease).where(RiskLease.id==1).values(owner='jobs-test',expires=time.time()+100));await s.commit()
    return v,body,r


@pytest.mark.asyncio
async def test_paging_recovery_retry_and_versions(client,auth_header,enabled,monkeypatch):
    v,body,run=await setup_run(client,auth_header)
    # 隔离该测试的队列，避免其他测试留下的 queued 任务参与领取。
    async with get_sessionmaker()() as s:
        await s.execute(update(RiskRun).where(RiskRun.id!=run['id'],RiskRun.status.in_(['queued','running'])).values(status='cancelled'));await s.commit()
    reads=[]
    async def fetch(scope):
        cursor=scope['_cursor'];reads.append(cursor)
        if cursor and len(reads)==2: raise ValueError('模拟第二批数据错误')
        return [source(3)] if cursor else [source(1),source(2),source(3)]
    monkeypatch.setattr(risk_engine,'fetch_events',fetch)
    assert await risk_jobs.process_one('jobs-test')
    assert await risk_jobs.process_one('jobs-test')
    r=(await client.get(f"/api/risk/runs/{run['id']}",headers=auth_header)).json()
    assert r['status']=='partial_failed' and r['counts']['scanned']==2
    assert r['counts']['customers']==1 and reads[1]['is_null']==1
    assert (await client.post(f"/api/risk/runs/{run['id']}/retry",headers=auth_header)).status_code==200
    await risk_jobs.process_one('jobs-test')
    r=(await client.get(f"/api/risk/runs/{run['id']}",headers=auth_header)).json()
    assert r['status']=='succeeded' and r['counts']['scanned']==3 and r['counts']['customers']==1
    async with get_sessionmaker()() as s:
        assert await s.scalar(select(func.count()).select_from(RiskItem).where(RiskItem.run_id==run['id']))==3
        assert await s.scalar(select(func.count()).select_from(RiskAlert).where(RiskAlert.model_version_id==v['id']))==3
    # 新模型版本保留独立预警，同事件不会被旧模型版本约束拦截。
    v2=(await client.post(f"/api/risk/models/{v['model_id']}/versions",headers=auth_header,json=DEFAULT_CONFIG)).json()
    await client.post(f"/api/risk/versions/{v2['id']}/publish",headers=auth_header)
    second=(await client.post('/api/risk/runs',headers=auth_header,json={**body,'version_id':v2['id']})).json()
    # 领取后模拟进程中断，接管恢复为待执行且原尝试留痕。
    async with get_sessionmaker()() as s:
        b=(await s.scalars(select(RiskBatch).where(RiskBatch.run_id==second['id']))).one()
        b.status='running';b.token='expired';await s.commit()
        await risk_jobs.recover(s);await s.commit()
    await risk_jobs.process_one('jobs-test');await risk_jobs.process_one('jobs-test')
    async with get_sessionmaker()() as s:
        assert await s.scalar(select(func.count()).select_from(RiskAlert).where(RiskAlert.model_id==v['model_id']))==6


@pytest.mark.asyncio
async def test_schedule_snapshot_trigger_and_permissions(client,auth_header,user_header,enabled):
    v,_,_=await setup_run(client,auth_header)
    payload=dict(name='每天固定计划',version_id=v['id'],com_ids=['11120101'],hour=3,minute=0,lookback_days=3,batch_size=2,enabled=True)
    assert (await client.post('/api/risk/schedules',headers=user_header,json=payload)).status_code==403
    created=await client.post('/api/risk/schedules',headers=auth_header,json=payload)
    assert created.status_code==200,created.text
    plan=created.json();now=datetime(2024,2,5,4)
    async with get_sessionmaker()() as s:
        await s.execute(update(RiskSchedule).where(RiskSchedule.id==plan['id']).values(next_fire=datetime(2024,2,1,3)));await s.commit()
    await risk_schedule.tick('jobs-test',now);await risk_schedule.tick('jobs-test',now)
    hist=(await client.get(f"/api/risk/schedules/{plan['id']}/history",headers=auth_header)).json()
    assert len(hist['triggers'])==2 and {r['status'] for r in hist['triggers']}=={'missed','queued'}
    rid=next(r['run_id'] for r in hist['triggers'] if r['run_id'])
    edited=await client.put(f"/api/risk/schedules/{plan['id']}",headers=auth_header,json={**payload,'lookback_days':7,'revision':1})
    assert edited.status_code==200
    assert (await client.put(f"/api/risk/schedules/{plan['id']}",headers=auth_header,json={**payload,'revision':1})).status_code==409
    run=(await client.get(f'/api/risk/runs/{rid}',headers=auth_header)).json()
    assert run['scope']['start_date']=='2024-02-02' and run['scope']['end_date']=='2024-02-04'
    assert run['scope']['schedule_snapshot']['lookback_days']==3


def test_calendar_and_migration(tmp_path):
    config=dict(frequency='weekly',weekday=0,hour=3,minute=0,lookback_days=3,batch_size=2,com_ids=['11120101'])
    assert risk_schedule.next_fire(config,datetime(2024,2,5,3))==datetime(2024,2,12,3)
    assert risk_schedule.scope_for(config,datetime(2024,3,1,3))['end_date']=='2024-02-29'
    path=tmp_path/'old.db'
    with sqlite3.connect(path) as s:
        s.executescript('CREATE TABLE risk_runs(id TEXT PRIMARY KEY,version_id INTEGER); CREATE TABLE risk_run_items(id INTEGER PRIMARY KEY,run_id TEXT); CREATE TABLE risk_alerts(id INTEGER PRIMARY KEY,model_id INTEGER,event_key TEXT,first_item_id INTEGER,UNIQUE(model_id,event_key)); INSERT INTO risk_runs VALUES ("old",7); INSERT INTO risk_run_items VALUES(1,"old"); INSERT INTO risk_alerts VALUES(42,3,"event",1);')
    _upgrade(str(path));_upgrade(str(path))
    with sqlite3.connect(path) as s:
        assert s.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert s.execute('SELECT model_version_id FROM risk_alerts WHERE id=42').fetchone()[0]==7
        s.execute('INSERT INTO risk_alerts VALUES(43,3,"event",1,8)')
        with pytest.raises(sqlite3.IntegrityError): s.execute('INSERT INTO risk_alerts VALUES(44,3,"event",1,8)')
        assert s.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert len(list((tmp_path/'backups').glob('*.db')))==1


@pytest.mark.asyncio
async def test_cancel_and_expired_owner(client,auth_header,enabled,monkeypatch):
    _,_,run=await setup_run(client,auth_header)
    async with get_sessionmaker()() as s:
        await s.execute(update(RiskRun).where(RiskRun.id!=run['id'],RiskRun.status.in_(['queued','running'])).values(status='cancelled'));await s.commit()
    async def cancelling(scope):
        await client.post(f"/api/risk/runs/{run['id']}/cancel",headers=auth_header)
        return [source(1)]
    monkeypatch.setattr(risk_engine,'fetch_events',cancelling)
    await risk_jobs.process_one('jobs-test')
    detail=(await client.get(f"/api/risk/runs/{run['id']}",headers=auth_header)).json()
    assert detail['status']=='cancelled' and detail['counts']['scanned']==0
    async with get_sessionmaker()() as s:
        assert await s.scalar(select(func.count()).select_from(RiskItem).where(RiskItem.run_id==run['id']))==0
        await s.execute(update(RiskLease).where(RiskLease.id==1).values(owner='new-owner',expires=time.time()+60));await s.commit()
    assert not await risk_jobs.process_one('jobs-test')


@pytest.mark.asyncio
async def test_transient_retry_and_boundary_duplicates(client,auth_header,enabled,monkeypatch):
    _,_,run=await setup_run(client,auth_header)
    async with get_sessionmaker()() as s:
        await s.execute(update(RiskRun).where(RiskRun.id!=run['id'],RiskRun.status.in_(['queued','running'])).values(status='cancelled'));await s.commit()
    async def broken(scope): raise ConnectionError('模拟瞬时故障')
    monkeypatch.setattr(risk_engine,'fetch_events',broken)
    await risk_jobs.process_one('jobs-test')
    async with get_sessionmaker()() as s:
        b=(await s.scalars(select(RiskBatch).where(RiskBatch.run_id==run['id']))).one()
        assert b.status=='retry_wait' and b.retry_at>time.time()
        b.retry_at=0;await s.commit()
    async def duplicate(scope): return [source(1),source(2),source(2)]
    monkeypatch.setattr(risk_engine,'fetch_events',duplicate)
    await risk_jobs.process_one('jobs-test')
    detail=(await client.get(f"/api/risk/runs/{run['id']}",headers=auth_header)).json()
    assert detail['status']=='failed' and detail['counts']['scanned']==0


@pytest.mark.asyncio
async def test_api_startup_and_source_gate(client,auth_header,enabled,monkeypatch):
    from app.main import app, lifespan
    from app.db.sqlite import get_engine
    from sqlalchemy import text
    async with lifespan(app):
        async with get_engine().connect() as conn:
            assert (await conn.execute(text('PRAGMA journal_mode'))).scalar()=='wal'
    v,body,_=await setup_run(client,auth_header)
    monkeypatch.setattr(get_settings(),'RISK_SOURCE_KEY_VERIFIED',False)
    assert (await client.post('/api/risk/runs',headers=auth_header,json=body)).status_code==409
    assert (await client.post('/api/risk/runs',headers=auth_header,json={**body,'mode':'trial'})).status_code==200
    plan=dict(name='待核实计划',version_id=v['id'],com_ids=['11120101'],enabled=False)
    assert (await client.post('/api/risk/schedules',headers=auth_header,json=plan)).status_code==200
    assert (await client.post('/api/risk/schedules',headers=auth_header,json={**plan,'enabled':True})).status_code==409
