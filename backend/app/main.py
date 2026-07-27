"""FastAPI 应用入口（纯 API 服务）。

生产部署由 Nginx 托管前端静态资源并反向代理 /api 到本服务，
详见 docs/07-信创服务器部署手册.md。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import audit, auth, meta
from app.core.config import get_settings
from app.db.sqlite import Base, get_engine as get_sqlite_engine

logger = logging.getLogger("shenji")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动时确保 SQLite 表存在
    engine = get_sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("SQLite tables ensured.")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="审计监管系统", version="0.1.0", lifespan=lifespan)

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

    @app.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
