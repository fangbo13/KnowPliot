"""
EY Data Collector — Standalone knowledge content crawler.

INTERNAL USE ONLY. 本脚本仅供 EY 内部员工用于构建新入职培训 AI 知识库，
仅从经授权许可的内部数据源或公开允许抓取的 EY 官方页面获取数据。
使用者须严格遵守 EY 信息安全政策、数据保护法规及目标网站的服务条款。
任何未经授权的抓取行为由使用者自行承担责任。
如涉及第三方版权内容，请确保已获得相应授权或仅提取摘要信息。

存储输出模块 — JSON Lines / CSV 格式写入 + SHA256 去重追踪。

输出 Schema 字段对齐 backend/apps/crawler/models.py CrawledDocument，
便于后续批量导入 Django 知识库系统。
"""

import csv
import hashlib
import json
import logging
import os
from datetime import datetime

from .models import CrawledDocumentRecord, CrawlStatus

logger = logging.getLogger("ey_data_collector.storage")


# ────────────────────────────────────────────────────────────────────
# SHA256 去重追踪器 — 对齐现有 CrawledDocument content_hash 机制
# ────────────────────────────────────────────────────────────────────

class DedupTracker:
    """SHA256 精确去重追踪器 — 对齐 backend/apps/crawler/tasks.py 的 dedup 检测。

    维护内存中的已见内容哈希集合。若哈希重复出现，
    文档标记为 "duplicate_skipped"（与 CrawledDocument.STATUS_CHOICES 一致）。

    注意: 此为精确去重（SHA256），而非模糊去重（SimHash）。
    SimHash 包已在 pyproject.toml 中声明但未实现，独立脚本
    也暂使用 SHA256 精确匹配（对齐现有实现）。
    """

    def __init__(self):
        self._seen_hashes: set[str] = set()
        self._hash_to_source: dict[str, str] = {}  # hash → source_url（用于引用）

    def is_duplicate(self, content_hash: str) -> bool:
        """检查内容哈希是否已存在。"""
        return content_hash in self._seen_hashes

    def mark_seen(self, content_hash: str, source_url: str) -> None:
        """记录内容哈希为已见。"""
        self._seen_hashes.add(content_hash)
        self._hash_to_source[content_hash] = source_url

    def get_existing_source(self, content_hash: str) -> str:
        """获取已有相同哈希的源 URL（用于去重引用信息）。"""
        return self._hash_to_source.get(content_hash, "")

    def compute_hash(self, text: str) -> str:
        """计算文本的 SHA256 哈希 — 对齐 services.py 的 hashlib.sha256 用法。"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────────
# JSON Lines 写入器
# ────────────────────────────────────────────────────────────────────

class JSONLinesWriter:
    """JSON Lines (.jsonl) 输出写入器 — 每行一个 JSON 对象。

    格式说明: JSON Lines 是一种方便流式处理的文本格式，
    每行一个独立的 JSON 对象，便于逐行读取和解析。
    适合后续导入向量数据库或知识库索引。
    """

    def __init__(self, output_path: str):
        self.output_path = output_path
        self._count = 0
        self._file = None

    def open(self) -> None:
        """打开输出文件。"""
        os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
        self._file = open(self.output_path, "a", encoding="utf-8")
        logger.info("JSON Lines 输出文件已打开: %s", self.output_path)

    def write(self, record: CrawledDocumentRecord) -> None:
        """追加一条记录为 JSON 行。"""
        if self._file is None:
            self.open()

        # 使用 model_dump() 导出 Pydantic 模型为 dict
        line = record.model_dump_json()
        self._file.write(line + "\n")
        self._file.flush()
        self._count += 1

        logger.debug(
            "写入记录 #%d: %s — 状态=%s",
            self._count, record.source_url[:80], record.crawl_status,
        )

    def close(self) -> None:
        """关闭输出文件。"""
        if self._file is not None:
            self._file.close()
            logger.info("JSON Lines 输出完成: %s — %d 条记录", self.output_path, self._count)
            self._file = None

    @property
    def count(self) -> int:
        """已写入的记录数。"""
        return self._count


# ────────────────────────────────────────────────────────────────────
# CSV 写入器
# ────────────────────────────────────────────────────────────────────

class CSVWriter:
    """CSV 输出写入器 — 每行一条爬取记录。

    CSV 列名对齐 CrawledDocumentRecord 字段名，
    便于用 Excel / pandas 直接读取和分析。
    """

    # CSV 列名 — 对齐 CrawledDocumentRecord 字段
    FIELDNAMES = [
        "source_url", "source_name", "crawl_status", "title_extracted",
        "extracted_text", "content_hash", "content_type",
        "raw_content_size", "cleaned_content_size", "final_url",
        "redirect_count", "copyright_status", "internal_only",
        "robots_txt_allowed", "crawl_delay_seconds", "error_message",
        "tags", "category", "processing_time_ms", "crawled_at",
    ]

    def __init__(self, output_path: str):
        self.output_path = output_path
        self._count = 0
        self._file = None
        self._writer = None

    def open(self) -> None:
        """打开输出文件并写入 CSV 头。"""
        os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)

        # 检查文件是否已存在（追加模式 vs 新建模式）
        write_header = not os.path.exists(self.output_path) or os.path.getsize(self.output_path) == 0

        self._file = open(self.output_path, "a", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(
            self._file,
            fieldnames=self.FIELDNAMES,
            extrasaction="ignore",
        )

        if write_header:
            self._writer.writeheader()
            self._file.flush()

        logger.info("CSV 输出文件已打开: %s", self.output_path)

    def write(self, record: CrawledDocumentRecord) -> None:
        """追加一条记录为 CSV 行。"""
        if self._writer is None:
            self.open()

        # 将 Pydantic 模型转为 dict，处理特殊类型
        row = record.model_dump()
        # tags 列表转为逗号分隔字符串
        row["tags"] = ",".join(row.get("tags", []))
        # internal_only 布尔值转为字符串
        row["internal_only"] = str(row.get("internal_only", False))
        # robots_txt_allowed 布尔值转为字符串
        row["robots_txt_allowed"] = str(row.get("robots_txt_allowed", True))
        # content_type 枚举转为字符串
        row["content_type"] = str(row.get("content_type", "html"))
        # copyright_status 枚举转为字符串
        row["copyright_status"] = str(row.get("copyright_status", "unknown"))
        # crawl_status 枚举转为字符串
        row["crawl_status"] = str(row.get("crawl_status", "pending"))

        self._writer.writerow(row)
        self._file.flush()
        self._count += 1

        logger.debug(
            "写入记录 #%d: %s — 状态=%s",
            self._count, record.source_url[:80], record.crawl_status,
        )

    def close(self) -> None:
        """关闭输出文件。"""
        if self._file is not None:
            self._file.close()
            logger.info("CSV 输出完成: %s — %d 条记录", self.output_path, self._count)
            self._file = None

    @property
    def count(self) -> int:
        """已写入的记录数。"""
        return self._count


# ────────────────────────────────────────────────────────────────────
# 输出工厂函数
# ────────────────────────────────────────────────────────────────────

def create_writer(
    output_format: str,
    output_dir: str,
    output_name: str = "",
) -> JSONLinesWriter | CSVWriter:
    """根据配置创建对应的输出写入器。

    Args:
        output_format: "jsonl" 或 "csv"。
        output_dir: 输出目录路径。
        output_name: 输出文件名（空则自动生成）。

    Returns:
        JSONLinesWriter 或 CSVWriter 实例。
    """
    if not output_name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_name = f"crawl_results_{timestamp}"

    if output_format == "jsonl":
        path = os.path.join(output_dir, f"{output_name}.jsonl")
        return JSONLinesWriter(path)
    elif output_format == "csv":
        path = os.path.join(output_dir, f"{output_name}.csv")
        return CSVWriter(path)
    else:
        logger.warning("未支持的输出格式: %s，使用 JSON Lines", output_format)
        path = os.path.join(output_dir, f"{output_name}.jsonl")
        return JSONLinesWriter(path)
