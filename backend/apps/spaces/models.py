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

import uuid

# NOTE: aliased because this module declares a ``settings`` JSONField below; the
# bare name ``settings`` would otherwise shadow the Django settings module for
# FK declarations that follow it in the class body.
from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_businessline"
        ordering = ["name"]
        unique_together = [("organization", "code")]

    def __str__(self):
        return f"{self.name} ({self.code})"


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
    name = models.CharField(max_length=200)
    # Global, URL-safe short code for routing / deep links / access-code display.
    code = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=50, blank=True, default="")
    language = models.CharField(max_length=8, default="en")
    visibility = models.CharField(
        max_length=20, choices=VISIBILITY_CHOICES, default="private"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    settings = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_spaces",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_knowledgespace"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} [{self.code}]"

    @property
    def is_active(self) -> bool:
        return self.status == "active"


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spaces_organizationmembership"
        unique_together = [("user", "organization", "business_line", "role")]

    def __str__(self):
        scope = self.business_line.code if self.business_line else self.organization.slug
        return f"{self.user} = {self.role} @ {scope}"


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
        max_length=20, choices=SpaceMembership.ROLE_CHOICES, default=SpaceMembership.ROLE_MEMBER
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
