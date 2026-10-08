"""FastAPI 应用入口（纯 API 服务）。

生产部署由 Nginx 托管前端静态资源并反向代理 /api 到本服务，
详见 docs/07-信创服务器部署手册.md。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import audit, auth, feedback, marketing_monopoly, meta, risk, risk_schedules
from app.services.risk_engine import bootstrap as bootstrap_risk
from app.core.config import get_settings
from app.db.migrate import ensure_sqlite_schema
from app.db.risk_migrate import ensure_risk_schema
from app.db.sqlite import Base, get_engine as get_sqlite_engine

logger = logging.getLogger("shenji")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动时确保 SQLite 表存在
    await ensure_risk_schema()
    engine = get_sqlite_engine()
    async with engine.begin() as conn:
        await conn.exec_driver_sql('BEGIN IMMEDIATE')
        await conn.run_sync(Base.metadata.create_all)
    # 老库平滑升级：补齐 role / external_id 列
    await ensure_sqlite_schema(engine)
    logger.info("SQLite tables ensured.")
    if get_settings().RISK_MODULE_ENABLED:
        await bootstrap_risk()
    # API 只管理页面与队列，计算由 python -m app.risk_worker 独立执行。
    yield



def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="穿透式监督查询系统", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(meta.router)
    app.include_router(audit.router)
    app.include_router(marketing_monopoly.router)
    app.include_router(feedback.router)
    app.include_router(risk.router)
    app.include_router(risk_schedules.router)

    @app.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
