"""只读复制现有 SQLite 并在临时副本升级，检查行数、主键及证据关联，不改业务库。"""
import argparse
import json
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
from app.db.risk_migrate import _upgrade


def check(source):
    with tempfile.TemporaryDirectory(prefix='risk-migration-check-') as folder:
        target=Path(folder)/'copy.db'
        with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as origin, closing(sqlite3.connect(target)) as copy:
            origin.backup(copy)
        with closing(sqlite3.connect(target)) as conn:
            tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name<>'schema_migrations'")]
            before={table:conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
            ids=conn.execute('SELECT id,first_item_id,latest_item_id FROM risk_alerts ORDER BY id').fetchall()
        _upgrade(str(target))
        with closing(sqlite3.connect(target)) as conn:
            assert all(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]==count for table,count in before.items())
            assert conn.execute('SELECT id,first_item_id,latest_item_id FROM risk_alerts ORDER BY id').fetchall()==ids
            missing=conn.execute('SELECT COUNT(*) FROM risk_alerts a LEFT JOIN risk_run_items i ON i.id=a.first_item_id LEFT JOIN risk_runs r ON r.id=i.run_id WHERE a.model_version_id IS NULL OR a.model_version_id<>r.version_id OR r.id IS NULL').fetchone()[0]
            assert missing==0
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            print(json.dumps(dict(result='passed',tables_preserved=len(before),alerts_preserved=len(ids),version_reference_errors=missing,source_modified=False),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True,type=Path)
    args=parser.parse_args();check(args.source)
