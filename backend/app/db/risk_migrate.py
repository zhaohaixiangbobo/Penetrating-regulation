"""风险分批升级：一致性备份、版本化预警唯一约束与本地 WAL 初始化。"""
import asyncio
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from app.db.sqlite import get_engine


def _upgrade(path: str):
    if path == ':memory:':
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target, timeout=10)) as conn:
        conn.execute('PRAGMA busy_timeout=10000')
        mode = conn.execute('PRAGMA journal_mode=WAL').fetchone()[0]
        if mode.lower() != 'wal':
            raise RuntimeError('SQLite WAL 初始化失败')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        conn.commit()
        if conn.execute("SELECT 1 FROM schema_migrations WHERE version='risk_batches_v2'").fetchone():
            return
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'risk_alerts' in tables:
            backup = target.parent / 'backups' / f'risk-v2-{datetime.now():%Y%m%d-%H%M%S-%f}.db'
            backup.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(backup)) as out:
                conn.backup(out)
        conn.execute('BEGIN IMMEDIATE')
        try:
            # 多个 API 进程同时启动时，在取得写锁后再次检查迁移记录。
            if conn.execute("SELECT 1 FROM schema_migrations WHERE version='risk_batches_v2'").fetchone():
                conn.commit()
                return
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'risk_alerts' in tables:
                cols = {r[1] for r in conn.execute('PRAGMA table_info(risk_alerts)')}
                if 'model_version_id' not in cols:
                    conn.execute('ALTER TABLE risk_alerts ADD COLUMN model_version_id INTEGER')
                    conn.execute('UPDATE risk_alerts SET model_version_id=(SELECT r.version_id FROM risk_run_items i JOIN risk_runs r ON r.id=i.run_id WHERE i.id=risk_alerts.first_item_id)')
                    if conn.execute('SELECT COUNT(*) FROM risk_alerts WHERE model_version_id IS NULL').fetchone()[0]:
                        raise RuntimeError('存在缺失首次运行版本的预警，迁移已回滚')
                    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='risk_alerts'").fetchone()[0]
                    indexes = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='risk_alerts' AND sql IS NOT NULL")]
                    sql = re.sub(r'UNIQUE\s*\(\s*model_id\s*,\s*event_key\s*\)', 'UNIQUE (model_version_id, event_key)', sql, flags=re.I)
                    sql = re.sub(r'CREATE TABLE\s+"?risk_alerts"?', 'CREATE TABLE risk_alerts_v2', sql, count=1, flags=re.I)
                    conn.execute(sql)
                    conn.execute('INSERT INTO risk_alerts_v2 SELECT * FROM risk_alerts')
                    conn.execute('DROP TABLE risk_alerts')
                    conn.execute('ALTER TABLE risk_alerts_v2 RENAME TO risk_alerts')
                    for statement in indexes:
                        conn.execute(statement)
                conn.execute('CREATE INDEX IF NOT EXISTS ix_risk_alerts_model_version_id ON risk_alerts(model_version_id)')
            if 'risk_run_items' in tables:
                if 'batch_id' not in {r[1] for r in conn.execute('PRAGMA table_info(risk_run_items)')}:
                    conn.execute('ALTER TABLE risk_run_items ADD COLUMN batch_id INTEGER')
                conn.execute('CREATE INDEX IF NOT EXISTS ix_risk_run_items_batch_id ON risk_run_items(batch_id)')
            conn.execute("INSERT INTO schema_migrations VALUES ('risk_batches_v2', ?)", (datetime.now().isoformat(),))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


async def ensure_risk_schema():
    await asyncio.to_thread(_upgrade, get_engine().url.database)
