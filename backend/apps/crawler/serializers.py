# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Crawler serializers — V4.1 KB-V4.1-011~017."""

from rest_framework import serializers
from .models import CrawledDocument
from .validators import CrawlURLValidator


class CrawlRequestSerializer(serializers.Serializer):
    """Serializer for crawl URL submission requests."""

    url = serializers.URLField(
        max_length=2048,
        help_text="URL to crawl. Must be http or https protocol.",
    )
    category_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Optional category to assign to the crawled document.",
    )
    internal_only = serializers.BooleanField(
        default=False,
        help_text="Mark as internal reference only (excluded from external search).",
    )

    def validate_url(self, value):
        """Validate URL against SSRF rules — KB-V4.1-011/012/013."""
        validator = CrawlURLValidator()
        is_valid, reason = validator.validate(value)
        if not is_valid:
            raise serializers.ValidationError(reason)
        return value


class CrawledDocumentSerializer(serializers.ModelSerializer):
    """Serializer for CrawledDocument model — list and detail views."""

    submitted_by_email = serializers.CharField(
        source="submitted_by.email", read_only=True,
    )
    document_title = serializers.CharField(
        source="document.title", read_only=True, default="",
    )

    class Meta:
        model = CrawledDocument
        fields = [
            "id", "source_url", "crawl_status", "title_extracted",
            "content_hash", "copyright_status", "internal_only",
            "robots_txt_allowed", "raw_content_size", "cleaned_content_size",
            "error_message", "submitted_by_email", "document_title",
            "submitted_at", "crawled_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "crawl_status", "title_extracted", "content_hash",
            "copyright_status", "robots_txt_allowed", "raw_content_size",
            "cleaned_content_size", "error_message", "submitted_by_email",
            "document_title", "submitted_at", "crawled_at", "created_at",
            "updated_at",
        ]


class CrawledDocumentWithdrawSerializer(serializers.Serializer):
    """Serializer for withdraw (takedown) requests."""

    reason = serializers.CharField(
        required=False,
        max_length=500,
        help_text="Optional reason for withdrawal (copyright concern, etc.).",
    )
