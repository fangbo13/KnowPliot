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

robots.txt 合规检查模块 — 独立实现，逻辑对齐
backend/apps/crawler/services.py RobotsTxtChecker，
使用内存字典缓存替代 Django cache framework。

V4.2 SYS-V4.2-005: robots.txt 预取 URL IP 校验 — 防止通过
robots.txt 预取本身的 SSRF 攻击向量。
"""

import time
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from .validators import CrawlURLValidator

logger = logging.getLogger("ey_data_collector.robots")

# robots.txt 缓存 TTL — 24 小时，与现有服务一致
ROBOTS_CACHE_TTL = 86400


class RobotsTxtChecker:
    """robots.txt 合规检查器 — 对齐 services.py RobotsTxtChecker。

    独立实现使用内存字典缓存替代 Django cache framework。
    缓存键为域名，值为 (RobotFileParser, timestamp) 元组。
    缓存 TTL 为 24 小时。

    V4.2 SYS-V4.2-005: 预取 robots.txt 前，校验其 URL 解析的 IP
    是否为私有地址（SSRF 防护）。

    对于内部数据源（is_internal=True），默认跳过 robots.txt 检查
    （内网站点通常没有 robots.txt 文件）。
    """

    def __init__(self, validator: CrawlURLValidator):
        self.validator = validator
        self._cache: dict[str, tuple[RobotFileParser, float]] = {}

    def can_fetch(
        self,
        url: str,
        user_agent: str,
        is_internal: bool = False,
    ) -> tuple[bool, float]:
        """检查 URL 是否被站点的 robots.txt 允许爬取。

        对齐 services.py RobotsTxtChecker.can_fetch() 逻辑：
        1. 内部数据源默认跳过（返回 True）
        2. V4.2 SYS-V4.2-005: 校验 robots.txt URL IP（SSRF 防护）
        3. 优先从缓存读取
        4. 缓存不存在时预取并解析 robots.txt
        5. robots.txt 不可达时默认允许（保守策略：无 robots.txt = 允许）

        Args:
            url: 待爬取的 URL。
            user_agent: 爬虫 User-Agent 标识。
            is_internal: 是否为内部数据源（跳过检查）。

        Returns:
            (is_allowed, crawl_delay_seconds) — 是否允许及 Crawl-delay 值。
        """
        # 内部数据源默认跳过 robots.txt 检查
        if is_internal:
            logger.info("内部数据源 — 跳过 robots.txt 检查: %s", url)
            return True, 0.0

        parsed = urlparse(url)
        domain = parsed.hostname
        if not domain:
            return False, 0.0

        robots_url = f"https://{domain}/robots.txt"

        # V4.2 SYS-V4.2-005: 校验 robots.txt 预取 URL IP
        is_valid, reason = self.validator.validate_robots_txt_url(robots_url)
        if not is_valid:
            logger.warning(
                "robots.txt 预取被阻断: %s — %s — 默认拒绝爬取",
                url, reason,
            )
            return False, 0.0  # 保守策略：robots.txt 不安全时拒绝

        # 优先从缓存读取
        cache_key = domain
        cached_entry = self._cache.get(cache_key)
        if cached_entry is not None:
            rp, timestamp = cached_entry
            # 检查缓存是否过期
            if time.time() - timestamp < ROBOTS_CACHE_TTL:
                pass  # 缓存有效，使用缓存的 rp
            else:
                # 缓存过期，清除并重新获取
                self._cache.pop(cache_key, None)
                rp = None
        else:
            rp = None

        # 缓存不存在或过期时预取 robots.txt
        if rp is None:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                self._cache[cache_key] = (rp, time.time())
                logger.info("已获取并缓存 robots.txt: %s", domain)
            except Exception as exc:
                logger.warning("无法获取 robots.txt: %s — %s", domain, exc)
                # robots.txt 不可达时默认允许（保守策略：无 robots.txt = 允许）
                return True, 0.0

        is_allowed = rp.can_fetch(user_agent, url)
        crawl_delay = rp.crawl_delay(user_agent) or 0.0

        if not is_allowed:
            logger.info("robots.txt DISALLOW: %s 被 %s", url, user_agent)

        return is_allowed, float(crawl_delay)
