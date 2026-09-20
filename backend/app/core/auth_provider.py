"""认证 Provider 抽象：本地账号 与 4A/OIDC 单点登录。

设计目标：把「身份从哪来」抽象成可替换的 Provider，业务接口与前端只依赖
本系统统一签发的 JWT，未来接入 4A 时业务层无需改动。

- LocalAuthProvider：现有 SQLite + bcrypt 登录（默认，AUTH_MODE=local）。
- OIDCAuthProvider ：对接 4A 统一身份平台的 OIDC 单点登录（预留，AUTH_MODE=oidc）。
  其中 build_authorize_url 已可用（仅拼接跳转地址，无网络请求），
  exchange_code 待甲方提供 OIDC 对接文档后实现（当前返回 501 占位）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlencode

from fastapi import HTTPException, status

from app.core.config import Settings, get_settings


class AuthProvider(ABC):
    """认证提供方统一接口。"""

    mode: str = "base"

    @abstractmethod
    def build_authorize_url(self, state: str) -> str:
        """返回跳转到身份提供方的登录地址（SSO 第一步）。"""

    @abstractmethod
    async def exchange_code(self, code: str, state: str) -> dict:
        """用回调 code 换取用户信息，返回 {username, role, external_id}。"""


class LocalAuthProvider(AuthProvider):
    """本地账号密码登录：不走 SSO。"""

    mode = "local"

    def build_authorize_url(self, state: str) -> str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="当前为本地登录模式，未启用 SSO")

    async def exchange_code(self, code: str, state: str) -> dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="当前为本地登录模式，未启用 SSO")


class OIDCAuthProvider(AuthProvider):
    """4A 统一身份平台 OIDC 单点登录（预留实现）。"""

    mode = "oidc"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _authorize_endpoint(self) -> str:
        # 标准 OIDC 授权端点，如各 4A 平台不同可在此调整或从发现文档读取
        return self.settings.OIDC_ISSUER.rstrip("/") + "/authorize"

    def build_authorize_url(self, state: str) -> str:
        s = self.settings
        if not (s.OIDC_ISSUER and s.OIDC_CLIENT_ID and s.OIDC_REDIRECT_URI):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OIDC 配置不完整")
        params = {
            "response_type": "code",
            "client_id": s.OIDC_CLIENT_ID,
            "redirect_uri": s.OIDC_REDIRECT_URI,
            "scope": s.OIDC_SCOPES,
            "state": state,
        }
        return f"{self._authorize_endpoint()}?{urlencode(params)}"

    async def exchange_code(self, code: str, state: str) -> dict:
        # TODO(4A): 待甲方提供 OIDC 对接文档后实现：
        #   1) 用 code + client_secret 调 token endpoint 换取 id_token / access_token
        #   2) 校验 id_token 签名与 state / nonce
        #   3) 解析 id_token 或调 userinfo，读取 OIDC_USERNAME_CLAIM / OIDC_ROLE_CLAIM
        #   4) 按 external_id 在本地 users 表 upsert，返回 {username, role, external_id}
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="OIDC 单点登录尚未接入（预留）")


def get_auth_provider() -> AuthProvider:
    """根据 AUTH_MODE 返回对应的认证 Provider。"""
    settings = get_settings()
    if settings.AUTH_MODE.lower() == "oidc":
        return OIDCAuthProvider(settings)
    return LocalAuthProvider()


__all__ = ["AuthProvider", "LocalAuthProvider",
           "OIDCAuthProvider", "get_auth_provider"]
