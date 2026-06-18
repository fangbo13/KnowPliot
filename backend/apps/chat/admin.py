"""Chat admin."""

from django.contrib import admin
from .models import ChatSession, Message, Citation, Feedback


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "title", "is_active", "created_at", "updated_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["title", "user__email"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["id", "session", "role", "content_short", "model_used", "response_time_ms", "created_at"]
    list_filter = ["role", "model_used"]
    search_fields = ["content"]
    readonly_fields = ["id", "created_at"]

    def content_short(self, obj):
        return obj.content[:60] + "..." if len(obj.content) > 60 else obj.content
    content_short.short_description = "Content"


@admin.register(Citation)
class CitationAdmin(admin.ModelAdmin):
    list_display = ["id", "message", "document", "page_number", "relevance_score"]
    list_filter = ["document"]
    readonly_fields = ["id"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ["id", "message", "rating", "reason", "created_at"]
    list_filter = ["rating", "reason"]
    readonly_fields = ["id", "created_at"]
