"""业务表探测：确认 eap_adb 库中所需业务表都存在且可读。

用法：
  cd d:\\2-code\\shenji\\backend
  D:\\3-anaconda\\envs\\py312\\python.exe -m scripts.probe_tables

对每张表：
  1) SELECT count(*) —— 权限 + 表存在性
  2) DESC 表名        —— 打印字段（截取前 15 行）

不打印任何业务数据，仅结构与行数。
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.starrocks import get_engine

TABLES = [
    "crm_mcs_cust_visit_plan",
    "t_comm_emp_yx",
    "t_comm_company",
    "uc_evaluation_m",
    "uc_evaluation_m_cust",
    "kc_customer_qsp",
]


async def main() -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        for tbl in TABLES:
            print(f"\n=== {tbl} ===")
            try:
                row = (await conn.execute(text(f"SELECT count(*) FROM {tbl}"))).first()
                print(f"count(*) = {row[0] if row else 'N/A'}")
            except Exception as e:  # noqa: BLE001
                print(f"[FAIL] count: {e}")
                continue
            try:
                rows = (await conn.execute(text(f"DESC {tbl}"))).fetchmany(15)
                for r in rows:
                    # DESC 结果通常是 (Field, Type, Null, Key, Default, Extra)
                    print("  ", tuple(r))
            except Exception as e:  # noqa: BLE001
                print(f"[FAIL] desc: {e}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
