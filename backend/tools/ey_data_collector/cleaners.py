"""
EY Data Collector — Standalone knowledge content crawler.

INTERNAL USE ONLY. 本脚本仅供 EY 内部员工用于构建新入职培训 AI 知识库，
仅从经授权许可的内部数据源或公开允许抓取的 EY 官方页面获取数据。
使用者须严格遵守 EY 信息安全政策、数据保护法规及目标网站的服务条款。
任何未经授权的抓取行为由使用者自行承担责任。
如涉及第三方版权内容，请确保已获得相应授权或仅提取摘要信息。

内容清洗模块 — XSS 防护的独立实现，逻辑完全对齐
backend/apps/crawler/cleaners.py，但不依赖 Django。

使用 bleach 清除危险 HTML 标签和属性，防止存储型 XSS 攻击。
允许列表（ALLOWED_TAGS / ALLOWED_ATTRIBUTES / ALLOWED_PROTOCOLS）
与现有 ContentCleaner 完全一致。
"""

import bleach
import logging

from .config import CrawlerConfig

logger = logging.getLogger("ey_data_collector.cleaners")

# ────────────────────────────────────────────────────────────────────
# HTML 安全子集 — 对齐 backend/apps/crawler/cleaners.py
# ────────────────────────────────────────────────────────────────────

ALLOWED_TAGS = [
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "a", "blockquote",
    "code", "pre", "table", "thead", "tbody", "tr", "th", "td",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],     # href 仅允许 http/https（通过 ALLOWED_PROTOCOLS）
    "td": ["align"],
    "th": ["align"],
}

# 允许的链接协议 — 禁止 javascript: 和 data: 协议
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


# ────────────────────────────────────────────────────────────────────
# 内容清洗器
# ────────────────────────────────────────────────────────────────────

class ContentCleaner:
    """XSS 内容清洗器 — 对齐 backend/apps/crawler/cleaners.py ContentCleaner。

    使用 bleach 移除危险标签（<script>, <iframe>, <object>, <embed>,
    <style>）和属性（onclick, onload, onerror 等），同时剥离
    <a href> 中的 javascript: 协议。

    max_content_size 从 CrawlerConfig 读取（替代硬编码常量），
    默认 500KB，对齐 KB-V4.1-016 CONTENT-P0-2 内容大小限制。
    """

    def __init__(self, config: CrawlerConfig):
        self.max_content_size = config.max_content_size

    def clean(self, raw_html: str) -> str:
        """bleach 清洗 HTML 内容，移除危险标签和属性。

        对齐 cleaners.py ContentCleaner.clean() 逻辑：
        - 使用相同的 ALLOWED_TAGS / ALLOWED_ATTRIBUTES / ALLOWED_PROTOCOLS
        - strip=True — 完全剥离不允许的标签（而非转义）
        - 超过 max_content_size 字节时抛出 ValueError

        Args:
            raw_html: 从爬取页面提取的原始 HTML 内容。

        Returns:
            仅包含安全标签和属性的清洗后 HTML。

        Raises:
            ValueError: 内容超过 max_content_size 字节限制。
        """
        if len(raw_html) > self.max_content_size:
            logger.warning(
                "内容超过大小限制: %d > %d 字节",
                len(raw_html), self.max_content_size,
            )
            raise ValueError(
                f"内容超过最大限制 {self.max_content_size} 字节 "
                f"（收到 {len(raw_html)} 字节）。"
            )

        cleaned = bleach.clean(
            raw_html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=ALLOWED_PROTOCOLS,
            strip=True,  # 完全剥离不允许的标签（而非转义）
        )

        reduction_pct = int(
            (1 - len(cleaned) / max(len(raw_html), 1)) * 100
        )
        logger.debug(
            "内容清洗: %d → %d 字节（减少 %d%%）",
            len(raw_html), len(cleaned), reduction_pct,
        )

        return cleaned

    def extract_text(self, html_content: str) -> str:
        """提取纯文本，剥离所有 HTML 标签。

        用于生成向量嵌入时不需要 HTML 标记的场景。
        对齐 cleaners.py ContentCleaner.extract_text()。
        """
        return bleach.clean(html_content, tags=[], strip=True)
