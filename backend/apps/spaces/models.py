# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Multi-space platform models — V6.0.

KnowPilot moves from a single global knowledge base to a multi-tenant,
multi-space architecture (see SPEC.MD §M2 / §5). One platform carries many
isolated knowledge spaces:

    Organization -> BusinessLine -> KnowledgeSpace -> (documents, sessions, ...)

Every space-scoped business object (Document, DocumentChunk, ChatSession,
Message, Citation, Feedback) carries a ``space`` FK so data is isolated per
space. Membership + invite codes control who can enter a space; the access
code is an *entry* mechanism only — it never bypasses RBAC (SPEC.MD §3.3).
"""

import hashlib
import unicodedata
import uuid
from datetime import timedelta

# NOTE: aliased because this module declares a ``settings`` JSONField below; the
# bare name ``settings`` would otherwise shadow the Django settings module for
# FK declarations that follow it in the class body.
from django.conf import settings as django_settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


SPACE_CLASSIFICATION_COMPLETE = "complete"
SPACE_CLASSIFICATION_LEGACY = "legacy_unclassified"
SPACE_CLASSIFICATION_EXEMPT = "exempt"


def locator_digest(value):
    canonical = unicodedata.normalize("NFC", value or "")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_access_request_expiry():
    return timezone.now() + timedelta(days=14)


class Organization(models.Model):
    """Top-level tenant (e.g. EY internal demo, a client tenant)."""

    STATUS_CHOICES = [("active", "Active"), ("archived", "Archived")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_organization"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BusinessLine(models.Model):
    """A business line within an organization (Audit, Tax, Consulting, ...)."""

    STATUS_CHOICES = [("active", "Active"), ("archived", "Archived")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="business_lines"
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_businessline"
        ordering = ["name"]
        unique_together = [("organization", "code")]

    def __str__(self):
        return f"{self.name} ({self.code})"


class WorkGroup(models.Model):
    """Controlled classification beneath one :class:`BusinessLine`.

    Work groups are taxonomy only.  They never grant membership or
    capabilities; the organization/business-line/workspace authorization
    boundary remains unchanged.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_line = models.ForeignKey(
        BusinessLine,
        on_delete=models.PROTECT,
        related_name="work_groups",
    )
    normalized_code = models.CharField(max_length=120)
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_workgroup"
        ordering = ["sort_order", "display_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_line", "normalized_code"],
                name="spaces_wg_bl_normalized_code",
            ),
            models.CheckConstraint(
                check=~Q(normalized_code=""),
                name="spaces_wg_code_nonempty",
            ),
            models.CheckConstraint(
                check=~Q(display_name=""),
                name="spaces_wg_name_nonempty",
            ),
        ]
        indexes = [
            models.Index(
                fields=["business_line", "active", "sort_order"],
                name="spaces_wg_bl_active_order",
            ),
        ]

    def __str__(self):
        return self.display_name


class OfficeLocation(models.Model):
    """Controlled organization-owned office/location classification."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="office_locations",
    )
    normalized_code = models.CharField(max_length=120)
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    version = models.PositiveBigIntegerField(default=1)
    locale = models.CharField(max_length=32, blank=True, default="")
    time_zone = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_officelocation"
        ordering = ["sort_order", "display_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "normalized_code"],
                name="spaces_office_org_normalized_code",
            ),
            models.CheckConstraint(
                check=~Q(normalized_code=""),
                name="spaces_office_code_nonempty",
            ),
            models.CheckConstraint(
                check=~Q(display_name=""),
                name="spaces_office_name_nonempty",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "active", "sort_order"],
                name="spaces_office_org_active_order",
            ),
        ]

    def __str__(self):
        return self.display_name


class KnowledgeSpace(models.Model):
    """An isolated knowledge space — the core unit of multi-tenancy.

    All documents, chunks, chat sessions, messages, citations, and feedback
    belong to exactly one space. Users only see spaces they have membership in
    (or that are public demo / org-shared), enforced server-side.
    """

    VISIBILITY_CHOICES = [
        ("private", "Private"),
        ("business_line", "Business Line Internal"),
        ("organization", "Organization Shared"),
        ("public_demo", "Public Demo"),
    ]
    STATUS_CHOICES = [("active", "Active"), ("archived", "Archived")]
    PROVISIONING_STATUS_CHOICES = [
        ("provisioning", "Provisioning"),
        ("ready", "Ready"),
        ("failed", "Failed"),
    ]
    CLASSIFICATION_COMPLETE = SPACE_CLASSIFICATION_COMPLETE
    CLASSIFICATION_LEGACY = SPACE_CLASSIFICATION_LEGACY
    CLASSIFICATION_EXEMPT = SPACE_CLASSIFICATION_EXEMPT
    CLASSIFICATION_STATE_CHOICES = [
        (SPACE_CLASSIFICATION_COMPLETE, "Complete"),
        (SPACE_CLASSIFICATION_LEGACY, "Legacy Unclassified"),
        (SPACE_CLASSIFICATION_EXEMPT, "Exempt"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="spaces"
    )
    business_line = models.ForeignKey(
        BusinessLine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="spaces",
    )
    work_group = models.ForeignKey(
        WorkGroup,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="spaces",
    )
    name = models.CharField(max_length=200)
    # Global, URL-safe short code for routing / deep links / access-code display.
    code = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=50, blank=True, default="")
    language = models.CharField(max_length=8, default="en")
    # Post-V3 Part 4: AI reply-language fallback (auto/zh/en). Does NOT drive
    # KB content language; used only when query-language detection is
    # inconclusive and the user has no explicit language_preference.
    default_language = models.CharField(
        max_length=8,
        choices=[("auto", "Auto-detect"), ("zh", "Chinese"), ("en", "English")],
        default="auto",
    )
    visibility = models.CharField(
        max_length=20, choices=VISIBILITY_CHOICES, default="private"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    provisioning_status = models.CharField(
        max_length=20,
        choices=PROVISIONING_STATUS_CHOICES,
        default="ready",
    )
    classification_state = models.CharField(
        max_length=24,
        choices=CLASSIFICATION_STATE_CHOICES,
        default=SPACE_CLASSIFICATION_LEGACY,
    )
    office_locations = models.ManyToManyField(
        OfficeLocation,
        through="KnowledgeSpaceOfficeLocation",
        related_name="spaces",
        blank=True,
    )
    settings = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_spaces",
    )
    # Canonical ownership authority. New writes must use
    # ``create_space_with_owner`` and populate this field.
    owner = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_spaces",
    )
    ownership_version = models.PositiveIntegerField(default=1)
    lifecycle_version = models.PositiveBigIntegerField(default=1)
    dependency_version = models.PositiveBigIntegerField(default=1)
    archived_at = models.DateTimeField(null=True, blank=True)
    retention_policy_version = models.PositiveBigIntegerField(default=1)
    retention_until = models.DateTimeField(null=True, blank=True)
    storage_manifest_version = models.PositiveBigIntegerField(default=0)
    storage_manifest_digest = models.CharField(max_length=64, blank=True, default="")
    storage_manifest_generated_at = models.DateTimeField(null=True, blank=True)
    purge_fence_generation = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_knowledgespace"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=Q(classification_state__in=[
                    SPACE_CLASSIFICATION_COMPLETE,
                    SPACE_CLASSIFICATION_LEGACY,
                    SPACE_CLASSIFICATION_EXEMPT,
                ]),
                name="spaces_classification_state_valid",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(classification_state=SPACE_CLASSIFICATION_COMPLETE)
                    | (Q(business_line__isnull=False) & Q(work_group__isnull=False))
                ),
                name="spaces_complete_classification_fields",
            ),
            models.CheckConstraint(
                check=(
                    Q(storage_manifest_version=0, storage_manifest_digest="")
                    | Q(
                        storage_manifest_version__gte=1,
                        storage_manifest_digest__regex=r"^[0-9a-f]{64}$",
                        storage_manifest_generated_at__isnull=False,
                    )
                ),
                name="spaces_storage_manifest_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "classification_state"],
                name="spaces_org_class_state",
            ),
            models.Index(
                fields=["business_line", "classification_state"],
                name="spaces_bl_class_state",
            ),
            models.Index(fields=["work_group"], name="spaces_work_group_idx"),
        ]

    def __str__(self):
        return f"{self.name} [{self.code}]"

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class KnowledgeSpaceOfficeLocation(models.Model):
    """Explicit workspace/location through row with stable uniqueness."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        KnowledgeSpace,
        on_delete=models.CASCADE,
        related_name="office_location_links",
    )
    office_location = models.ForeignKey(
        OfficeLocation,
        on_delete=models.PROTECT,
        related_name="space_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_knowledgespace_office_locations"
        constraints = [
            models.UniqueConstraint(
                fields=["space", "office_location"],
                name="spaces_space_office_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["office_location", "space"],
                name="spaces_office_space_idx",
            ),
        ]


# Short compatibility alias for callers that refer to the relation as a
# generic space/location through model.
SpaceOfficeLocation = KnowledgeSpaceOfficeLocation


class WorkspaceUsageDaily(models.Model):
    """Privacy-minimal per-user/per-space UTC-day interaction bucket."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_usage_daily",
    )
    space = models.ForeignKey(
        KnowledgeSpace,
        on_delete=models.CASCADE,
        related_name="usage_daily",
    )
    date = models.DateField()
    interaction_count = models.PositiveIntegerField(default=0)
    last_interacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "spaces_workspaceusagedaily"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "space", "date"],
                name="spaces_usage_daily_user_space_date",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "date"], name="spaces_usage_daily_user_date"),
            models.Index(fields=["space", "date"], name="spaces_usage_daily_space_date"),
        ]


class WorkspaceUsageSummary(models.Model):
    """Idempotently recomputed 30-day usage summary."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_usage_summaries",
    )
    space = models.ForeignKey(
        KnowledgeSpace,
        on_delete=models.CASCADE,
        related_name="usage_summaries",
    )
    interaction_count_30d = models.PositiveIntegerField(default=0)
    last_interacted_at = models.DateTimeField(null=True, blank=True)
    computed_through = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "spaces_workspaceusagesummary"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "space"],
                name="spaces_usage_summary_user_space",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "interaction_count_30d", "last_interacted_at"],
                name="spaces_usage_summary_rank",
            ),
            models.Index(fields=["space"], name="spaces_usage_summary_space"),
        ]


class SpaceMembership(models.Model):
    """Maps a user to a space with a space-scoped role.

    Space-level roles (SPEC.MD §M8). Platform-level roles (Super Admin / Org
    Admin) come from the global RBAC layer (``apps.rbac``) and are resolved in
    ``apps.spaces.permissions``, not stored here.
    """

    ROLE_OWNER = "owner"
    ROLE_KNOWLEDGE_ADMIN = "knowledge_admin"
    ROLE_REVIEWER = "reviewer"
    ROLE_MEMBER = "member"
    ROLE_GUEST = "guest"
    ROLE_CHOICES = [
        (ROLE_OWNER, "Space Owner"),
        (ROLE_KNOWLEDGE_ADMIN, "Knowledge Admin"),
        (ROLE_REVIEWER, "Reviewer"),
        (ROLE_MEMBER, "Member"),
        (ROLE_GUEST, "Guest"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("pending", "Pending"),
        ("revoked", "Revoked"),
    ]
    SOURCE_LEGACY = "legacy"
    SOURCE_MANUAL = "manual"
    SOURCE_ACCESS_REQUEST = "access_request"
    SOURCE_INVITATION = "invitation"
    SOURCE_OWNERSHIP = "ownership"
    SOURCE_CHOICES = [
        (SOURCE_LEGACY, "Legacy"),
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_ACCESS_REQUEST, "Access Request"),
        (SOURCE_INVITATION, "Invitation"),
        (SOURCE_OWNERSHIP, "Ownership"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        KnowledgeSpace, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="space_memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    membership_version = models.PositiveBigIntegerField(default=1)
    source_kind = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_LEGACY,
    )
    invited_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="space_invitations_sent",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_spacemembership"
        unique_together = [("space", "user")]
        ordering = ["-last_accessed_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["space"],
                condition=Q(role="owner", status="active"),
                name="spaces_one_active_owner_membership",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(role="owner")
                    | (Q(status="active") & Q(expires_at__isnull=True))
                ),
                name="spaces_owner_membership_effective",
            ),
            models.CheckConstraint(
                check=~Q(role="owner") | Q(invited_by__isnull=True),
                name="spaces_owner_membership_not_invited",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.space} ({self.role})"

    @property
    def is_effective(self) -> bool:
        """Active and not expired."""
        if self.status != "active":
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class OwnershipTransfer(models.Model):
    """Durable, idempotent ownership-transfer state machine record."""

    MODE_VOLUNTARY = "voluntary"
    MODE_FORCED = "forced"
    MODE_OFFBOARDING = "offboarding"
    MODE_CHOICES = [
        (MODE_VOLUNTARY, "Voluntary"),
        (MODE_FORCED, "Forced"),
        (MODE_OFFBOARDING, "Offboarding"),
    ]
    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_DECLINED = "declined"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_INVALIDATED = "invalidated"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_INVALIDATED, "Invalidated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        KnowledgeSpace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ownership_transfers",
    )
    space_uuid = models.UUIDField(null=True, blank=True, editable=False)
    organization_uuid = models.UUIDField(null=True, blank=True, editable=False)
    locator_digest = models.CharField(max_length=64, blank=True, default="", editable=False)
    tombstone = models.ForeignKey(
        "spaces.WorkspaceTombstone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ownership_transfers",
    )
    from_owner = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ownership_transfers_from"
    )
    to_owner = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ownership_transfers_to"
    )
    requested_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ownership_transfers_requested"
    )
    accepted_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ownership_transfers_accepted",
    )
    mode = models.CharField(max_length=16, choices=MODE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    expected_ownership_version = models.PositiveIntegerField()
    reason_code = models.CharField(max_length=64)
    reason_note = models.CharField(max_length=500, blank=True, default="")
    idempotency_key = models.UUIDField()
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "spaces_ownershiptransfer"
        constraints = [
            models.UniqueConstraint(
                fields=["space"], condition=Q(status="pending"), name="spaces_one_pending_owner_transfer"
            ),
            models.UniqueConstraint(
                fields=["requested_by", "idempotency_key"], name="spaces_owner_transfer_request_key"
            ),
            models.CheckConstraint(check=~Q(from_owner=models.F("to_owner")), name="spaces_owner_transfer_distinct"),
            models.CheckConstraint(
                check=~Q(requested_by=models.F("to_owner")),
                name="spaces_owner_transfer_actor_target",
            ),
            models.CheckConstraint(
                check=~Q(status="completed") | Q(completed_at__isnull=False),
                name="spaces_owner_transfer_completed_timestamp",
            ),
            models.CheckConstraint(
                check=(
                    Q(
                        space_uuid__isnull=False,
                        organization_uuid__isnull=False,
                        locator_digest__regex=r"^[0-9a-f]{64}$",
                    )
                ),
                name="spaces_owner_transfer_space_evidence",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.space_id:
            if not self.space_uuid:
                self.space_uuid = self.space_id
            if not self.organization_uuid:
                self.organization_uuid = self.space.organization_id
            if not self.locator_digest:
                locator = getattr(self.space, "locator_reservation", None)
                if locator is not None:
                    self.locator_digest = locator_digest(
                        locator.normalized_locator
                    )
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {
                    "space_uuid",
                    "organization_uuid",
                    "locator_digest",
                }
        super().save(*args, **kwargs)


class OrganizationMembership(models.Model):
    """Org-/business-line-level admin assignment (above space membership).

    - ``org_admin`` governs an entire organization (all its spaces).
    - ``business_admin`` governs a single business line (all spaces in it).

    These grant full access within their scope (SPEC.MD §M8). Platform Super
    Admin (Django superuser / global 'admin' role) sits above both.
    """

    ROLE_ORG_ADMIN = "org_admin"
    ROLE_BUSINESS_ADMIN = "business_admin"
    ROLE_CHOICES = [
        (ROLE_ORG_ADMIN, "Organization Admin"),
        (ROLE_BUSINESS_ADMIN, "Business Admin"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="admin_memberships"
    )
    business_line = models.ForeignKey(
        BusinessLine,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="admin_memberships",
        help_text="Required for business_admin; ignored for org_admin.",
    )
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_organizationmembership"
        unique_together = [("user", "organization", "business_line", "role")]

    def __str__(self):
        scope = self.business_line.code if self.business_line else self.organization.slug
        return f"{self.user} = {self.role} @ {scope}"

    @property
    def is_effective(self) -> bool:
        """An explicit governance grant must be active and unexpired."""

        if not self.is_active:
            return False
        return not self.expires_at or self.expires_at >= timezone.now()


class SpaceAccessCode(models.Model):
    """Hash-only locator credential that creates an owner-reviewed request."""

    STATUS_ACTIVE = "active"
    STATUS_REVOKED = "revoked"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_REVOKED, "Revoked"),
        (STATUS_EXPIRED, "Expired"),
    ]
    ROLE_CHOICES = [
        (SpaceMembership.ROLE_MEMBER, "Member"),
        (SpaceMembership.ROLE_GUEST, "Guest"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        KnowledgeSpace,
        on_delete=models.CASCADE,
        related_name="access_codes_v2",
    )
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="space_access_codes_created",
    )
    secret_hash = models.CharField(max_length=64, unique=True)
    pepper_version = models.PositiveSmallIntegerField(default=1)
    display_prefix = models.CharField(max_length=12)
    role_ceiling = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=SpaceMembership.ROLE_MEMBER,
    )
    max_uses = models.PositiveIntegerField()
    used_count = models.PositiveIntegerField(default=0)
    max_pending = models.PositiveIntegerField()
    pending_count = models.PositiveIntegerField(default=0)
    policy_version = models.PositiveBigIntegerField(default=1)
    version = models.PositiveBigIntegerField(default=1)
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_spaceaccesscode"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(secret_hash__regex=r"^[0-9a-f]{64}$"),
                name="spaces_access_code_hash_shape",
            ),
            models.CheckConstraint(
                check=Q(role_ceiling__in=["member", "guest"]),
                name="spaces_access_code_role_ceiling",
            ),
            models.CheckConstraint(
                check=Q(pepper_version__gte=1) & ~Q(display_prefix=""),
                name="spaces_access_code_key_evidence",
            ),
            models.CheckConstraint(
                check=Q(max_uses__gte=1) & Q(used_count__lte=models.F("max_uses")),
                name="spaces_access_code_use_ceiling",
            ),
            models.CheckConstraint(
                check=Q(max_pending__gte=1)
                & Q(pending_count__lte=models.F("max_pending")),
                name="spaces_access_code_pending_ceiling",
            ),
        ]
        indexes = [
            models.Index(
                fields=["space", "status", "expires_at"],
                name="spaces_access_code_state",
            ),
        ]


class SpaceInvitation(models.Model):
    """Recipient-bound, hash-only, single-use non-owner membership offer."""

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_EXPIRED = "expired"
    STATUS_REVOKED = "revoked"
    STATUS_INVALIDATED = "invalidated"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_REVOKED, "Revoked"),
        (STATUS_INVALIDATED, "Invalidated"),
    ]
    ROLE_CHOICES = [
        (SpaceMembership.ROLE_KNOWLEDGE_ADMIN, "Knowledge Admin"),
        (SpaceMembership.ROLE_REVIEWER, "Reviewer"),
        (SpaceMembership.ROLE_MEMBER, "Member"),
        (SpaceMembership.ROLE_GUEST, "Guest"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        KnowledgeSpace,
        on_delete=models.CASCADE,
        related_name="targeted_invitations",
    )
    inviter = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="targeted_space_invitations_sent",
    )
    inviter_uuid = models.UUIDField()
    target_user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="targeted_space_invitations",
    )
    target_user_uuid = models.UUIDField(null=True, blank=True)
    target_email_hmac = models.CharField(max_length=64, blank=True, default="")
    encrypted_delivery_address = models.TextField(blank=True, default="")
    target_key = models.CharField(max_length=140)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    token_hash = models.CharField(max_length=64, unique=True)
    token_pepper_version = models.PositiveSmallIntegerField(default=1)
    token_prefix = models.CharField(max_length=12)
    policy_version = models.PositiveBigIntegerField(default=1)
    ownership_version = models.PositiveBigIntegerField()
    version = models.PositiveBigIntegerField(default=1)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    expires_at = models.DateTimeField()
    responded_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="targeted_space_invitations_responded",
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    resulting_membership_uuid = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_spaceinvitation"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["space", "target_key"],
                condition=Q(status="pending"),
                name="spaces_one_pending_target_invite",
            ),
            models.CheckConstraint(
                check=Q(token_hash__regex=r"^[0-9a-f]{64}$"),
                name="spaces_invitation_token_hash_shape",
            ),
            models.CheckConstraint(
                check=Q(token_pepper_version__gte=1) & ~Q(token_prefix=""),
                name="spaces_invitation_key_evidence",
            ),
            models.CheckConstraint(
                check=Q(role__in=["knowledge_admin", "reviewer", "member", "guest"]),
                name="spaces_invitation_non_owner_role",
            ),
            models.CheckConstraint(
                check=(
                    (
                        Q(target_user__isnull=False)
                        & Q(target_user_uuid__isnull=False)
                        & Q(target_user_uuid=models.F("target_user"))
                        & Q(target_email_hmac="")
                        & Q(encrypted_delivery_address="")
                        & Q(target_key__startswith="user:")
                    )
                    | (
                        Q(target_user__isnull=True)
                        & Q(target_user_uuid__isnull=True)
                        & Q(target_email_hmac__regex=r"^[0-9a-f]{64}$")
                        & ~Q(encrypted_delivery_address="")
                        & Q(target_key__startswith="email:")
                    )
                ),
                name="spaces_invitation_target_shape",
            ),
            models.CheckConstraint(
                check=Q(inviter__isnull=True)
                | Q(inviter_uuid=models.F("inviter")),
                name="spaces_invitation_inviter_snapshot",
            ),
            models.CheckConstraint(
                check=(
                    ~Q(status__in=["accepted", "declined"])
                    | (
                        Q(responded_at__isnull=False)
                        & Q(consumed_at__isnull=False)
                    )
                ),
                name="spaces_invitation_response_evidence",
            ),
            models.CheckConstraint(
                check=~Q(status="accepted")
                | Q(resulting_membership_uuid__isnull=False),
                name="spaces_invitation_accept_membership",
            ),
        ]
        indexes = [
            models.Index(
                fields=["space", "status", "expires_at"],
                name="spaces_invitation_state",
            ),
            models.Index(
                fields=["target_key", "status"],
                name="spaces_invitation_target",
            ),
        ]


class InviteCode(models.Model):
    """A space entry / invite / demo-activation code.

    The plaintext code is shown to the creator once and never stored; only a
    SHA-256 hash is persisted. Joining via code creates (or re-activates) a
    membership with ``role`` — it grants entry, not RBAC bypass (SPEC.MD §3.3).
    """

    STATUS_CHOICES = [("active", "Active"), ("revoked", "Revoked")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        KnowledgeSpace, on_delete=models.CASCADE, related_name="invite_codes"
    )
    code_hash = models.CharField(
        max_length=64, unique=True, help_text="SHA-256 hex of the access code"
    )
    code_prefix = models.CharField(
        max_length=12, blank=True, default="", help_text="Display prefix, e.g. 'AUD-'"
    )
    role = models.CharField(
        max_length=20,
        choices=[
            (SpaceMembership.ROLE_MEMBER, "Member"),
            (SpaceMembership.ROLE_GUEST, "Guest"),
        ],
        default=SpaceMembership.ROLE_MEMBER,
    )
    compatibility_kind = models.CharField(
        max_length=32,
        default="legacy_invitation_code",
        editable=False,
    )
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invite_codes_created",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.IntegerField(default=0, help_text="0 = unlimited")
    used_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_invitecode"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(role__in=["member", "guest"]),
                name="spaces_legacy_invite_non_owner",
            ),
        ]

    def __str__(self):
        return f"InviteCode {self.code_prefix}*** -> {self.space} ({self.role})"

    def is_valid(self) -> bool:
        if self.status != "active":
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True


class AdminRegistrationCode(models.Model):
    """A tiered admin-provisioning code — V7.0 (docs/KnowPilot_V7_Identity_RBAC_Spec.md §8).

    Reuses the InviteCode security pattern (SHA-256 hash, plaintext shown once,
    expiry / max-uses / revoke). On registration it grants an
    ``OrganizationMembership`` of ``grants_role`` within the bound scope.

    Security invariant: ``grants_role`` can ONLY be ``org_admin`` or
    ``business_admin``. Super Admin is intentionally absent — the platform's
    highest privilege is never obtainable through any registration entry point
    (CLI ``createsuperuser`` / console promotion only).
    """

    GRANT_CHOICES = [
        (OrganizationMembership.ROLE_ORG_ADMIN, "Organization Admin"),
        (OrganizationMembership.ROLE_BUSINESS_ADMIN, "Business Admin"),
    ]
    STATUS_CHOICES = [("active", "Active"), ("revoked", "Revoked")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code_hash = models.CharField(
        max_length=64, unique=True, help_text="SHA-256 hex of the admin code"
    )
    code_prefix = models.CharField(max_length=12, blank=True, default="")
    grants_role = models.CharField(max_length=20, choices=GRANT_CHOICES)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="admin_codes"
    )
    business_line = models.ForeignKey(
        BusinessLine,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="admin_codes",
        help_text="Required for business_admin; ignored for org_admin.",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.IntegerField(default=0, help_text="0 = unlimited")
    used_count = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_codes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_adminregistrationcode"
        ordering = ["-created_at"]

    def __str__(self):
        scope = self.business_line.code if self.business_line else self.organization.slug
        return f"AdminCode {self.code_prefix}*** -> {self.grants_role} @ {scope}"

    def is_valid(self) -> bool:
        if self.status != "active":
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True


class SpaceEmailInvite(models.Model):
    """A pending invitation addressed to an email that may not be registered yet.

    When an admin invites someone by email (SPEC §M2 / V7 §7.4): if the user
    already exists, a SpaceMembership is created directly; otherwise this row is
    created and *redeemed* on registration — the new account is auto-added to the
    space with ``role`` and notified.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("revoked", "Revoked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    space = models.ForeignKey(
        KnowledgeSpace, on_delete=models.CASCADE, related_name="email_invites"
    )
    role = models.CharField(
        max_length=20, choices=SpaceMembership.ROLE_CHOICES, default=SpaceMembership.ROLE_MEMBER
    )
    invited_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_invites_sent",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_spaceemailinvite"
        unique_together = [("space", "email")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"EmailInvite {self.email} -> {self.space} ({self.role}, {self.status})"

    def is_valid(self) -> bool:
        if self.status != "pending":
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class SpaceAccessRequest(models.Model):
    """A user's idempotent request to join a discoverable knowledge space."""

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_INVALIDATED = "invalidated"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_INVALIDATED, "Invalidated"),
    ]
    SOURCE_ACCESS_CODE = "access_code"
    SOURCE_DISCOVERY = "discovery"
    SOURCE_CHOICES = [
        (SOURCE_ACCESS_CODE, "Access Code"),
        (SOURCE_DISCOVERY, "Discovery"),
    ]
    ROLE_CHOICES = [
        (SpaceMembership.ROLE_MEMBER, "Member"),
        (SpaceMembership.ROLE_GUEST, "Guest"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        KnowledgeSpace, on_delete=models.CASCADE, related_name="access_requests"
    )
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="space_access_requests",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=SpaceMembership.ROLE_MEMBER,
    )
    role_ceiling = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=SpaceMembership.ROLE_MEMBER,
    )
    source_kind = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_DISCOVERY,
    )
    access_code = models.ForeignKey(
        SpaceAccessCode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="access_requests",
    )
    access_code_version = models.PositiveBigIntegerField(null=True, blank=True)
    discovery_policy_version = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        default=1,
    )
    request_version = models.PositiveBigIntegerField(default=1)
    reason = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    expires_at = models.DateTimeField(default=default_access_request_expiry)
    reviewed_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_space_access_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_reason_code = models.CharField(max_length=64, blank=True, default="")
    decision_reason_text = models.CharField(max_length=500, blank=True, default="")
    rejection_reason = models.CharField(max_length=500, blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    resulting_membership_uuid = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_spaceaccessrequest"
        constraints = [
            models.UniqueConstraint(
                fields=["space", "user"],
                condition=Q(status="pending"),
                name="spaces_one_pending_access_request",
            ),
            models.CheckConstraint(
                check=Q(role__in=["member", "guest"])
                & Q(role_ceiling__in=["member", "guest"])
                & (~Q(role_ceiling="guest") | Q(role="guest")),
                name="spaces_access_request_role_ceiling",
            ),
            models.CheckConstraint(
                check=(
                    (
                        Q(source_kind="access_code")
                        & Q(access_code__isnull=False)
                        & Q(access_code_version__isnull=False)
                        & Q(discovery_policy_version__isnull=True)
                    )
                    | (
                        Q(source_kind="discovery")
                        & Q(access_code__isnull=True)
                        & Q(access_code_version__isnull=True)
                        & Q(discovery_policy_version__isnull=False)
                    )
                ),
                name="spaces_access_request_source_shape",
            ),
        ]
        ordering = ["-created_at"]


class GovernancePolicy(models.Model):
    """Versioned, scoped operational policy. Security invariants are not configurable."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="governance_policies")
    space = models.ForeignKey(KnowledgeSpace, null=True, blank=True, on_delete=models.SET_NULL, related_name="governance_policies")
    space_uuid = models.UUIDField(null=True, blank=True, editable=False)
    organization_uuid = models.UUIDField(null=True, blank=True, editable=False)
    locator_digest = models.CharField(
        max_length=64, blank=True, default="", editable=False
    )
    tombstone = models.ForeignKey(
        "spaces.WorkspaceTombstone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="governance_policies",
    )
    revision = models.PositiveIntegerField(default=1)
    values = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_governancepolicy"
        ordering = ["-revision", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(space_uuid__isnull=True, locator_digest="")
                    | Q(
                        space_uuid__isnull=False,
                        organization_uuid__isnull=False,
                        locator_digest__regex=r"^[0-9a-f]{64}$",
                    )
                ),
                name="spaces_governance_scope_evidence",
            ),
        ]

    def clean(self):
        allowed = {
            "model_profile",
            "fast_model_profile_id",
            "deep_model_profile_id",
            "fast_thinking_budget",
            "deep_thinking_budget",
            "retrieval_top_k",
            "similarity_threshold",
            "needs_human_review",
            "max_answer_chars",
            "retention_days",
        }
        invalid = set(self.values) - allowed
        if invalid:
            from django.core.exceptions import ValidationError
            raise ValidationError({"values": f"Unsupported policy fields: {', '.join(sorted(invalid))}"})
        for field_name in ("fast_model_profile_id", "deep_model_profile_id"):
            profile_id = self.values.get(field_name)
            if profile_id is None:
                continue
            try:
                if not isinstance(profile_id, str):
                    raise ValueError
                uuid.UUID(profile_id)
            except (TypeError, ValueError, AttributeError):
                from django.core.exceptions import ValidationError

                raise ValidationError(
                    {"values": f"{field_name} must be a UUID string."}
                ) from None
        for field_name in ("fast_thinking_budget", "deep_thinking_budget"):
            thinking_budget = self.values.get(field_name)
            if thinking_budget is not None and (
                isinstance(thinking_budget, bool)
                or not isinstance(thinking_budget, int)
                or not 1 <= thinking_budget <= 32768
            ):
                from django.core.exceptions import ValidationError

                raise ValidationError(
                    {"values": f"{field_name} must be an integer from 1 to 32768."}
                )
        top_k = self.values.get("retrieval_top_k")
        if top_k is not None and (not isinstance(top_k, int) or not 1 <= top_k <= 20):
            from django.core.exceptions import ValidationError
            raise ValidationError({"values": "retrieval_top_k must be an integer from 1 to 20."})

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            from django.core.exceptions import ValidationError
            raise ValidationError("Governance policy revisions are immutable; create a new revision instead.")
        if self.space_id and not self.space_uuid:
            self.space_uuid = self.space_id
        if self.space_id and not self.organization_uuid:
            self.organization_uuid = self.space.organization_id
        if self.space_id and not self.locator_digest:
            locator = getattr(self.space, "locator_reservation", None)
            if locator is not None:
                self.locator_digest = locator_digest(locator.normalized_locator)
        if self.organization_id and not self.organization_uuid:
            self.organization_uuid = self.organization_id
        self.full_clean()
        return super().save(*args, **kwargs)


class ModelProfile(models.Model):
    """Platform-managed model registry; secrets remain in deployment configuration."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    provider = models.CharField(max_length=40)
    model_id = models.CharField(max_length=160)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spaces_modelprofile"


def resolve_effective_policy(space):
    """Resolve defaults < organization < space; retrieval safety is never configurable."""
    defaults = {"retrieval_top_k": 5, "similarity_threshold": 0.3, "needs_human_review": False, "max_answer_chars": 12000, "retention_days": 365}
    org = GovernancePolicy.objects.filter(organization=space.organization, space__isnull=True).order_by("-revision", "-created_at").first()
    scoped = GovernancePolicy.objects.filter(space=space).order_by("-revision", "-created_at").first()
    if org:
        defaults.update(org.values)
    if scoped:
        defaults.update(scoped.values)
    return defaults


def create_policy_revision(*, organization=None, space=None, values=None):
    """Create (never mutate) the next revision for one policy scope."""
    if bool(organization) == bool(space):
        raise ValueError("A policy revision needs exactly one organization or space scope.")
    query = GovernancePolicy.objects.filter(space=space) if space else GovernancePolicy.objects.filter(organization=organization, space__isnull=True)
    latest = query.order_by("-revision").first()
    return GovernancePolicy.objects.create(
        organization=organization or space.organization,
        space=space,
        revision=(latest.revision + 1) if latest else 1,
        values=values or {},
    )


# V3 governed-workflow aggregates are kept in a dedicated module to make the
# legacy model file reviewable, but are re-exported here for the public app
# import path and Django's model discovery.
from .governed_models import (  # noqa: E402  (models above must load first)
    GovernedActionOutbox,
    GovernedActionRequest,
    WorkspaceCreateRequestDetail,
    WorkspaceCreationPolicy,
    WorkspaceDeletionRequestDetail,
    WorkspaceLocatorReservation,
    WorkspacePurgeCheckpoint,
    WorkspacePurgeDependency,
    WorkspacePurgeJob,
    WorkspaceRetentionHold,
    WorkspaceTombstone,
    WriteIdempotencyRecord,
)
