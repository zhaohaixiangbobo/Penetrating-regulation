"""拜访定位查询最小验证：鉴权、日期阈值校验及查询导出契约。"""
import pytest
from .test_audit import FakeSession, _clear_fake, _use_fake

pytestmark = pytest.mark.asyncio
BASE = '/api/marketing-monopoly/visit-location'
VALID = {'start_date': '2024-01-01', 'end_date': '2024-01-02'}

async def test_auth(client):
    assert (await client.post(BASE, json=VALID)).status_code == 401

@pytest.mark.parametrize('changes', [
    {'distance_meters': 0}, {'start_date': '2023-12-31'},
    {'end_date': '2023-12-31'}, {'sort_field': 'bad'}, {'page_size': 201},
])
async def test_validation(client, auth_header, changes):
    response = await client.post(BASE, json={**VALID, **changes}, headers=auth_header)
    assert response.status_code == 422

async def test_query_export(client, auth_header):
    row = dict(visit_id='1', plan_date='2024-01-01', longitude=117.0, latitude=39.0,
               gis_long=117.01, gis_lat=39.0, distance_meters=864.2)
    session = FakeSession(1, [row])
    _use_fake(session)
    try:
        result = await client.post(BASE, json=VALID, headers=auth_header)
        export = await client.post(BASE + '/export', json=VALID, headers=auth_header)
    finally:
        _clear_fake()
    assert result.status_code == export.status_code == 200
    assert result.json()['items'] == export.json()
    sql, params = session.executed[0]
    assert 'distance_meters > :distance_meters' in sql
    assert params['distance_meters'] == 200
    assert "a.visit_status = '03' AND a.deleted = '0'" in sql
    assert 'ST_Distance_Sphere(lic.longitude, lic.latitude, a.gis_long, a.gis_lat)' in sql
    assert 'INTERVAL 1 DAY' in sql
