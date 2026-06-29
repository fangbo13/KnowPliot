"""
EY Data Collector — Standalone knowledge content crawler.

INTERNAL USE ONLY. 本脚本仅供 EY 内部员工用于构建新入职培训 AI 知识库，
仅从经授权许可的内部数据源或公开允许抓取的 EY 官方页面获取数据。
使用者须严格遵守 EY 信息安全政策、数据保护法规及目标网站的服务条款。
任何未经授权的抓取行为由使用者自行承担责任。
如涉及第三方版权内容，请确保已获得相应授权或仅提取摘要信息。

Pydantic 数据模型定义 — 对齐 backend/apps/crawler/models.py CrawledDocument 字段，
便于后续导入 Django 系统。
"""

from pydantic import BaseModel, Field
from enum import Enum


# ────────────────────────────────────────────────────────────────────
# 内容类型枚举
# ────────────────────────────────────────────────────────────────────

class ContentType(str, Enum):
    """抓取内容格式类型。"""
    HTML = "html"
    PDF = "pdf"
    WORD = "word"
    UNKNOWN = "unknown"


# ────────────────────────────────────────────────────────────────────
# 爬取状态枚举 — 对齐 CrawledDocument.STATUS_CHOICES
# ────────────────────────────────────────────────────────────────────

class CrawlStatus(str, Enum):
    """爬取生命周期状态 — 与现有 CrawledDocument.STATUS_CHOICES 一致。"""
    PENDING = "pending"
    FETCHING = "fetching"
    PARSING = "parsing"
    CLEANING = "cleaning"
    EMBEDDING = "embedding"
    ACTIVE = "active"
    FAILED = "failed"
    WITHDRAWN = "withdrawn"
    DUPLICATE_SKIPPED = "duplicate_skipped"


# ────────────────────────────────────────────────────────────────────
# 版权状态枚举 — 对齐 CrawledDocument.COPYRIGHT_CHOICES
# ────────────────────────────────────────────────────────────────────

class CopyrightStatus(str, Enum):
    """版权分类状态 — 与现有 CrawledDocument.COPYRIGHT_CHOICES 一致。"""
    UNKNOWN = "unknown"
    INTERNAL_ONLY = "internal_only"
    PUBLIC_DOMAIN = "public_domain"
    RESTRICTED = "restricted"


# ────────────────────────────────────────────────────────────────────
# 提取结果模型
# ────────────────────────────────────────────────────────────────────

class ExtractionResult(BaseModel):
    """内容提取结果。"""
    extracted_text: str = ""
    title: str = ""
    content_type: ContentType = ContentType.UNKNOWN
    metadata: dict = Field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────
# 爬取文档记录 — 输出 Schema
# ────────────────────────────────────────────────────────────────────

class CrawledDocumentRecord(BaseModel):
    """输出记录 Schema — 字段对齐 backend/apps/crawler/models.py CrawledDocument，
    便于后续批量导入 Django 系统，字段映射关系：

    - source_url            ↔ CrawledDocument.source_url
    - crawl_status          ↔ CrawledDocument.crawl_status (STATUS_CHOICES)
    - content_hash          ↔ CrawledDocument.content_hash
    - title_extracted       ↔ CrawledDocument.title_extracted
    - raw_content_size      ↔ CrawledDocument.raw_content_size
    - cleaned_content_size  ↔ CrawledDocument.cleaned_content_size
    - copyright_status      ↔ CrawledDocument.copyright_status (COPYRIGHT_CHOICES)
    - internal_only         ↔ CrawledDocument.internal_only
    - robots_txt_allowed    ↔ CrawledDocument.robots_txt_allowed
    - crawl_delay_seconds   ↔ CrawledDocument.crawl_delay_seconds
    - error_message         ↔ CrawledDocument.error_message

    以下为独立脚本扩展字段（不影响 Django 导入兼容性）：
    - source_name, final_url, redirect_count, content_type, tags, category,
      extracted_text, processing_time_ms, crawled_at
    """
    source_url: str = ""
    source_name: str = ""
    crawl_status: CrawlStatus = CrawlStatus.PENDING
    title_extracted: str = ""
    extracted_text: str = ""
    content_hash: str = ""
    content_type: ContentType = ContentType.HTML
    raw_content_size: int = 0
    cleaned_content_size: int = 0
    final_url: str = ""
    redirect_count: int = 0
    copyright_status: CopyrightStatus = CopyrightStatus.UNKNOWN
    internal_only: bool = False
    robots_txt_allowed: bool = True
    crawl_delay_seconds: float = 0.0
    error_message: str = ""
    tags: list[str] = Field(default_factory=list)
    category: str = ""
    processing_time_ms: int = 0
    crawled_at: str = ""  # ISO 8601 时间戳


# ────────────────────────────────────────────────────────────────────
# 源配置模型
# ────────────────────────────────────────────────────────────────────

class SourceConfig(BaseModel):
    """单个数据源配置。"""
    name: str
    url: str
    source_type: str = "external"      # "internal" | "external"
    auth_type: str = "none"            # "none" | "kerberos" | "api_key" | "bearer"
    auth_env_var: str = ""             # 认证凭据的环境变量名
    content_type_hint: str = ""        # "html" | "pdf" | "word" | ""（自动检测）
    tags: list[str] = Field(default_factory=list)
    category: str = ""
    internal_only: bool = False
