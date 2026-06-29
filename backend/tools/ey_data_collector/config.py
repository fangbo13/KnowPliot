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

配置加载模块 — 从 YAML 文件加载配置，叠加环境变量覆盖。
配置字段命名对齐 backend/config/settings/base.py (lines 165-169) 中的
CRAWL_* 环境变量约定。
"""

import os
import logging
from dataclasses import dataclass, field

import yaml

from .models import SourceConfig

logger = logging.getLogger("ey_data_collector.config")


# ────────────────────────────────────────────────────────────────────
# 全局爬取配置
# ────────────────────────────────────────────────────────────────────

@dataclass
class CrawlerConfig:
    """全局爬取配置 — 字段命名对齐 backend/config/settings/base.py CRAWL_* 变量。

    环境变量覆盖优先级：环境变量 > YAML 配置 > 默认值。
    环境变量命名约定：EY_CRAWL_前缀 + 大写字段名。
    """
    # 身份标识与透明度
    user_agent: str = "EY-DataCollector/1.0"
    contact_email: str = ""                    # X-Contact 头（内网邮箱）
    purpose: str = "New employee training knowledge content collection"  # X-Purpose 头

    # URL 与内容限制 — 对齐 settings/base.py CRAWL_* 设置
    max_url_length: int = 2048                 # CRAWL_MAX_URL_LENGTH
    max_redirects: int = 3                     # CRAWL_MAX_REDIRECTS
    max_content_size: int = 500_000            # 500KB，对齐 CRAWL_MAX_CONTENT_SIZE_KB

    # 速率限制
    rate_limit_min_delay: float = 2.0          # 请求间最小延迟（秒）
    rate_limit_max_delay: float = 5.0          # 请求间最大延迟（秒）

    # 重试策略 — 对齐 Celery task max_retries + exponential backoff
    max_retries: int = 3                       # 最大重试次数
    retry_backoff_base: int = 60               # 基础退避秒数；delay = base * 2^attempt

    # HTTP 超时 — 对齐 services.py httpx.Timeout 参数
    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    write_timeout: float = 10.0

    # 输出设置
    output_format: str = "jsonl"               # "jsonl" | "csv"
    output_dir: str = "./output"               # 输出目录
    output_name: str = ""                      # 输出文件名（空则自动生成）

    # 去重
    dedup_enabled: bool = True                 # SHA256 精确去重开关

    # 日志
    log_level: str = "INFO"                    # DEBUG/INFO/WARNING/ERROR
    log_file: str = ""                         # 日志文件路径（空则仅 stdout）

    # 安全开关
    skip_robots: bool = False                  # 是否跳过 robots.txt 检查（不建议）
    skip_ssrf: bool = False                    # 是否跳过 SSRF 校验（不建议，危险）

    # 数据源列表
    sources: list[SourceConfig] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────
# YAML 配置文件加载
# ────────────────────────────────────────────────────────────────────

def _resolve_env_vars(value: str) -> str:
    """解析 YAML 值中的环境变量引用。

    支持 ${ENV_VAR} 和 ${ENV_VAR:default} 两种格式。
    例如: "${EY_CRAWL_CONTACT_EMAIL}" → 从环境变量读取
          "${EY_CRAWL_LOG_LEVEL:INFO}" → 有默认值的环境变量
    """
    if not isinstance(value, str) or "${" not in value:
        return value

    # 提取 ${...} 中的变量名和默认值
    start = value.find("${")
    end = value.find("}", start)
    if start == -1 or end == -1:
        return value

    var_part = value[start + 2:end]
    if ":" in var_part:
        var_name, default_val = var_part.split(":", 1)
    else:
        var_name = var_part
        default_val = ""

    resolved = os.environ.get(var_name.strip(), default_val.strip())
    result = value[:start] + resolved + value[end + 1:]

    # 递归解析（支持嵌套引用）
    if "${" in result:
        return _resolve_env_vars(result)

    return result


def _resolve_dict_env_vars(d: dict) -> dict:
    """递归解析字典中所有字符串值的环境变量引用。"""
    result = {}
    for key, value in d.items():
        if isinstance(value, str):
            result[key] = _resolve_env_vars(value)
        elif isinstance(value, dict):
            result[key] = _resolve_dict_env_vars(value)
        elif isinstance(value, list):
            result[key] = [
                _resolve_env_vars(item) if isinstance(item, str)
                else _resolve_dict_env_vars(item) if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def load_config(config_path: str) -> CrawlerConfig:
    """从 YAML 配置文件加载 CrawlerConfig，叠加环境变量覆盖。

    配置优先级：环境变量 > YAML 配置 > 默认值。

    环境变量覆盖列表（对齐 settings/base.py 命名约定）：
    - EY_CRAWL_USER_AGENT        → user_agent
    - EY_CRAWL_CONTACT_EMAIL     → contact_email
    - EY_CRAWL_MAX_URL_LENGTH    → max_url_length
    - EY_CRAWL_MAX_REDIRECTS     → max_redirects
    - EY_CRAWL_MAX_CONTENT_SIZE  → max_content_size
    - EY_CRAWL_RATE_MIN_DELAY    → rate_limit_min_delay
    - EY_CRAWL_RATE_MAX_DELAY    → rate_limit_max_delay
    - EY_CRAWL_MAX_RETRIES       → max_retries
    - EY_CRAWL_RETRY_BACKOFF     → retry_backoff_base
    - EY_CRAWL_OUTPUT_FORMAT     → output_format
    - EY_CRAWL_OUTPUT_DIR        → output_dir
    - EY_CRAWL_LOG_LEVEL         → log_level
    - EY_CRAWL_LOG_FILE          → log_file

    Args:
        config_path: YAML 配置文件路径。

    Returns:
        CrawlerConfig 实例。

    Raises:
        FileNotFoundError: 配置文件不存在。
        yaml.YAMLError: 配置文件格式错误。
    """
    config = CrawlerConfig()

    # ── 加载 YAML 配置 ──
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("配置文件不存在: %s", config_path)
        raise
    except yaml.YAMLError as exc:
        logger.error("配置文件格式错误: %s — %s", config_path, exc)
        raise

    if not raw:
        logger.warning("配置文件为空，使用默认值")
        return config

    # 解析 YAML 中的环境变量引用
    raw = _resolve_dict_env_vars(raw)

    # ── 解析 global 配置段 ──
    global_cfg = raw.get("global", {})
    if global_cfg:
        config.user_agent = global_cfg.get("user_agent", config.user_agent)
        config.contact_email = global_cfg.get("contact_email", config.contact_email)
        config.purpose = global_cfg.get("purpose", config.purpose)
        config.max_url_length = int(global_cfg.get("max_url_length", config.max_url_length))
        config.max_redirects = int(global_cfg.get("max_redirects", config.max_redirects))
        config.max_content_size = int(global_cfg.get("max_content_size", config.max_content_size))
        config.max_retries = int(global_cfg.get("max_retries", config.max_retries))
        config.retry_backoff_base = int(global_cfg.get("retry_backoff_base", config.retry_backoff_base))
        config.output_format = global_cfg.get("output_format", config.output_format)
        config.output_dir = global_cfg.get("output_dir", config.output_dir)
        config.output_name = global_cfg.get("output_name", config.output_name)
        config.dedup_enabled = global_cfg.get("dedup_enabled", config.dedup_enabled)
        config.log_level = global_cfg.get("log_level", config.log_level)
        config.log_file = global_cfg.get("log_file", config.log_file)

        # 速率限制子配置
        rate_cfg = global_cfg.get("rate_limit", {})
        if rate_cfg:
            config.rate_limit_min_delay = float(rate_cfg.get("min_delay", config.rate_limit_min_delay))
            config.rate_limit_max_delay = float(rate_cfg.get("max_delay", config.rate_limit_max_delay))

        # 超时子配置
        timeout_cfg = global_cfg.get("timeout", {})
        if timeout_cfg:
            config.connect_timeout = float(timeout_cfg.get("connect", config.connect_timeout))
            config.read_timeout = float(timeout_cfg.get("read", config.read_timeout))
            config.write_timeout = float(timeout_cfg.get("write", config.write_timeout))

    # ── 解析 sources 配置段 ──
    sources_cfg = raw.get("sources", [])
    config.sources = []
    for src in sources_cfg:
        try:
            source = SourceConfig(
                name=src.get("name", ""),
                url=src.get("url", ""),
                source_type=src.get("source_type", "external"),
                auth_type=src.get("auth_type", "none"),
                auth_env_var=src.get("auth_env_var", ""),
                content_type_hint=src.get("content_type_hint", ""),
                tags=src.get("tags", []),
                category=src.get("category", ""),
                internal_only=src.get("internal_only", False),
            )
            config.sources.append(source)
        except Exception as exc:
            logger.warning("跳过无效数据源配置 '%s': %s", src.get("name", "?"), exc)

    # ── 环境变量覆盖（最高优先级）──
    env_overrides = {
        "EY_CRAWL_USER_AGENT": ("user_agent", str),
        "EY_CRAWL_CONTACT_EMAIL": ("contact_email", str),
        "EY_CRAWL_MAX_URL_LENGTH": ("max_url_length", int),
        "EY_CRAWL_MAX_REDIRECTS": ("max_redirects", int),
        "EY_CRAWL_MAX_CONTENT_SIZE": ("max_content_size", int),
        "EY_CRAWL_RATE_MIN_DELAY": ("rate_limit_min_delay", float),
        "EY_CRAWL_RATE_MAX_DELAY": ("rate_limit_max_delay", float),
        "EY_CRAWL_MAX_RETRIES": ("max_retries", int),
        "EY_CRAWL_RETRY_BACKOFF": ("retry_backoff_base", int),
        "EY_CRAWL_OUTPUT_FORMAT": ("output_format", str),
        "EY_CRAWL_OUTPUT_DIR": ("output_dir", str),
        "EY_CRAWL_LOG_LEVEL": ("log_level", str),
        "EY_CRAWL_LOG_FILE": ("log_file", str),
    }
    for env_var, (attr_name, type_fn) in env_overrides.items():
        env_val = os.environ.get(env_var)
        if env_val is not None:
            setattr(config, attr_name, type_fn(env_val))
            logger.debug("环境变量覆盖: %s → %s=%s", env_var, attr_name, env_val)

    logger.info("已加载配置: %s (%d 个数据源)", config_path, len(config.sources))
    return config
