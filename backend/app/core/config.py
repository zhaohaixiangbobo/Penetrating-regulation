"""应用配置：从 .env 加载，暴露给 FastAPI 使用。"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 13 个公司代码（来源：database.md）
COMPANIES: list[dict[str, str]] = [
    {"com_id": "11120101", "short_name": "第一"},
    {"com_id": "11120102", "short_name": "第二"},
    {"com_id": "11120103", "short_name": "第三"},
    {"com_id": "11120104", "short_name": "东丽"},
    {"com_id": "11120105", "short_name": "西青"},
    {"com_id": "11120106", "short_name": "津南"},
    {"com_id": "11120107", "short_name": "北辰"},
    {"com_id": "11120111", "short_name": "武清"},
    {"com_id": "11120112", "short_name": "宝坻"},
    {"com_id": "11120113", "short_name": "滨海"},
    {"com_id": "11120201", "short_name": "蓟州"},
    {"com_id": "11120202", "short_name": "静海"},
    {"com_id": "11120203", "short_name": "宁河"},
]

VALID_COM_IDS: set[str] = {c["com_id"] for c in COMPANIES}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")

    STARROCKS_URL: str = "mysql+asyncmy://root:TJycrock%23lc2025@10.9.14.128:9030/eap_adb?charset=utf8mb4"
    SQLITE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    JWT_SECRET: str = "please-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MIN: int = 480

    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001,http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
