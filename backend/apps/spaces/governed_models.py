# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Durable v3 governed-workflow persistence.

The legacy space, access-request, and invite models remain available for the
compatibility window.  These models are deliberately separate aggregates for
the v3 creation/deletion and operation-idempotency contracts.  They live in a
separate module so the large historical ``spaces.models`` module can evolve
without turning the governed envelope into a generic JSON command bus.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class WorkspaceCreationPolicy(models.Model):
    """Immutable, versioned policy that explicitly enables beta creation."""

    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_RETIRED = "retired"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_RETIRED, "Retired"),
    )
    AUDIENCE_REGISTERED_BETA = "registered_beta"
    AUDIENCE_AUTHORITATIVE = "authoritative_members"
    AUDIENCE_CHOICES = (
        (AUDIENCE_REGISTERED_BETA, "Registered beta"),
        (AUDIENCE_AUTHORITATIVE, "Authoritative members"),
    )
    ROUTE_PLATFORM = "platform"
    ROUTE_NEAREST_SCOPE = "nearest_scope"
    ROUTE_CHOICES = ((ROUTE_PLATFORM, "Platform"), (ROUTE_NEAREST_SCOPE, "Nearest scope"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_line = models.ForeignKey(
        "spaces.BusinessLine",
        on_delete=models.PROTECT,
        related_name="workspace_creation_policies",
    )
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    audience = models.CharField(
        max_length=32, choices=AUDIENCE_CHOICES, default=AUDIENCE_REGISTERED_BETA
    )
    review_route = models.CharField(
        max_length=20, choices=ROUTE_CHOICES, default=ROUTE_PLATFORM
    )
    effective_from = models.DateTimeField(null=True, blank=True)
    effective_until = models.DateTimeField(null=True, blank=True)
    reviewer_separation_required = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workspace_creation_policies_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "spaces_workspacecreationpolicy"
        ordering = ["business_line_id", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=("business_line", "revision"),
                name="spaces_creation_policy_business_revision",
            ),
            models.UniqueConstraint(
                fields=("business_line",),
                condition=Q(status="active"),
                name="spaces_one_active_creation_policy",
            ),
            models.CheckConstraint(
                check=~Q(effective_from__isnull=False, effective_until__isnull=False)
                | Q(effective_until__gte=models.F("effective_from")),
                name="spaces_creation_policy_effective_order",
            ),
        ]

    @property
    def is_effective(self) -> bool:
        now = timezone.now()
        return (
            self.status == self.STATUS_ACTIVE
            and (self.effective_from is None or self.effective_from <= now)
            and (self.effective_until is None or self.effective_until >= now)
        )


class WorkspaceLocatorReservation(models.Model):
    """Single namespace row for requested, live, and tombstoned locators."""

    STATE_REQUEST_RESERVED = "request_reserved"
    STATE_LIVE = "live"
    STATE_TOMBSTONED = "tombstoned"
    STATE_RELEASED = "released"
    STATE_CHOICES = (
        (STATE_REQUEST_RESERVED, "Request reserved"),
        (STATE_LIVE, "Live"),
        (STATE_TOMBSTONED, "Tombstoned"),
        (STATE_RELEASED, "Released"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "spaces.Organization", on_delete=models.PROTECT, related_name="locator_reservations"
    )
    normalized_code = models.CharField(max_length=120)
    normalized_locator = models.CharField(max_length=180, blank=True, default="")
    state = models.CharField(max_length=20, choices=STATE_CHOICES)
    live_space = models.OneToOneField(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="locator_reservation",
    )
    active_request = models.OneToOneField(
        "spaces.GovernedActionRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reserved_locator",
    )
    tombstone = models.OneToOneField(
        "spaces.WorkspaceTombstone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tombstone_reservation",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_workspacelocatorreservation"
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "normalized_code"),
                name="spaces_locator_org_code_unique",
            ),
            models.CheckConstraint(
                check=~Q(state="live") | Q(live_space__isnull=False),
                name="spaces_locator_live_has_space",
            ),
            models.CheckConstraint(
                check=(
                    Q(
                        state="request_reserved",
                        active_request__isnull=False,
                        live_space__isnull=True,
                        tombstone__isnull=True,
                    )
                    | Q(
                        state="live",
                        live_space__isnull=False,
                        active_request__isnull=True,
                        tombstone__isnull=True,
                    )
                    | Q(
                        state="tombstoned",
                        tombstone__isnull=False,
                        live_space__isnull=True,
                        active_request__isnull=True,
                    )
                    | Q(
                        state="released",
                        live_space__isnull=True,
                        active_request__isnull=True,
                        tombstone__isnull=True,
                    )
                ),
                name="spaces_locator_state_shape",
            ),
        ]
        indexes = [models.Index(fields=("organization", "state", "normalized_code"))]


class GovernedActionRequest(models.Model):
    """Typed common envelope for workspace creation and permanent deletion."""

    ACTION_WORKSPACE_CREATE = "workspace_create"
    ACTION_WORKSPACE_DELETE = "workspace_permanent_delete"
    ACTION_CHOICES = (
        (ACTION_WORKSPACE_CREATE, "Workspace create"),
        (ACTION_WORKSPACE_DELETE, "Workspace permanent delete"),
    )
    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_SCHEDULED = "scheduled"
    STATUS_EXECUTING = "executing"
    STATUS_FAILED = "failed"
    STATUS_INVALIDATED = "invalidated"
    STATUS_CHOICES = tuple(
        (value, value.replace("_", " ").title())
        for value in (
            STATUS_PENDING,
            STATUS_COMPLETED,
            STATUS_REJECTED,
            STATUS_CANCELLED,
            STATUS_EXPIRED,
            STATUS_SCHEDULED,
            STATUS_EXECUTING,
            STATUS_FAILED,
            STATUS_INVALIDATED,
        )
    )
    DELETE_LIVE_STATUSES = (STATUS_PENDING, STATUS_SCHEDULED, STATUS_EXECUTING, STATUS_FAILED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_type = models.CharField(max_length=40, choices=ACTION_CHOICES)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="governed_requests_submitted",
    )
    requester_uuid = models.UUIDField(db_index=True)
    scope_type = models.CharField(max_length=40, default="platform")
    scope_uuid = models.UUIDField(null=True, blank=True)
    organization = models.ForeignKey(
        "spaces.Organization",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="governed_requests",
    )
    business_line = models.ForeignKey(
        "spaces.BusinessLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="governed_requests",
    )
    target_space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="governed_requests",
    )
    target_space_uuid = models.UUIDField(null=True, blank=True, db_index=True)
    locator_reservation = models.ForeignKey(
        WorkspaceLocatorReservation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="governed_requests",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    idempotency_key = models.UUIDField()
    request_digest = models.CharField(max_length=64)
    request_version = models.PositiveBigIntegerField(default=1)
    impact_revision = models.PositiveBigIntegerField(default=0)
    impact_version = models.CharField(max_length=64, blank=True, default="")
    impact_expires_at = models.DateTimeField(null=True, blank=True)
    impact_snapshot = models.JSONField(default=dict, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="governed_requests_reviewed",
    )
    reviewer_uuid = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reason_code = models.CharField(max_length=64, blank=True, default="")
    reason_text = models.CharField(max_length=500, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    result_uuid = models.UUIDField(null=True, blank=True)
    failure_code = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_governedactionrequest"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("requester_uuid", "action_type", "idempotency_key"),
                name="spaces_governed_request_submit_key",
            ),
            models.UniqueConstraint(
                fields=("target_space",),
                # Nested ``Meta`` classes do not close over the containing
                # model class on Python. Keep the persisted enum literals
                # explicit here so model import/migration generation is stable.
                condition=Q(
                    action_type="workspace_permanent_delete",
                    status__in=("pending", "scheduled", "executing", "failed"),
                ),
                name="spaces_one_live_delete_request",
            ),
            models.CheckConstraint(
                check=Q(request_digest__regex=r"^[0-9a-f]{64}$"),
                name="spaces_governed_request_digest_shape",
            ),
            models.CheckConstraint(
                check=~Q(action_type="workspace_permanent_delete")
                | Q(target_space_uuid__isnull=False),
                name="spaces_delete_has_target_snapshot",
            ),
        ]
        indexes = [
            models.Index(fields=("action_type", "status", "created_at")),
            models.Index(fields=("requester_uuid", "status", "created_at")),
        ]


class WorkspaceCreateRequestDetail(models.Model):
    """Typed details for a workspace-create envelope."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.OneToOneField(
        GovernedActionRequest, on_delete=models.CASCADE, related_name="create_detail"
    )
    normalized_name = models.CharField(max_length=200)
    normalized_code = models.CharField(max_length=120)
    purpose = models.TextField(max_length=1000)
    requested_visibility = models.CharField(max_length=20, default="private")
    requested_join_policy = models.CharField(max_length=20, default="access_code")
    requested_join_code = models.CharField(max_length=24, null=True, blank=True)
    business_line = models.ForeignKey(
        "spaces.BusinessLine", on_delete=models.PROTECT, related_name="create_request_details"
    )
    work_group_id = models.UUIDField()
    office_location_ids = models.JSONField(default=list)
    template_version_id = models.UUIDField(null=True, blank=True)
    created_space_uuid = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_workspacecreaterequestdetail"
        constraints = [
            models.UniqueConstraint(
                fields=("request",), name="spaces_create_detail_request_unique"
            )
        ]


class WorkspaceDeletionRequestDetail(models.Model):
    """Typed details and consent evidence for permanent deletion."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.OneToOneField(
        GovernedActionRequest, on_delete=models.CASCADE, related_name="delete_detail"
    )
    locator = models.CharField(max_length=180)
    expected_lifecycle_version = models.PositiveBigIntegerField()
    expected_ownership_version = models.PositiveBigIntegerField()
    expected_dependency_version = models.PositiveBigIntegerField(default=1)
    archived_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    purge_not_before = models.DateTimeField(null=True, blank=True)
    retention_policy_version = models.PositiveBigIntegerField(default=1)
    storage_manifest_version = models.PositiveBigIntegerField(default=0)
    storage_manifest_digest = models.CharField(max_length=64, blank=True, default="")
    confirmation_digest = models.CharField(max_length=64, blank=True, default="")
    tombstone_uuid = models.UUIDField(null=True, blank=True)
    purge_job_uuid = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_workspacedeletionrequestdetail"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(storage_manifest_version=0, storage_manifest_digest="")
                    | Q(
                        storage_manifest_version__gte=1,
                        storage_manifest_digest__regex=r"^[0-9a-f]{64}$",
                    )
                ),
                name="spaces_delete_detail_manifest_shape",
            ),
        ]


class WriteIdempotencyRecord(models.Model):
    """Operation-level idempotency record shared by every v3 mutation."""

    DISPOSITION_IN_PROGRESS = "in_progress"
    DISPOSITION_COMPLETED = "completed"
    DISPOSITION_FAILED = "failed"
    DISPOSITION_CHOICES = (
        (DISPOSITION_IN_PROGRESS, "In progress"),
        (DISPOSITION_COMPLETED, "Completed"),
        (DISPOSITION_FAILED, "Failed"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_uuid = models.UUIDField()
    operation_code = models.CharField(max_length=80)
    key = models.UUIDField()
    request_digest = models.CharField(max_length=64)
    target_uuid = models.UUIDField(null=True, blank=True)
    request_uuid = models.UUIDField(null=True, blank=True)
    disposition = models.CharField(
        max_length=20, choices=DISPOSITION_CHOICES, default=DISPOSITION_IN_PROGRESS
    )
    result_reference = models.UUIDField(null=True, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_schema_version = models.PositiveSmallIntegerField(default=1)
    response_body = models.JSONField(default=dict, blank=True)
    failure_code = models.CharField(max_length=80, blank=True, default="")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_writeidempotencyrecord"
        constraints = [
            models.UniqueConstraint(
                fields=("actor_uuid", "operation_code", "key"),
                name="spaces_write_idempotency_actor_operation_key",
            ),
            models.CheckConstraint(
                check=Q(request_digest__regex=r"^[0-9a-f]{64}$"),
                name="spaces_write_idempotency_digest_shape",
            ),
        ]
        indexes = [models.Index(fields=("expires_at", "disposition"))]


class GovernedActionOutbox(models.Model):
    """Durable transition notification; delivery is retried after commit."""

    STATE_PENDING = "pending"
    STATE_DELIVERED = "delivered"
    STATE_FAILED = "failed"
    STATE_CHOICES = ((STATE_PENDING, "Pending"), (STATE_DELIVERED, "Delivered"), (STATE_FAILED, "Failed"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        GovernedActionRequest, on_delete=models.CASCADE, related_name="outbox_events"
    )
    event_type = models.CharField(max_length=80)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="governed_outbox_events",
    )
    payload_version = models.PositiveSmallIntegerField(default=1)
    transition_version = models.PositiveBigIntegerField()
    payload = models.JSONField(default=dict, blank=True)
    state = models.CharField(max_length=12, choices=STATE_CHOICES, default=STATE_PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "spaces_governedactionoutbox"
        constraints = [
            models.UniqueConstraint(
                fields=("request", "event_type", "recipient", "transition_version"),
                name="spaces_governed_outbox_transition_unique",
            )
        ]
        indexes = [models.Index(fields=("state", "next_attempt_at", "created_at"))]


class WorkspaceTombstone(models.Model):
    """Permanent namespace/evidence marker retained after space purge."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_space_uuid = models.UUIDField(unique=True)
    organization_uuid = models.UUIDField()
    request_uuid = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    locator_reservation = models.OneToOneField(
        WorkspaceLocatorReservation,
        on_delete=models.PROTECT,
        related_name="tombstone_marker",
    )
    locator_digest = models.CharField(max_length=64)
    normalized_locator = models.CharField(max_length=180)
    normalized_org_slug = models.CharField(max_length=120, blank=True, default="")
    normalized_space_code = models.CharField(max_length=120, blank=True, default="")
    request = models.OneToOneField(
        GovernedActionRequest,
        on_delete=models.PROTECT,
        related_name="tombstone_marker",
    )
    archived_at = models.DateTimeField()
    purged_at = models.DateTimeField(null=True, blank=True)
    final_manifest_digest = models.CharField(max_length=64, blank=True, default="")
    manifest_version = models.PositiveBigIntegerField(default=0)
    retention_flags = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_workspacetombstone"
        constraints = [
            models.CheckConstraint(
                check=Q(locator_digest__regex=r"^[0-9a-f]{64}$"),
                name="spaces_tombstone_locator_digest_shape",
            ),
            models.CheckConstraint(
                check=(
                    Q(manifest_version=0, final_manifest_digest="")
                    | Q(
                        manifest_version__gte=1,
                        final_manifest_digest__regex=r"^[0-9a-f]{64}$",
                    )
                ),
                name="spaces_tombstone_manifest_shape",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(normalized_locator="")
                    & ~Q(normalized_org_slug="")
                    & ~Q(normalized_space_code="")
                    & Q(request_uuid=models.F("request"))
                ),
                name="spaces_tombstone_identity_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.request_id and not self.request_uuid:
            self.request_uuid = self.request_id
        if self.normalized_locator and (
            not self.normalized_org_slug or not self.normalized_space_code
        ):
            parts = self.normalized_locator.split("/", 1)
            if len(parts) == 2:
                self.normalized_org_slug, self.normalized_space_code = parts
        super().save(*args, **kwargs)


class WorkspacePurgeJob(models.Model):
    """Fenced, resumable multi-store purge lineage."""

    STATE_QUEUED = "queued"
    STATE_RUNNING = "running"
    STATE_FAILED = "failed"
    STATE_COMPLETED = "completed"
    STATE_CHOICES = tuple((s, s.title()) for s in (STATE_QUEUED, STATE_RUNNING, STATE_FAILED, STATE_COMPLETED))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.OneToOneField(
        GovernedActionRequest, on_delete=models.PROTECT, related_name="purge_job"
    )
    state = models.CharField(max_length=12, choices=STATE_CHOICES, default=STATE_QUEUED)
    attempt = models.PositiveIntegerField(default=0)
    lease_generation = models.PositiveBigIntegerField(default=0)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    session_fence_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    request_version_snapshot = models.PositiveBigIntegerField(default=0)
    lifecycle_version_snapshot = models.PositiveBigIntegerField(default=0)
    ownership_version_snapshot = models.PositiveBigIntegerField(default=0)
    impact_version_snapshot = models.CharField(max_length=64, blank=True, default="")
    retention_not_before = models.DateTimeField(null=True, blank=True)
    manifest_version = models.PositiveBigIntegerField(default=0)
    manifest_digest = models.CharField(max_length=64, blank=True, default="")
    failure_code = models.CharField(max_length=80, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_workspacepurgejob"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(manifest_version=0, manifest_digest="")
                    | Q(
                        manifest_version__gte=1,
                        manifest_digest__regex=r"^[0-9a-f]{64}$",
                    )
                ),
                name="spaces_purge_job_manifest_shape",
            ),
        ]


class WorkspacePurgeCheckpoint(models.Model):
    """Per-store/batch acknowledgement used for safe resume and fencing."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_ACKED = "acked"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = tuple((s, s.title()) for s in (STATUS_PENDING, STATUS_RUNNING, STATUS_ACKED, STATUS_FAILED))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        WorkspacePurgeJob, on_delete=models.CASCADE, related_name="checkpoints"
    )
    STORE_CHOICES = (
        ("database", "Database"),
        ("blob", "Blob"),
        ("search", "Search"),
        ("vector", "Vector"),
        ("replay", "Replay"),
    )
    store_code = models.CharField(max_length=20, choices=STORE_CHOICES)
    batch_key = models.CharField(max_length=160)
    expected_digest = models.CharField(max_length=64, blank=True, default="")
    acknowledged_digest = models.CharField(max_length=64, blank=True, default="")
    item_count = models.PositiveBigIntegerField(default=0)
    byte_count = models.PositiveBigIntegerField(default=0)
    last_cursor = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempts = models.PositiveIntegerField(default=0)
    lease_generation = models.PositiveBigIntegerField(default=0)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_workspacepurgecheckpoint"
        constraints = [
            models.UniqueConstraint(
                fields=("job", "store_code", "batch_key"),
                name="spaces_purge_checkpoint_store_batch_unique",
            ),
            models.CheckConstraint(
                check=Q(store_code__in=["database", "blob", "search", "vector", "replay"]),
                name="spaces_purge_checkpoint_store_code",
            ),
        ]


class WorkspacePurgeDependency(models.Model):
    """Migration-owned registry entry for every workspace purge dependency."""

    DISPOSITION_ELIGIBLE = "eligible_content"
    DISPOSITION_RETAINED = "retained_evidence"
    DISPOSITION_CREDENTIAL = "credential"
    DISPOSITION_PERSONALIZATION = "personalization"
    DISPOSITION_BLOCKER = "blocker"
    DISPOSITION_CHOICES = (
        (DISPOSITION_ELIGIBLE, "Eligible content"),
        (DISPOSITION_RETAINED, "Retained evidence"),
        (DISPOSITION_CREDENTIAL, "Credential"),
        (DISPOSITION_PERSONALIZATION, "Personalization"),
        (DISPOSITION_BLOCKER, "Blocker"),
    )
    STATE_PENDING = "pending"
    STATE_READY = "ready"
    STATE_CHOICES = ((STATE_PENDING, "Pending"), (STATE_READY, "Ready"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_label = models.CharField(max_length=160)
    space_field = models.CharField(max_length=80, blank=True, default="")
    disposition = models.CharField(max_length=24, choices=DISPOSITION_CHOICES)
    blocker_code = models.CharField(max_length=64, blank=True, default="")
    lock_order = models.PositiveSmallIntegerField()
    purge_order = models.PositiveSmallIntegerField()
    snapshot_fields = models.JSONField(default=list, blank=True)
    scrub_fields = models.JSONField(default=list, blank=True)
    migration_owner = models.CharField(max_length=160)
    registration_state = models.CharField(
        max_length=12,
        choices=STATE_CHOICES,
        default=STATE_PENDING,
    )
    schema_revision = models.PositiveBigIntegerField(default=1)
    required = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_workspacepurgedependency"
        ordering = ["purge_order", "model_label", "space_field"]
        constraints = [
            models.UniqueConstraint(
                fields=("model_label", "space_field"),
                name="spaces_purge_dependency_model_field",
            ),
            models.CheckConstraint(
                check=Q(lock_order__gte=1) & Q(purge_order__gte=1),
                name="spaces_purge_dependency_order_positive",
            ),
        ]


class WorkspaceRetentionHold(models.Model):
    """Governed legal/business retention evidence that survives workspace purge."""

    TYPE_LEGAL = "legal"
    TYPE_AUDIT = "audit"
    TYPE_INVESTIGATION = "investigation"
    TYPE_BACKUP = "backup"
    TYPE_BUSINESS_RECORD = "business_record"
    TYPE_CHOICES = (
        (TYPE_LEGAL, "Legal"),
        (TYPE_AUDIT, "Audit"),
        (TYPE_INVESTIGATION, "Investigation"),
        (TYPE_BACKUP, "Backup"),
        (TYPE_BUSINESS_RECORD, "Business record"),
    )
    STATUS_ACTIVE = "active"
    STATUS_RELEASED = "released"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_RELEASED, "Released"),
        (STATUS_EXPIRED, "Expired"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retention_holds",
    )
    space_uuid = models.UUIDField()
    organization_uuid = models.UUIDField()
    locator_digest = models.CharField(max_length=64)
    tombstone = models.ForeignKey(
        WorkspaceTombstone,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retention_holds",
    )
    hold_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    reason_code = models.CharField(max_length=64)
    policy_version = models.PositiveBigIntegerField(default=1)
    version = models.PositiveBigIntegerField(default=1)
    effective_from = models.DateTimeField(default=timezone.now)
    release_not_before = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workspace_retention_holds_created",
    )
    created_by_uuid = models.UUIDField(null=True, blank=True, editable=False)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workspace_retention_holds_released",
    )
    released_by_uuid = models.UUIDField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_workspaceretentionhold"
        constraints = [
            models.UniqueConstraint(
                fields=("space", "hold_type"),
                condition=Q(status="active"),
                name="spaces_one_active_retention_hold",
            ),
            models.CheckConstraint(
                check=Q(locator_digest__regex=r"^[0-9a-f]{64}$"),
                name="spaces_retention_hold_locator_shape",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(status="active")
                    | (Q(space__isnull=False) & Q(released_at__isnull=True))
                ),
                name="spaces_active_hold_live_space",
            ),
            models.CheckConstraint(
                check=~Q(status="released") | Q(released_at__isnull=False),
                name="spaces_released_hold_timestamp",
            ),
        ]
        indexes = [
            models.Index(
                fields=("space_uuid", "status", "hold_type"),
                name="spaces_hold_space_status",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.created_by_id and not self.created_by_uuid:
            self.created_by_uuid = self.created_by_id
        if self.released_by_id and not self.released_by_uuid:
            self.released_by_uuid = self.released_by_id
        super().save(*args, **kwargs)


# Export the classes through ``apps.spaces.models`` once this module is
# imported by the app's models module.  Keeping ``__all__`` explicit also makes
# static audits and migration reviews straightforward.
__all__ = [
    "WorkspaceCreationPolicy",
    "WorkspaceLocatorReservation",
    "GovernedActionRequest",
    "WorkspaceCreateRequestDetail",
    "WorkspaceDeletionRequestDetail",
    "WriteIdempotencyRecord",
    "GovernedActionOutbox",
    "WorkspaceTombstone",
    "WorkspacePurgeJob",
    "WorkspacePurgeCheckpoint",
    "WorkspacePurgeDependency",
    "WorkspaceRetentionHold",
]
