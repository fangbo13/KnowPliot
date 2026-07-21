# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from django.contrib import admin

from .models import (
    ActionOutboxEvent,
    Announcement,
    AnnouncementDismissal,
    Notification,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "recipient", "level", "is_read", "created_at")
    list_filter = ("type", "level", "is_read")
    search_fields = ("title", "body", "recipient__email")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "audience_ref", "version", "is_active", "published_at")
    list_filter = ("audience", "is_active", "level")
    search_fields = ("title", "body", "version")


@admin.register(AnnouncementDismissal)
class AnnouncementDismissalAdmin(admin.ModelAdmin):
    list_display = ("user", "announcement", "dismissed_at")


@admin.register(ActionOutboxEvent)
class ActionOutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "aggregate_type",
        "transition",
        "transition_version",
        "state",
        "attempt_count",
        "created_at",
    )
    list_filter = ("aggregate_type", "transition", "state")
    readonly_fields = (
        "aggregate_type",
        "aggregate_uuid",
        "transition",
        "transition_version",
        "recipient_key",
        "payload",
        "payload_digest",
        "attempt_count",
        "created_at",
        "updated_at",
    )
