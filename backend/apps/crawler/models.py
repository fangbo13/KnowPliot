# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Crawler models — V4.1 KB-V4.1-011~017 web crawling knowledge ingestion.

CrawledDocument: Metadata for web-crawled documents, linking to the existing
Document model via OneToOneField. Tracks source URL, crawl status, content
hash for dedup, copyright status, and robots.txt compliance.

CrawlTaskLog: Per-task tracking for rate limiting, redirect counting, and
processing time measurement.
"""

import uuid

from django.db import models
from django.conf import settings


class CrawledDocument(models.Model):
    """Metadata for web-crawled documents — V4.1 KB-V4.1-011~017.

    Each CrawledDocument links to a knowledge.Document via OneToOneField,
    keeping crawler-specific metadata separate from the document model.
    This separation allows clean takedown (withdraw) without affecting
    the Document model's core fields.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("fetching", "Fetching"),
        ("parsing", "Parsing"),
        ("cleaning", "Cleaning"),
        ("embedding", "Embedding"),
        ("active", "Active"),
        ("failed", "Failed"),
        ("withdrawn", "Withdrawn"),  # V4.1-017: copyright takedown
        ("duplicate_skipped", "Duplicate Skipped"),  # SimHash dedup
    ]

    COPYRIGHT_CHOICES = [
        ("unknown", "Unknown"),
        ("internal_only", "Internal Only"),
        ("public_domain", "Public Domain"),
        ("restricted", "Restricted"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Source tracking — V4.1-017: every crawled content must record source
    source_url = models.URLField(
        max_length=2048,
        help_text="The URL that was crawled. V4.1 KB-V4.1-012: URL length limit 2048.",
    )

    # Link to knowledge.Document — OneToOneField for clean separation
    document = models.OneToOneField(
        "knowledge.Document",
        on_delete=models.CASCADE,
        related_name="crawl_meta",
        null=True,
        blank=True,
        help_text="Linked knowledge.Document created from crawled content.",
    )

    # Crawl status lifecycle
    crawl_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Current status in the crawl lifecycle: pending→fetching→parsing→cleaning→embedding→active/failed/withdrawn.",
    )

    # Dedup — V4.1 SimHash/sha256 fingerprint
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="SHA256 hash of cleaned content for dedup detection.",
    )

    # Copyright — V4.1-017: copyright status tracking
    copyright_status = models.CharField(
        max_length=20,
        choices=COPYRIGHT_CHOICES,
        default="unknown",
        help_text="Copyright classification of the crawled content.",
    )
    copyright_disclaimer = models.TextField(
        blank=True,
        default="",
        help_text="Admin-added copyright note for this content.",
    )

    # Internal-only flag — content marked as "仅内部参考" won't appear in external检索
    internal_only = models.BooleanField(
        default=False,
        help_text="If True, this content is for internal reference only and excluded from external search.",
    )

    # robots.txt compliance — V4.1-014
    robots_txt_allowed = models.BooleanField(
        default=True,
        help_text="Whether robots.txt allowed crawling this URL.",
    )
    crawl_delay_seconds = models.IntegerField(
        default=0,
        help_text="Crawl-delay from robots.txt (seconds between requests to same domain).",
    )

    # Extracted content metadata
    title_extracted = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Title extracted by trafilatura from the crawled page.",
    )
    raw_content_size = models.IntegerField(
        default=0,
        help_text="Size of raw HTML content before cleaning (bytes).",
    )
    cleaned_content_size = models.IntegerField(
        default=0,
        help_text="Size of content after bleach cleaning (bytes).",
    )

    # Error tracking
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error message if crawl_status='failed'.",
    )

    # Audit trail
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_crawls",
        help_text="User who submitted this crawl request.",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    crawled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when content was actually fetched from the URL.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crawler_crawleddocument"
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["source_url"]),
            models.Index(fields=["content_hash"]),
            models.Index(fields=["crawl_status"]),
        ]

    def __str__(self):
        return f"CrawledDocument({self.source_url[:80]}, status={self.crawl_status})"


class CrawlTaskLog(models.Model):
    """Per-task tracking for crawler operations.

    Tracks domain-level rate limiting state, redirect handling, and
    processing time for each crawl task execution.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    crawled_document = models.OneToOneField(
        CrawledDocument,
        on_delete=models.CASCADE,
        related_name="task_log",
    )
    target_domain = models.CharField(
        max_length=255,
        help_text="Domain extracted from source_url for per-domain rate limiting.",
    )
    redirect_count = models.IntegerField(
        default=0,
        help_text="Number of redirects followed during fetching.",
    )
    final_url = models.URLField(
        max_length=2048,
        blank=True,
        default="",
        help_text="Final URL after all redirects.",
    )
    user_agent_used = models.CharField(
        max_length=200,
        help_text="User-Agent header sent during the crawl request.",
    )
    response_status_code = models.IntegerField(
        null=True,
        blank=True,
        help_text="HTTP status code of the final response.",
    )
    processing_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Total processing time in milliseconds (fetch + clean + embed).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "crawler_crawltasklog"
        ordering = ["-created_at"]

    def __str__(self):
        return f"CrawlTaskLog({self.target_domain}, status={self.response_status_code})"
