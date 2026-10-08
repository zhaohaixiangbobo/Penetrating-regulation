"""应用配置：从 .env 加载，暴露给 FastAPI 使用。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 后端根目录（app/core/config.py -> app -> backend），用于计算不依赖 CWD 的绝对路径
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


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

# ------------------------------------------------------------------
# 审计线索反馈：附件上传相关常量
# ------------------------------------------------------------------
# 附件根目录（绝对路径，位于 backend/data/uploads/clues），备份时需与 app.db 一并备份
UPLOAD_DIR: Path = _BACKEND_ROOT / "data" / "uploads" / "clues"
# 单个附件大小上限（MB）
MAX_UPLOAD_MB: int = 10
# 单条线索附件数量上限
MAX_ATTACHMENTS_PER_CLUE: int = 5
# 允许的附件扩展名（小写，含点）
ALLOWED_UPLOAD_EXTS: set[str] = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip",
}
# 线索类型与状态取值（后端确定性校验用）
CLUE_CATEGORIES: tuple[str, ...] = ("营销", "专卖", "审计", "财务", "其他")
CLUE_STATUSES: tuple[str, ...] = ("pending", "processing", "done")
CLUE_STATUS_LABELS: dict[str, str] = {
    "pending": "待处理", "processing": "处理中", "done": "已处理",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 风险一期默认关闭；管理员可在本地配置中启用，原查询保持可用。
    RISK_MODULE_ENABLED: bool = False
    RISK_RUN_ENABLED: bool = False
    # 独立后台默认不开启计划；源键核实后才允许自动正式发布。
    RISK_SCHEDULE_ENABLED: bool = False
    RISK_SOURCE_KEY_VERIFIED: bool = False
    RISK_BATCH_SIZE: int = Field(1000, ge=1, le=5000)
    RISK_MAX_PENDING_RUNS: int = Field(50, ge=1, le=500)


    STARROCKS_URL: str = "mysql+asyncmy://root:TJycrock%23lc2025@10.9.14.128:9030/eap_adb?charset=utf8mb4"
    SQLITE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    JWT_SECRET: str = "please-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MIN: int = 480

    # ------------------------------------------------------------------
    # 认证模式与 4A/OIDC 预留配置
    #   AUTH_MODE=local ：本地 SQLite 账号 + 密码登录（默认）
    #   AUTH_MODE=oidc  ：对接 4A 统一身份平台（OIDC 单点登录，待甲方文档落地）
    # 说明：切换到 oidc 时，本地登录接口仍可作为降级入口保留。
    # ------------------------------------------------------------------
    AUTH_MODE: str = "local"
    # 新建账号的默认角色（admin / user）
    DEFAULT_ROLE: str = "user"

    # OIDC 对接参数（AUTH_MODE=oidc 时必填，local 模式下留空即可）
    OIDC_ISSUER: str = ""            # 例如 https://4a.example.com/oidc
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = ""      # 例如 http://10.9.14.128/api/auth/sso/callback
    OIDC_SCOPES: str = "openid profile"
    # 从 OIDC 用户信息中读取用户名/角色所用的字段名（不同 4A 平台可能不同）
    OIDC_USERNAME_CLAIM: str = "preferred_username"
    OIDC_ROLE_CLAIM: str = "role"

    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8001,http://127.0.0.1:8001,http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
