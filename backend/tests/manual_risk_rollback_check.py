"""隔离回切检查：旧提交读取含风险表的数据库副本，验证账号和原线索兼容。"""
from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from sqlalchemy.engine import make_url
from app.core.config import get_settings

BASELINE='76a212a31aa26a2c27e675f9f71912b480ea9294'
CHILD = '''
import asyncio,json
from httpx import ASGITransport,AsyncClient
from app.main import app
from app.core.security import create_access_token
async def main():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
            assert (await c.get('/api/health')).status_code==200
            token=create_access_token(subject='admin',extra={'role':'admin'})
            assert (await c.get('/api/auth/me',headers={'Authorization':'Bearer '+token})).status_code==200
    print('old_backend_startup_and_account_passed')
asyncio.run(main())
'''

def main():
    root=Path(__file__).resolve().parents[2]
    source=Path(make_url(get_settings().SQLITE_URL).database).resolve()
    assert source.is_file(),'当前SQLite库不存在'
    # 临时目录内隔离旧代码、复制数据库；原库只经备份接口读取。
    with tempfile.TemporaryDirectory(prefix='shenji-risk-rollback-') as name:
        target=Path(name).resolve()
        archive=subprocess.check_output(['git','archive',BASELINE,'backend'],cwd=root)
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            assert all((target/m.name).resolve().is_relative_to(target) for m in bundle.getmembers())
            bundle.extractall(target,filter='data')
        copy=target/'verification.db'
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(copy)) as dest:
            original.backup(dest)
            assert dest.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            before={table:dest.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ['users','audit_clues','risk_alerts']}
        env=os.environ.copy()
        env.update(SQLITE_URL='sqlite+aiosqlite:///'+copy.as_posix(),STARROCKS_URL='mysql+asyncmy://u:p@127.0.0.1:9030/test',JWT_SECRET='isolated-rollback-test-secret-32-chars')
        subprocess.run([sys.executable,'-c',CHILD],cwd=target/'backend',env=env,check=True,timeout=30)
        with closing(sqlite3.connect(copy)) as dest:
            after={table:dest.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in before}
        assert before==after,'旧应用启动改变了业务数量'
        print(json.dumps(dict(baseline=BASELINE,preserved_counts=after,passed=True),ensure_ascii=False))

if __name__=='__main__': main()
