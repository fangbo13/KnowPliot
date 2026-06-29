# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat admin — V4.1 SYS-V4.1-008: HTML escape Message.content to prevent stored XSS.

When Message.content contains malicious HTML (e.g., <img onerror=alert(1)>),
the Django admin list_display previously rendered it raw without escaping.
Now using format_html + escape to ensure safe display in admin panel.
"""

from django.contrib import admin
from django.utils.html import format_html, escape

from .models import ChatSession, Message, Citation, Feedback


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "title", "is_active", "created_at", "updated_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["title", "user__email"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    # V4.1 SYS-V4.1-008: content_short now uses HTML escaping
    list_display = ["id", "session", "role", "content_short", "model_used", "response_time_ms", "created_at"]
    list_filter = ["role", "model_used"]
    search_fields = ["content"]
    readonly_fields = ["id", "created_at"]

    def content_short(self, obj):
        """V4.1 SYS-V4.1-008: Escape HTML to prevent stored XSS in admin panel.

        Previously returned raw obj.content[:60] which could execute
        malicious HTML/JS in the admin interface. Now uses Django's
        escape() + format_html() to safely display text.
        """
        truncated = obj.content[:60]
        escaped = escape(truncated)
        if len(obj.content) > 60:
            return format_html("{}…", escaped)
        return format_html("{}", escaped)
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
