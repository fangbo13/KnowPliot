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

速率限制模块 — 随机延迟 + 动态响应头调整。

基础行为：每次 HTTP 请求间加入随机延迟（2~5 秒，可配置）。
动态调整：根据响应头中的限流信息自动调整间隔：
  - Retry-After: 直接使用指定延迟值（覆盖基础延迟）
  - X-RateLimit-Remaining == 0: 根据 X-RateLimit-Reset 计算延迟
  - RateLimit-Policy: 解析策略中的窗口信息

同时维护每个域名的最近请求时间，确保同一域名两次请求间
至少有 min_delay 的间隔。
"""

import random
import time
import logging

from .config import CrawlerConfig

logger = logging.getLogger("ey_data_collector.rate_limiter")


class RateLimiter:
    """速率限制器 — 随机延迟 + 动态响应头调整。

    请求间基础延迟: random.uniform(min_delay, max_delay)
    动态延迟: 根据 HTTP 响应头中的限流信息调整（覆盖基础延迟）

    域名级别追踪: 维护每个域名的最近请求时间戳，
    确保同一域名两次请求间至少有 min_delay 的间隔。
    """

    def __init__(self, config: CrawlerConfig):
        self.min_delay = config.rate_limit_min_delay
        self.max_delay = config.rate_limit_max_delay
        self._domain_last_request: dict[str, float] = {}

    def wait(
        self,
        domain: str,
        response_headers: dict[str, str] | None = None,
    ) -> float:
        """在下次请求前应用速率限制延迟。

        策略优先级：
        1. 如果响应头包含 Retry-After → 使用该值（429 场景）
        2. 如果 X-RateLimit-Remaining == 0 → 根据 Reset 计算延迟
        3. 计算自上次请求到该域名以来的已等待时间
        4. 基础延迟 = random.uniform(min_delay, max_delay)
        5. 最终延迟 = max(基础延迟 - 已等待时间, 0)

        Args:
            domain: 目标域名（用于域名级别追踪）。
            response_headers: 上次请求的响应头（用于动态调整）。

        Returns:
            实际等待的秒数。
        """
        # ── 优先级 1: Retry-After 头 ──
        dynamic_delay = 0.0
        if response_headers:
            retry_after = response_headers.get("retry-after")
            if retry_after:
                try:
                    # Retry-After 可能是秒数或 HTTP 日期
                    dynamic_delay = float(retry_after)
                except ValueError:
                    # 尝试解析为 HTTP 日期格式
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(retry_after)
                        dynamic_delay = max(0, dt.timestamp() - time.time())
                    except Exception:
                        dynamic_delay = 0.0

                if dynamic_delay > 0:
                    logger.info(
                        "Retry-After 头指定延迟: %.1f 秒（域名 %s）",
                        dynamic_delay, domain,
                    )
                    time.sleep(dynamic_delay)
                    self._domain_last_request[domain] = time.time()
                    return dynamic_delay

            # ── 优先级 2: X-RateLimit-Remaining == 0 ──
            remaining = response_headers.get("x-ratelimit-remaining")
            if remaining and int(remaining) == 0:
                reset_ts = response_headers.get("x-ratelimit-reset")
                if reset_ts:
                    try:
                        reset_time = float(reset_ts)
                        delay = max(0, reset_time - time.time())
                        logger.info(
                            "X-RateLimit-Remaining=0，等待至 Reset: %.1f 秒（域名 %s）",
                            delay, domain,
                        )
                        time.sleep(delay)
                        self._domain_last_request[domain] = time.time()
                        return delay
                    except ValueError:
                        pass

        # ── 基础延迟：随机间隔 ──
        base_delay = random.uniform(self.min_delay, self.max_delay)

        # ── 域名级别追踪：确保同一域名两次请求间至少 min_delay ──
        last_time = self._domain_last_request.get(domain, 0.0)
        elapsed = time.time() - last_time
        actual_delay = max(base_delay - elapsed, 0.0)

        if actual_delay > 0:
            logger.debug(
                "速率限制: 等待 %.2f 秒（域名 %s，基础 %.2f，已过 %.2f）",
                actual_delay, domain, base_delay, elapsed,
            )
            time.sleep(actual_delay)

        self._domain_last_request[domain] = time.time()
        return actual_delay
