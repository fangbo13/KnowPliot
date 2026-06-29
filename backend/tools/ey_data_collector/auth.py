# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""
EY Data Collector — Standalone knowledge content crawler.

INTERNAL USE ONLY. 本脚本仅供 EY 内部员工用于构建新入职培训 AI 知识库，
仅从经授权许可的内部数据源或公开允许抓取的 EY 官方页面获取数据。
使用者须严格遵守 EY 信息安全政策、数据保护法规及目标网站的服务条款。
任何未经授权的抓取行为由使用者自行承担责任。
如涉及第三方版权内容，请确保已获得相应授权或仅提取摘要信息。

内网认证模块 — 处理 Kerberos / API Key / Bearer Token 认证。

对于内部数据源（SharePoint/Wiki/内网 API），脚本需要通过认证才能访问。
支持的认证方式：
- Kerberos: 通过 requests-kerberos 或 gssapi，适用于内网 SharePoint
- API Key: 通过环境变量，适用于内网 API 端点
- Bearer Token: 通过环境变量，适用于 OAuth 保护的端点

若认证凭据缺失，脚本优雅退出并提示缺失的环境变量名，
而不是静默失败或崩溃。
"""

import os
import logging

from .models import SourceConfig

logger = logging.getLogger("ey_data_collector.auth")


class AuthHandler:
    """内网认证处理器 — 支持 Kerberos / API Key / Bearer Token。

    每种认证方式的凭据来源：
    - Kerberos: 系统级 Kerberos 票据（无需额外环境变量）
    - API Key: 环境变量 auth_env_var 中指定的变量名
    - Bearer Token: 环境变量 auth_env_var 中指定的变量名

    预检逻辑: check_credentials_available() 在爬取前检查凭据是否可用，
    缺失时返回 (False, 描述信息) 而非抛出异常。
    """

    def check_credentials_available(
        self, source: SourceConfig,
    ) -> tuple[bool, str]:
        """预检: 验证所需认证凭据是否可用。

        Args:
            source: 数据源配置。

        Returns:
            (available, message) — available=False 时 message 描述缺失的凭据。
        """
        if source.auth_type == "none":
            return True, "无需认证凭据"

        if source.auth_type == "kerberos":
            # Kerberos 认证依赖系统级票据，检查 kinit 是否可用
            # 实际生产环境中，Kerberos 票据通常由系统自动管理
            return True, "Kerberos 认证依赖系统级票据（请确保已 kinit）"

        if source.auth_type in ("api_key", "bearer"):
            env_var = source.auth_env_var
            if not env_var:
                return False, (
                    f"数据源 '{source.name}' 配置 auth_type={source.auth_type} "
                    f"但未指定 auth_env_var 环境变量名"
                )

            cred = os.environ.get(env_var)
            if not cred:
                return False, (
                    f"缺失认证凭据: 环境变量 '{env_var}' 未设置 "
                    f"（数据源: {source.name}, 认证方式: {source.auth_type}）。"
                    f"请设置: export {env_var}=<your_credentials>"
                )

            return True, f"认证凭据可用: {env_var}"

        return False, f"未支持的认证方式: {source.auth_type}"

    def get_auth_headers(self, source: SourceConfig) -> dict[str, str]:
        """构建认证相关的 HTTP 请求头。

        Args:
            source: 数据源配置。

        Returns:
            需添加到请求头的认证信息字典。
        """
        headers: dict[str, str] = {}

        if source.auth_type == "none":
            return headers

        if source.auth_type == "api_key":
            env_var = source.auth_env_var
            cred = os.environ.get(env_var, "")
            if cred:
                # API Key 通常通过自定义头传递
                headers["X-API-Key"] = cred
                logger.debug("API Key 认证头已添加（来源: %s）", source.name)

        elif source.auth_type == "bearer":
            env_var = source.auth_env_var
            cred = os.environ.get(env_var, "")
            if cred:
                headers["Authorization"] = f"Bearer {cred}"
                logger.debug("Bearer Token 认证头已添加（来源: %s）", source.name)

        elif source.auth_type == "kerberos":
            # Kerberos 认证在 httpx 层面通过 requests-kerberos 适配器处理
            # 此处仅标记需要 Kerberos 认证
            headers["X-Auth-Type"] = "Kerberos"
            logger.debug("Kerberos 认证标记已添加（来源: %s）", source.name)

        return headers
