"""
EY Data Collector — Standalone knowledge content crawler.

INTERNAL USE ONLY. 本脚本仅供 EY 内部员工用于构建新入职培训 AI 知识库，
仅从经授权许可的内部数据源或公开允许抓取的 EY 官方页面获取数据。
使用者须严格遵守 EY 信息安全政策、数据保护法规及目标网站的服务条款。
任何未经授权的抓取行为由使用者自行承担责任。
如涉及第三方版权内容，请确保已获得相应授权或仅提取摘要信息。

主协调器 + CLI 入口 — 完整爬取工作流：

1. 加载配置（YAML + 环境变量）
2. 认证预检（Kerberos / API Key / Bearer Token）
3. URL 校验（SSRF 防护）
4. DNS rebinding 重新校验（time-of-use 检查）
5. robots.txt 合规检查
6. 速率限制延迟
7. 通过 httpx 获取内容
8. 重定向链 IP 校验
9. 内容类型检测
10. 多格式提取（HTML/PDF/Word）
11. 内容清洗（bleach XSS 防护）
12. SHA256 哈希去重
13. 写入输出（JSONL/CSV）

对齐现有 backend/apps/crawler/services.py CrawlerService.crawl_url() 工作流，
但为独立脚本（不依赖 Django/Celery）。

运行方式:
    # 批量模式 — 从 YAML 配置文件读取数据源
    python -m ey_data_collector --config sources.yaml

    # 单 URL 模式
    python -m ey_data_collector --url "https://www.ey.com/en/careers/culture" --name "EY Careers"

    # 仅爬取内部数据源
    python -m ey_data_collector --config sources.yaml --source-type-filter internal

    # 试运行（验证配置、检查认证、不实际爬取）
    python -m ey_data_collector --config sources.yaml --dry-run

    # 自定义速率限制
    python -m ey_data_collector --config sources.yaml --min-delay 5.0 --max-delay 10.0

环境变量配置:
    export EY_CRAWL_USER_AGENT="EY-DataCollector/1.0"
    export EY_CRAWL_CONTACT_EMAIL="your.name@ey.com"
    export EY_CRAWL_LOG_LEVEL="DEBUG"
    export EY_INTERNAL_API_TOKEN="your-token-here"
    export EY_TRAINING_API_KEY="your-key-here"

合规性验证:
    1. 试运行模式 (--dry-run) 会检查所有数据源的认证凭据和 robots.txt
    2. 日志中所有 SSRF 阻断和 robots.txt 拒绝都有明确记录
    3. 使用 --skip-robots 或 --skip-ssrf 时会有警告日志

输出文件:
    - JSONL: 每行一条 CrawledDocumentRecord JSON 对象
    - CSV:  每行一条爬取记录，列名对齐 CrawledDocument 字段
    - 日志:  结构化日志（时间戳 | 级别 | 模块 | 信息）
"""

import argparse
import asyncio
import hashlib
import httpx
import logging
import os
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

from .config import CrawlerConfig, load_config
from .models import (
    CrawledDocumentRecord,
    CrawlStatus,
    ContentType,
    CopyrightStatus,
    SourceConfig,
)
from .validators import CrawlURLValidator
from .cleaners import ContentCleaner
from .robots import RobotsTxtChecker
from .rate_limiter import RateLimiter
from .auth import AuthHandler
from .extractors import MultiFormatExtractor, detect_content_type
from .storage import create_writer, DedupTracker

logger = logging.getLogger("ey_data_collector")


# ────────────────────────────────────────────────────────────────────
# 日志配置
# ────────────────────────────────────────────────────────────────────

def setup_logging(config: CrawlerConfig) -> None:
    """配置结构化日志。

    格式: 2026-06-26 14:30:00 | INFO     | ey_data_collector | Message
    对齐 backend/apps/crawler/services.py 的 logging.getLogger(__name__) 模式。
    """
    root_logger = logging.getLogger("ey_data_collector")
    root_logger.setLevel(getattr(logging, config.log_level.upper()))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出（stdout）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件输出（可选）
    if config.log_file:
        os.makedirs(os.path.dirname(config.log_file) or ".", exist_ok=True)
        file_handler = logging.FileHandler(config.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


# ────────────────────────────────────────────────────────────────────
# 主协调器
# ────────────────────────────────────────────────────────────────────

class EYDataCollector:
    """主协调器 — 独立版 CrawlerService + Celery task 工作流。

    工作流（对齐 backend/apps/crawler/services.py CrawlerService.crawl_url）:
    1. 认证预检 → 2. URL 校验 → 3. DNS rebinding 重新校验 →
    4. robots.txt → 5. 速率限制 → 6. httpx 获取 → 7. 重定向链 →
    8. 内容类型检测 → 9. 多格式提取 → 10. 内容清洗 → 11. SHA256 去重 →
    12. 写入输出
    """

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.validator = CrawlURLValidator(config)
        self.robots_checker = RobotsTxtChecker(self.validator)
        self.rate_limiter = RateLimiter(config)
        self.auth_handler = AuthHandler()
        self.extractor = MultiFormatExtractor(config)
        self.dedup_tracker = DedupTracker()
        self.writer = create_writer(
            config.output_format,
            config.output_dir,
            config.output_name,
        )

        # 统计
        self._stats = {
            "success": 0,
            "failed": 0,
            "duplicate_skipped": 0,
            "auth_skipped": 0,
            "robots_blocked": 0,
            "ssrf_blocked": 0,
            "total": 0,
        }

    async def crawl_url(self, source: SourceConfig) -> CrawledDocumentRecord:
        """完整爬取工作流 — 对齐 CrawlerService.crawl_url()。

        Args:
            source: 数据源配置。

        Returns:
            CrawledDocumentRecord 包含爬取结果或错误信息。
        """
        url = source.url
        is_internal = source.source_type == "internal"
        self._stats["total"] += 1

        record = CrawledDocumentRecord(
            source_url=url,
            source_name=source.name,
            crawl_status=CrawlStatus.PENDING,
            internal_only=source.internal_only,
            tags=source.tags,
            category=source.category,
            copyright_status=(
                CopyrightStatus.INTERNAL_ONLY
                if is_internal
                else CopyrightStatus.UNKNOWN
            ),
        )

        start_time = time.time()

        try:
            # ── Step 1: 认证预检 ──
            available, msg = self.auth_handler.check_credentials_available(source)
            if not available:
                logger.warning("认证凭据缺失 — 跳过数据源 '%s': %s", source.name, msg)
                record.crawl_status = CrawlStatus.FAILED
                record.error_message = msg
                self._stats["auth_skipped"] += 1
                self.writer.write(record)
                return record

            # ── Step 2: URL 校验（SSRF 防护） ──
            if not self.config.skip_ssrf:
                is_valid, reason = self.validator.validate(url, is_internal=is_internal)
                if not is_valid:
                    logger.warning("URL 校验失败: %s — %s", url, reason)
                    record.crawl_status = CrawlStatus.FAILED
                    record.error_message = reason
                    self._stats["ssrf_blocked"] += 1
                    self.writer.write(record)
                    return record

            # V4.2 SYS-V4.2-002: DNS rebinding 重新校验（仅外部数据源）
            if not is_internal and not self.config.skip_ssrf:
                parsed = urlparse(url)
                hostname = parsed.hostname
                if hostname:
                    from .validators import _validate_hostname_ips
                    is_public, dns_reason = _validate_hostname_ips(hostname)
                    if not is_public:
                        raise ValueError(
                            f"DNS rebinding 检测: 主机名 '{hostname}' "
                            f"在获取时解析到私有 IP — {dns_reason}"
                        )

            # ── Step 3: robots.txt 合规检查 ──
            if not self.config.skip_robots:
                is_allowed, crawl_delay = self.robots_checker.can_fetch(
                    url, self.config.user_agent, is_internal=is_internal,
                )
                record.robots_txt_allowed = is_allowed
                record.crawl_delay_seconds = crawl_delay

                if not is_allowed:
                    logger.info("robots.txt 拒绝爬取: %s", url)
                    record.crawl_status = CrawlStatus.FAILED
                    record.error_message = f"robots.txt 禁止爬取: {url}"
                    self._stats["robots_blocked"] += 1
                    self.writer.write(record)
                    return record

                if crawl_delay > 0:
                    logger.info("遵守 Crawl-delay %.1f 秒: %s", crawl_delay, url)
                    time.sleep(crawl_delay)

            # ── Step 4: 速率限制 ──
            domain = urlparse(url).hostname or url
            self.rate_limiter.wait(domain)

            # ── Step 5: 通过 httpx 获取内容 ──
            record.crawl_status = CrawlStatus.FETCHING
            auth_headers = self.auth_handler.get_auth_headers(source)

            client = httpx.AsyncClient(
                verify=True,
                timeout=httpx.Timeout(
                    connect=self.config.connect_timeout,
                    read=self.config.read_timeout,
                    write=self.config.write_timeout,
                    pool=5.0,
                ),
                follow_redirects=True,
                max_redirects=self.config.max_redirects,
                headers=self._build_headers(source, auth_headers),
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )

            try:
                response = await client.get(url)
            except httpx.TimeoutException:
                raise ValueError(f"获取 URL 超时: {url}")
            except httpx.RequestError as exc:
                raise ValueError(f"获取 URL 网络错误: {exc}")
            finally:
                await client.aclose()

            # ── Step 6: 响应状态校验 ──
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code} 响应: {url}")

            # ── Step 7: 重定向链 IP 校验（仅外部数据源） ──
            if not is_internal and not self.config.skip_ssrf:
                is_valid_chain, chain_reason = self.validator.validate_redirect_chain(
                    response, is_internal=is_internal,
                )
                if not is_valid_chain:
                    raise ValueError(f"重定向链校验失败: {chain_reason}")

            # ── Step 8: 内容类型检测 ──
            content_type_header = response.headers.get("content-type", "")
            content_type = detect_content_type(
                url=url,
                content_type_header=content_type_header,
                content_bytes=response.content,
                hint=source.content_type_hint,
            )

            logger.info("内容类型检测: %s → %s", url, content_type)

            # ── Step 9: 多格式提取 ──
            record.crawl_status = CrawlStatus.PARSING
            extraction = self.extractor.extract(
                content_bytes=response.content,
                content_type=content_type,
                url=str(response.url),
                html_text=response.text if content_type == ContentType.HTML else "",
            )

            if not extraction.extracted_text:
                raise ValueError("无法提取文本内容")

            # ── Step 10: 记录提取结果 ──
            record.title_extracted = extraction.title
            record.extracted_text = extraction.extracted_text
            record.content_type = content_type
            record.raw_content_size = len(response.content)
            record.cleaned_content_size = len(extraction.extracted_text)
            record.final_url = str(response.url)
            record.redirect_count = len(response.history)

            # ── Step 11: SHA256 去重 ──
            if self.config.dedup_enabled:
                content_hash = self.dedup_tracker.compute_hash(extraction.extracted_text)
                record.content_hash = content_hash

                if self.dedup_tracker.is_duplicate(content_hash):
                    existing_source = self.dedup_tracker.get_existing_source(content_hash)
                    record.crawl_status = CrawlStatus.DUPLICATE_SKIPPED
                    record.error_message = (
                        f"内容哈希重复，匹配已爬取文档: {existing_source}"
                    )
                    self._stats["duplicate_skipped"] += 1
                    logger.info("去重跳过: %s — 哈希匹配 %s", url, existing_source[:80])
                    self.writer.write(record)
                    return record

                self.dedup_tracker.mark_seen(content_hash, url)

            else:
                record.content_hash = self.dedup_tracker.compute_hash(
                    extraction.extracted_text,
                )

            # ── Step 12: 成功 ──
            record.crawl_status = CrawlStatus.ACTIVE
            record.crawled_at = datetime.now().isoformat()
            processing_time_ms = int((time.time() - start_time) * 1000)
            record.processing_time_ms = processing_time_ms

            self._stats["success"] += 1
            logger.info(
                "爬取成功: %s — %d 字符, 标题='%s', 耗时 %d ms",
                url, record.cleaned_content_size, record.title_extracted[:50],
                processing_time_ms,
            )

            self.writer.write(record)
            return record

        except Exception as exc:
            # ── 错误处理 ──
            record.crawl_status = CrawlStatus.FAILED
            record.error_message = str(exc)[:1000]
            record.crawled_at = datetime.now().isoformat()
            processing_time_ms = int((time.time() - start_time) * 1000)
            record.processing_time_ms = processing_time_ms

            self._stats["failed"] += 1
            logger.error("爬取失败: %s — %s", url, exc, exc_info=True)

            self.writer.write(record)
            return record

    async def crawl_url_with_retry(self, source: SourceConfig) -> CrawledDocumentRecord:
        """带指数退避重试的爬取工作流。

        重试策略对齐 Celery task: delay = 60 * 2^attempt
        - 第一次重试: 60 秒延迟
        - 第二次重试: 120 秒延迟
        - 第三次重试: 240 秒延迟

        仅对可重试错误进行重试（网络超时、HTTP 502/503/504），
        不可重试错误（SSRF 阻断、robots.txt 拒绝、HTTP 404）直接失败。

        Args:
            source: 数据源配置。

        Returns:
            最终的 CrawledDocumentRecord（成功或失败）。
        """
        max_retries = self.config.max_retries

        for attempt in range(max_retries + 1):
            result = await self.crawl_url(source)

            # 成功或不可重试错误 → 直接返回
            if result.crawl_status == CrawlStatus.ACTIVE:
                return result
            if result.crawl_status == CrawlStatus.DUPLICATE_SKIPPED:
                return result

            # 检查是否为可重试错误
            error_msg = result.error_message
            is_retriable = self._is_retriable_error(error_msg)

            if not is_retriable or attempt >= max_retries:
                if attempt >= max_retries:
                    logger.error(
                        "爬取在 %d 次重试后最终失败: %s — %s",
                        max_retries, source.url, error_msg,
                    )
                return result

            # 指数退避延迟
            delay = self.config.retry_backoff_base * (2 ** attempt)
            logger.warning(
                "重试: %s — 第 %d/%d 次, 延迟 %d 秒, 错误=%s",
                source.url, attempt + 1, max_retries, delay, error_msg[:80],
            )
            time.sleep(delay)

        return result

    def _is_retriable_error(self, error_msg: str) -> bool:
        """判断错误是否可重试。

        可重试: 网络超时、HTTP 502/503/504、连接错误
        不可重试: SSRF 阻断、robots.txt 拒绝、HTTP 400/401/403/404、内容大小超限
        """
        retriable_patterns = [
            "获取 URL 超时",
            "网络错误",
            "HTTP 502",
            "HTTP 503",
            "HTTP 504",
            "TimeoutException",
            "ConnectError",
            "RequestError",
        ]
        for pattern in retriable_patterns:
            if pattern in error_msg:
                return True

        return False

    async def crawl_batch(
        self,
        sources: list[SourceConfig],
        source_type_filter: str = "",
        tag_filter: str = "",
        category_filter: str = "",
    ) -> list[CrawledDocumentRecord]:
        """批量爬取数据源 — 逐个爬取（遵守速率限制）。

        Args:
            sources: 数据源列表。
            source_type_filter: 仅爬取此类型的数据源（"internal"/"external"）。
            tag_filter: 仅爬取含此标签的数据源。
            category_filter: 仅爬取此分类的数据源。

        Returns:
            所有爬取结果列表。
        """
        # 过滤数据源
        filtered = sources
        if source_type_filter:
            filtered = [s for s in filtered if s.source_type == source_type_filter]
        if tag_filter:
            filtered = [s for s in filtered if tag_filter in s.tags]
        if category_filter:
            filtered = [s for s in filtered if s.category == category_filter]

        logger.info("开始批量爬取: %d 个数据源（过滤后）", len(filtered))

        results = []
        for source in filtered:
            result = await self.crawl_url_with_retry(source)
            results.append(result)

        # 打印统计摘要
        logger.info(
            "批量爬取完成: %d 成功, %d 失败, %d 去重跳过, "
            "%d 认证跳过, %d robots.txt 阻断, %d SSRF 阻断, %d 总计",
            self._stats["success"],
            self._stats["failed"],
            self._stats["duplicate_skipped"],
            self._stats["auth_skipped"],
            self._stats["robots_blocked"],
            self._stats["ssrf_blocked"],
            self._stats["total"],
        )

        return results

    def _build_headers(
        self,
        source: SourceConfig,
        auth_headers: dict[str, str],
    ) -> dict[str, str]:
        """构建请求头 — User-Agent + X-Contact + X-Purpose + 认证头。

        对齐 backend/apps/crawler/services.py 的 CRAWL_USER_AGENT 设置，
        同时满足用户要求:
        - 真实 User-Agent: EY-DataCollector/1.0
        - X-Contact 头: 内网邮箱
        - X-Purpose 头: 用途说明
        """
        headers = {
            "User-Agent": self.config.user_agent,
        }

        # X-Contact 头（内网邮箱，便于管理员联系）
        if self.config.contact_email:
            headers["X-Contact"] = self.config.contact_email

        # X-Purpose 头（用途说明，便于外部站点理解请求目的）
        headers["X-Purpose"] = self.config.purpose

        # 认证头
        headers.update(auth_headers)

        return headers

    def dry_run(self, sources: list[SourceConfig]) -> None:
        """试运行 — 验证配置和数据源，不实际爬取。

        检查项:
        1. 每个数据源的认证凭据是否可用
        2. 外部数据源的 robots.txt 是否允许爬取
        3. 外部数据源的 SSRF 校验是否通过
        4. 输出目录是否可写

        Args:
            sources: 数据源列表。
        """
        logger.info("========== 试运行 (Dry Run) ========== ")
        logger.info("配置摘要:")
        logger.info("  User-Agent: %s", self.config.user_agent)
        logger.info("  速率限制: %.1f ~ %.1f 秒", self.config.rate_limit_min_delay, self.config.rate_limit_max_delay)
        logger.info("  最大重试: %d 次", self.config.max_retries)
        logger.info("  输出格式: %s", self.config.output_format)
        logger.info("  输出目录: %s", self.config.output_dir)
        logger.info("  去重: %s", "启用" if self.config.dedup_enabled else "禁用")
        logger.info("  SSRF 校验: %s", "启用" if not self.config.skip_ssrf else "跳过")
        logger.info("  robots.txt 检查: %s", "启用" if not self.config.skip_robots else "跳过")
        logger.info("  数据源数量: %d", len(sources))

        # 检查输出目录
        try:
            os.makedirs(self.config.output_dir, exist_ok=True)
            logger.info("  [OK] 输出目录可写: %s", self.config.output_dir)
        except OSError as exc:
            logger.error("  [FAIL] 输出目录不可写: %s -- %s", self.config.output_dir, exc)

        # 检查每个数据源
        for i, source in enumerate(sources, 1):
            logger.info("--- 数据源 #%d: %s ---", i, source.name)
            is_internal = source.source_type == "internal"

            # 认证检查
            available, msg = self.auth_handler.check_credentials_available(source)
            if available:
                logger.info("  [OK] 认证: %s", msg)
            else:
                logger.warning("  [FAIL] 认证: %s", msg)

            # SSRF 校验（仅外部数据源）
            if not is_internal and not self.config.skip_ssrf:
                is_valid, reason = self.validator.validate(source.url)
                if is_valid:
                    logger.info("  [OK] SSRF: URL 校验通过")
                else:
                    logger.warning("  [FAIL] SSRF: %s", reason)

            # robots.txt 检查（仅外部数据源）
            if not is_internal and not self.config.skip_robots:
                is_allowed, delay = self.robots_checker.can_fetch(
                    source.url, self.config.user_agent,
                )
                if is_allowed:
                    logger.info("  [OK] robots.txt: 允许爬取 (Crawl-delay=%.1f秒)", delay)
                else:
                    logger.warning("  [FAIL] robots.txt: 禁止爬取")

        logger.info("========== 试运行结束 ========== ")


# ────────────────────────────────────────────────────────────────────
# CLI 入口
# ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description=(
            "EY Data Collector — 从经授权许可的内部/外部数据源抓取新入职培训知识内容。\n"
            "INTERNAL USE ONLY — 仅供 EY 内部使用。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m ey_data_collector --config sources.yaml\n"
            "  python -m ey_data_collector --url https://www.ey.com/en/careers --name 'EY Careers'\n"
            "  python -m ey_data_collector --config sources.yaml --dry-run\n"
            "  python -m ey_data_collector --config sources.yaml --source-type-filter internal\n"
        ),
    )

    # ── 批量模式 ──
    parser.add_argument(
        "--config", type=str, default="",
        help="YAML 配置文件路径（批量模式必需）",
    )

    # ── 单 URL 模式 ──
    parser.add_argument(
        "--url", type=str, default="",
        help="单个爬取 URL（跳过配置文件数据源）",
    )
    parser.add_argument(
        "--name", type=str, default="",
        help="数据源名称（单 URL 模式）",
    )
    parser.add_argument(
        "--source-type", type=str, default="external",
        choices=["internal", "external"],
        help="数据源类型（单 URL 模式）",
    )
    parser.add_argument(
        "--auth-type", type=str, default="none",
        choices=["none", "kerberos", "api_key", "bearer"],
        help="认证方式（单 URL 模式）",
    )
    parser.add_argument(
        "--auth-env-var", type=str, default="",
        help="认证凭据环境变量名（单 URL 模式）",
    )
    parser.add_argument(
        "--content-type", type=str, default="",
        choices=["html", "pdf", "word", ""],
        help="内容类型提示（单 URL 模式，空=自动检测）",
    )
    parser.add_argument(
        "--internal-only", type=str, default="false",
        choices=["true", "false"],
        help="标记为内部专用（单 URL 模式）",
    )

    # ── 输出 ──
    parser.add_argument(
        "--output-format", type=str, default="jsonl",
        choices=["jsonl", "csv"],
        help="输出格式（默认 jsonl）",
    )
    parser.add_argument(
        "--output-dir", type=str, default="./output",
        help="输出目录路径",
    )
    parser.add_argument(
        "--output-name", type=str, default="",
        help="输出文件名（空则自动生成）",
    )

    # ── 速率限制 ──
    parser.add_argument(
        "--min-delay", type=float, default=2.0,
        help="请求间最小延迟秒数（默认 2.0）",
    )
    parser.add_argument(
        "--max-delay", type=float, default=5.0,
        help="请求间最大延迟秒数（默认 5.0）",
    )

    # ── 重试 ──
    parser.add_argument(
        "--max-retries", type=int, default=3,
        help="最大重试次数（默认 3）",
    )
    parser.add_argument(
        "--retry-backoff", type=int, default=60,
        help="基础退避秒数（默认 60）",
    )

    # ── 过滤 ──
    parser.add_argument(
        "--source-type-filter", type=str, default="",
        choices=["internal", "external"],
        help="仅爬取此类型的数据源",
    )
    parser.add_argument(
        "--tag-filter", type=str, default="",
        help="仅爬取含此标签的数据源",
    )
    parser.add_argument(
        "--category-filter", type=str, default="",
        help="仅爬取此分类的数据源",
    )

    # ── 日志 ──
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认 INFO）",
    )
    parser.add_argument(
        "--log-file", type=str, default="",
        help="日志文件路径（默认仅 stdout）",
    )

    # ── 去重 ──
    parser.add_argument(
        "--no-dedup", action="store_true",
        help="禁用 SHA256 去重检查",
    )

    # ── 安全开关 ──
    parser.add_argument(
        "--skip-robots", action="store_true",
        help="跳过 robots.txt 合规检查（不建议）",
    )
    parser.add_argument(
        "--skip-ssrf", action="store_true",
        help="跳过 SSRF 校验（不建议，危险）",
    )

    # ── 试运行 ──
    parser.add_argument(
        "--dry-run", action="store_true",
        help="试运行 — 验证配置和数据源，不实际爬取",
    )

    return parser.parse_args()


async def async_main() -> None:
    """异步主入口 — 解析参数、加载配置、执行爬取。"""
    args = parse_args()

    # ── 构建配置 ──
    if args.config:
        config = load_config(args.config)
    else:
        # 默认配置（单 URL 模式）
        config = CrawlerConfig()

    # ── CLI 参数覆盖 ──
    config.output_format = args.output_format
    config.output_dir = args.output_dir
    config.output_name = args.output_name
    config.rate_limit_min_delay = args.min_delay
    config.rate_limit_max_delay = args.max_delay
    config.max_retries = args.max_retries
    config.retry_backoff_base = args.retry_backoff
    config.log_level = args.log_level
    config.log_file = args.log_file
    config.dedup_enabled = not args.no_dedup
    config.skip_robots = args.skip_robots
    config.skip_ssrf = args.skip_ssrf

    if args.skip_robots:
        logger.warning("⚠ 已跳过 robots.txt 合规检查 — 请确保目标站点允许爬取")
    if args.skip_ssrf:
        logger.warning("⚠ 已跳过 SSRF 校验 — 此操作有安全风险，仅用于开发调试")

    # ── 设置日志 ──
    setup_logging(config)

    # ── 构建数据源列表 ──
    sources = config.sources

    if args.url:
        # 单 URL 模式
        single_source = SourceConfig(
            name=args.name or args.url[:80],
            url=args.url,
            source_type=args.source_type,
            auth_type=args.auth_type,
            auth_env_var=args.auth_env_var,
            content_type_hint=args.content_type,
            internal_only=args.internal_only == "true",
        )
        sources = [single_source]

    if not sources:
        logger.error("未指定数据源 — 请使用 --config 或 --url 参数")
        sys.exit(1)

    # ── 初始化协调器 ──
    collector = EYDataCollector(config)

    # ── 试运行 ──
    if args.dry_run:
        collector.dry_run(sources)
        return

    # ── 打印免责声明 ──
    logger.info(
        "本脚本仅供 EY 内部员工用于构建新入职培训 AI 知识库，"
        "仅从经授权许可的内部数据源或公开允许抓取的 EY 官方页面获取数据。"
    )

    # ── 执行爬取 ──
    results = await collector.crawl_batch(
        sources=sources,
        source_type_filter=args.source_type_filter,
        tag_filter=args.tag_filter,
        category_filter=args.category_filter,
    )

    # ── 关闭输出 ──
    collector.writer.close()

    # ── 打印最终统计 ──
    success_count = sum(1 for r in results if r.crawl_status == CrawlStatus.ACTIVE)
    failed_count = sum(1 for r in results if r.crawl_status == CrawlStatus.FAILED)
    dedup_count = sum(1 for r in results if r.crawl_status == CrawlStatus.DUPLICATE_SKIPPED)

    logger.info(
        "========== 最终统计 ========== "
        "总计: %d | 成功: %d | 失败: %d | 去重跳过: %d",
        len(results), success_count, failed_count, dedup_count,
    )

    # 输出文件路径
    logger.info("输出文件: %s", collector.writer.output_path)


def main() -> None:
    """同步主入口 — 包装异步主入口。"""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
