# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Notification URLs — V7.0."""

from django.urls import path

from .views import (
    announcements,
    mark_all_read,
    mark_read,
    notifications_feed,
    unread_count,
)

urlpatterns = [
    path("", notifications_feed, name="notifications-feed"),
    path("unread-count/", unread_count, name="notifications-unread-count"),
    path("read-all/", mark_all_read, name="notifications-read-all"),
    path("<uuid:item_id>/read/", mark_read, name="notifications-read"),
    # Admin: publish / list announcements (version updates).
    path("announcements/", announcements, name="notifications-announcements"),
]
