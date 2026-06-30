# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Notification models — V7.0 (docs/KnowPilot_V7_Identity_RBAC_Spec.md §6/§9).

Two delivery mechanisms stack into one user-facing feed:

1. **Notification** — *targeted*, one row per recipient. Used for space
   invitations, role grants, document-review requests, account events.

2. **Announcement** — *broadcast*, a single row addressed to an audience
   (all / org / business_line / role). Used for version-update messages.
   Read-state is tracked sparsely via ``AnnouncementDismissal`` so we never
   fan a broadcast out to thousands of per-user rows.

The merged feed (targeted + matching announcements) and unread counting live in
``apps.notifications.services``.
"""

import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    """A targeted, per-recipient in-app message."""

    TYPE_WELCOME = "welcome"
    TYPE_SPACE_INVITE = "space_invite"
    TYPE_ROLE_GRANTED = "role_granted"
    TYPE_DOCUMENT_REVIEW = "document_review"
    TYPE_ACCOUNT = "account"
    TYPE_SYSTEM = "system_broadcast"
    TYPE_CHOICES = [
        (TYPE_WELCOME, "Welcome"),
        (TYPE_SPACE_INVITE, "Space Invite"),
        (TYPE_ROLE_GRANTED, "Role Granted"),
        (TYPE_DOCUMENT_REVIEW, "Document Review"),
        (TYPE_ACCOUNT, "Account"),
        (TYPE_SYSTEM, "System"),
    ]

    LEVEL_CHOICES = [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_ACCOUNT)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default="info")
    # Optional in-app deep link, e.g. "/spaces/manage" or "/chat".
    link = models.CharField(max_length=300, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return f"[{self.type}] {self.title} -> {self.recipient_id}"


class Announcement(models.Model):
    """A broadcast message addressed to an audience (e.g. a version update)."""

    AUDIENCE_ALL = "all"
    AUDIENCE_ORG = "org"
    AUDIENCE_BUSINESS_LINE = "business_line"
    AUDIENCE_ROLE = "role"
    AUDIENCE_CHOICES = [
        (AUDIENCE_ALL, "Everyone"),
        (AUDIENCE_ORG, "Organization"),
        (AUDIENCE_BUSINESS_LINE, "Business Line"),
        (AUDIENCE_ROLE, "Platform Role"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    level = models.CharField(max_length=10, choices=Notification.LEVEL_CHOICES, default="info")
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_ALL)
    # For ``org`` -> Organization.slug; ``business_line`` -> BusinessLine.code;
    # ``role`` -> one of super_admin/org_admin/business_admin/employee. Null for ``all``.
    audience_ref = models.CharField(max_length=120, blank=True, default="")
    version = models.CharField(max_length=20, blank=True, default="", help_text="e.g. 'V7.0'")
    is_active = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="announcements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_announcement"
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return f"Announcement[{self.audience}] {self.title}"


class AnnouncementDismissal(models.Model):
    """Sparse read-state: a user has dismissed (read) a broadcast."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcement_dismissals",
    )
    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="dismissals"
    )
    dismissed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_announcementdismissal"
        unique_together = [("user", "announcement")]

    def __str__(self):
        return f"{self.user_id} dismissed {self.announcement_id}"
