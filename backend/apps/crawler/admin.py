"""Crawler admin — V4.1 KB-V4.1-011~017."""

from django.contrib import admin
from .models import CrawledDocument, CrawlTaskLog


@admin.register(CrawledDocument)
class CrawledDocumentAdmin(admin.ModelAdmin):
    list_display = ["source_url", "crawl_status", "title_extracted", "submitted_by", "submitted_at"]
    list_filter = ["crawl_status", "copyright_status", "internal_only"]
    search_fields = ["source_url", "title_extracted"]
    readonly_fields = ["id", "content_hash", "submitted_at", "crawled_at", "created_at", "updated_at"]


@admin.register(CrawlTaskLog)
class CrawlTaskLogAdmin(admin.ModelAdmin):
    list_display = ["target_domain", "response_status_code", "processing_time_ms", "created_at"]
    list_filter = ["target_domain"]
    readonly_fields = ["id", "created_at"]
