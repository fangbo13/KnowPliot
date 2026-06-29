# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge admin."""

from django.contrib import admin
from .models import DocumentCategory, Document, DocumentChunk, AnswerTemplate


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at"]
    prepopulated_fields = {"slug": ("name",)}


class DocumentChunkInline(admin.TabularInline):
    model = DocumentChunk
    extra = 0
    readonly_fields = ["content", "chunk_index", "page_number"]
    can_delete = False
    max_num = 5

    def content(self, obj):
        return obj.content[:100] + "..."


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "status", "version", "chunk_count", "created_at"]
    list_filter = ["status", "category", "file_type"]
    search_fields = ["title"]
    readonly_fields = ["id", "chunk_count", "processing_error", "created_at", "updated_at"]
    inlines = [DocumentChunkInline]


@admin.register(AnswerTemplate)
class AnswerTemplateAdmin(admin.ModelAdmin):
    list_display = ["question_pattern", "language", "is_active", "created_at"]
    list_filter = ["language", "is_active"]
    search_fields = ["question_pattern"]
