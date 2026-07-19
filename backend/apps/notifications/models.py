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
from django.utils import timezone


class Notification(models.Model):
    """A targeted, per-recipient in-app message."""

    TYPE_WELCOME = "welcome"
    TYPE_SPACE_INVITE = "space_invite"
    TYPE_ROLE_GRANTED = "role_granted"
    TYPE_DOCUMENT_REVIEW = "document_review"
    TYPE_SPACE_INVITATION = "space_invitation"
    TYPE_SPACE_ACCESS_REQUEST = "space_access_request"
    TYPE_ACCOUNT = "account"
    TYPE_SYSTEM = "system_broadcast"
    TYPE_CHOICES = [
        (TYPE_WELCOME, "Welcome"),
        (TYPE_SPACE_INVITE, "Space Invite"),
        (TYPE_ROLE_GRANTED, "Role Granted"),
        (TYPE_DOCUMENT_REVIEW, "Document Review"),
        (TYPE_SPACE_INVITATION, "Space Invitation"),
        (TYPE_SPACE_ACCESS_REQUEST, "Space Access Request"),
        (TYPE_ACCOUNT, "Account"),
        (TYPE_SYSTEM, "System"),
    ]

    LEVEL_CHOICES = [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]
    ACTION_NONE = "none"
    ACTION_AVAILABLE = "available"
    ACTION_ACTIONED = "actioned"
    ACTION_STALE = "stale"
    ACTION_KIND_RESOURCE_DELETED = "resource_deleted"
    ACTION_STATE_CHOICES = [
        (ACTION_NONE, "None"),
        (ACTION_AVAILABLE, "Available"),
        (ACTION_ACTIONED, "Actioned"),
        (ACTION_STALE, "Stale"),
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
    action_kind = models.CharField(max_length=40, blank=True, default="")
    resource_type = models.CharField(max_length=40, blank=True, default="")
    resource_uuid = models.UUIDField(null=True, blank=True)
    resource_version = models.PositiveBigIntegerField(null=True, blank=True)
    allowed_actions = models.JSONField(default=list, blank=True)
    action_state = models.CharField(
        max_length=12,
        choices=ACTION_STATE_CHOICES,
        default=ACTION_NONE,
    )
    deep_link = models.CharField(max_length=300, blank=True, default="")
    actioned_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(
                fields=["recipient", "type", "is_read", "created_at"],
                name="notif_rec_type_read_cr_idx",
            ),
            models.Index(
                fields=["recipient", "action_state", "created_at"],
                name="notif_rec_action_state_idx",
            ),
            models.Index(
                fields=["resource_type", "resource_uuid"],
                name="notif_resource_lookup_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    (
                        models.Q(action_kind="")
                        & models.Q(resource_type="")
                        & models.Q(resource_uuid__isnull=True)
                        & models.Q(action_state="none")
                        & models.Q(deep_link="")
                    )
                    | (
                        ~models.Q(action_kind__in=["", "resource_deleted"])
                        & ~models.Q(resource_type="")
                        & models.Q(resource_uuid__isnull=False)
                        & models.Q(action_state__in=["available", "actioned", "stale"])
                        & models.Q(deep_link__startswith="/")
                        & ~models.Q(deep_link__startswith="//")
                    )
                    | (
                        models.Q(action_kind="resource_deleted")
                        & ~models.Q(resource_type="")
                        & models.Q(resource_uuid__isnull=False)
                        & models.Q(action_state="stale")
                        & models.Q(allowed_actions=[])
                        & models.Q(deep_link="")
                    )
                ),
                name="notif_actionable_resource_shape",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(action_state="actioned")
                    | models.Q(actioned_at__isnull=False)
                ),
                name="notif_actioned_has_timestamp",
            ),
        ]

    def __str__(self):
        return f"[{self.type}] {self.title} -> {self.recipient_id}"


class ActionOutboxEvent(models.Model):
    """Durable external-delivery intent for an independent domain aggregate.

    The row deliberately stores only a stable recipient key and a safe payload.
    Raw invitation tokens, email addresses, and provider credentials belong in
    neither the outbox nor its retry diagnostics.
    """

    STATE_PENDING = "pending"
    STATE_DELIVERING = "delivering"
    STATE_DELIVERED = "delivered"
    STATE_FAILED = "failed"
    STATE_CHOICES = [
        (STATE_PENDING, "Pending"),
        (STATE_DELIVERING, "Delivering"),
        (STATE_DELIVERED, "Delivered"),
        (STATE_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_type = models.CharField(max_length=48)
    aggregate_uuid = models.UUIDField()
    transition = models.CharField(max_length=48)
    transition_version = models.PositiveBigIntegerField()
    recipient_key = models.CharField(max_length=96)
    payload = models.JSONField(default=dict)
    payload_digest = models.CharField(max_length=64)
    state = models.CharField(
        max_length=12,
        choices=STATE_CHOICES,
        default=STATE_PENDING,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_actionoutboxevent"
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "aggregate_type",
                    "aggregate_uuid",
                    "transition",
                    "transition_version",
                    "recipient_key",
                ],
                name="notif_outbox_transition_recipient_uniq",
            ),
            models.CheckConstraint(
                check=models.Q(
                    state__in=["pending", "delivering", "delivered", "failed"]
                ),
                name="notif_outbox_state_valid",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(state="delivered", delivered_at__isnull=False)
                    | (
                        ~models.Q(state="delivered")
                        & models.Q(delivered_at__isnull=True)
                    )
                ),
                name="notif_outbox_delivered_has_time",
            ),
        ]
        indexes = [
            models.Index(
                fields=["state", "next_attempt_at", "created_at"],
                name="notif_outbox_due_idx",
            ),
            models.Index(
                fields=["aggregate_type", "aggregate_uuid"],
                name="notif_outbox_aggregate_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.aggregate_type}:{self.aggregate_uuid}:"
            f"{self.transition}@{self.transition_version}"
        )


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
