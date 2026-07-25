# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""User models."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import PermissionDenied
from django.db import models


class User(AbstractUser):
    """Custom user model for EY employees.

    V4.0 RBAC: Added has_role(), has_permission(), get_permissions() methods
    for dual-track permission checking. During Phase 2 (dual-authorization
    window), these methods fall back to is_hr_admin for backward compatibility.
    """

    SERVICE_LINE_CHOICES = [
        ("assurance", "Assurance"),
        ("consulting", "Consulting"),
        ("tax", "Tax"),
        ("strategy_transactions", "Strategy & Transactions"),
        ("core", "Core Business Services"),
    ]

    ROLE_LEVEL_CHOICES = [
        ("staff", "Staff"),
        ("senior", "Senior"),
        ("manager", "Manager"),
        ("senior_manager", "Senior Manager"),
        ("partner", "Partner"),
    ]

    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("zh", "Chinese"),
    ]

    ACCOUNT_PURPOSE_TEST = "test"
    ACCOUNT_PURPOSE_SERVICE = "service"
    ACCOUNT_PURPOSE_CHOICES = [
        (ACCOUNT_PURPOSE_TEST, "Automated test principal"),
        (ACCOUNT_PURPOSE_SERVICE, "Service principal"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    service_line = models.CharField(
        max_length=30, choices=SERVICE_LINE_CHOICES, null=True, blank=True
    )
    office_location = models.CharField(max_length=100, null=True, blank=True)
    role_level = models.CharField(
        max_length=20, choices=ROLE_LEVEL_CHOICES, null=True, blank=True
    )
    start_date = models.DateField(null=True, blank=True)
    language_preference = models.CharField(
        max_length=2, choices=LANGUAGE_CHOICES, default="en"
    )
    THEME_CHOICES = [("system", "System"), ("light", "Light"), ("dark", "Dark")]
    theme_preference = models.CharField(
        max_length=10, choices=THEME_CHOICES, default="system"
    )
    default_space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_for_users",
    )
    notification_preferences = models.JSONField(default=dict, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.BinaryField(null=True, blank=True)
    mfa_pending_secret = models.BinaryField(null=True, blank=True)
    mfa_recovery_codes = models.JSONField(default=list, blank=True)
    manager = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports"
    )
    buddy = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="buddy_assignees"
    )
    is_hr_admin = models.BooleanField(default=False)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deactivated_users",
    )
    deactivation_reason_code = models.CharField(max_length=64, blank=True, default="")
    account_purpose = models.CharField(
        max_length=16,
        choices=ACCOUNT_PURPOSE_CHOICES,
        null=True,
        blank=True,
    )
    test_principal_expires_at = models.DateTimeField(null=True, blank=True)
    test_run_id = models.CharField(max_length=128, blank=True, default="")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users_user"

    def __str__(self):
        return f"{self.email} ({self.employee_id or 'no-id'})"

    def delete(self, *args, **kwargs):
        """Phase 1 retention policy: accounts are offboarded, never hard-deleted."""

        raise PermissionDenied("User hard deletion is disabled; use the offboarding workflow.")

    def save(self, *args, **kwargs):
        """Enforce superuser uniqueness: at most one is_superuser=True account may exist.

        If a second user is set to is_superuser=True, the save will raise ValueError.
        This guarantees the platform always has exactly one super admin.
        """
        if self.is_superuser:
            qs = User.objects.filter(is_superuser=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValueError(
                    "A superuser already exists. Only one super admin is allowed. "
                    "Set the existing superuser's is_superuser=False before creating a new one."
                )
        super().save(*args, **kwargs)

    # ── V4.0 RBAC methods ──────────────────────────────────────────────

    # V4.2 SYS-V4.2-006: Request-level RBAC cache — avoids N+1 queries.
    # Each request now caches permission/role data on request._rbac_cache,
    # so has_permission() + has_role() share the same data instead of
    # making 3 separate DB queries per request (2 for has_permission via
    # get_permissions, 1 for has_role via UserRole filter).
    _rbac_cache = None  # Set by RbacCacheMiddleware per request

    def has_role(self, role_name: str) -> bool:
        """Check if user has an active RBAC role.

        Phase 2 dual-authorization: also returns True if is_hr_admin=True
        and role_name is 'hr' (content scope), or if is_superuser (admin scope).

        V4.2 SYS-V4.2-006: Uses request-level cache to avoid repeated DB queries.
        """
        if self.is_superuser:
            return True  # Superusers implicitly have all roles

        # V4.2 SYS-V4.2-006: Check request-level cache
        cache = self._get_rbac_cache()
        if cache is not None:
            return role_name in cache["roles"]

        from apps.rbac.models import UserRole
        if UserRole.objects.filter(
            user=self, role__name=role_name, is_active=True
        ).exists():
            return True

        # Dual-authorization fallback: is_hr_admin grants 'hr' role equivalent
        if role_name == "hr" and getattr(self, "is_hr_admin", False):
            return True

        return False

    def has_permission(self, codename: str) -> bool:
        """Check if user has a specific RBAC permission codename.

        Phase 2 dual-authorization: falls back to is_hr_admin for
        content-domain permissions (document/category/template/workflow/audit).

        V4.2 SYS-V4.2-006: Uses request-level cache to avoid repeated DB queries.
        V4.2 SYS-V4.2-024: Synced content_resources with permissions.py — added "audit".
        """
        if self.is_superuser:
            return True  # Superusers have all permissions

        # V4.2 SYS-V4.2-006: Check request-level cache
        cache = self._get_rbac_cache()
        if cache is not None:
            if codename in cache["permissions"]:
                return True

        else:
            perms = self.get_permissions()
            if codename in perms:
                return True

        # Dual-authorization fallback: is_hr_admin grants content-domain perms
        if getattr(self, "is_hr_admin", False):
            # V4.2 SYS-V4.2-024: Synced content_resources with permissions.py
            content_resources = {"document", "category", "template", "workflow", "audit"}
            resource = codename.split(".", 1)[0] if "." in codename else codename
            if resource in content_resources:
                return True

        return False

    def get_permissions(self) -> set:
        """Return set of active permission codenames for this user.

        Queries UserRole → RolePermission → Permission.codename chain.

        V4.2 SYS-V4.2-006: Populates request-level cache on first call.
        """
        if self.is_superuser:
            from apps.rbac.models import Permission
            return set(Permission.objects.values_list("codename", flat=True))

        from apps.rbac.models import UserRole, RolePermission

        # V4.2 SYS-V4.2-006: Populate cache if available
        cache = self._get_rbac_cache()
        if cache is not None:
            if cache["permissions"] is None:
                role_ids = UserRole.objects.filter(
                    user=self, is_active=True
                ).values_list("role_id", flat=True)

                perms = set(
                    RolePermission.objects.filter(
                        role_id__in=role_ids
                    ).values_list("permission__codename", flat=True)
                )
                cache["permissions"] = perms

                # Also populate roles cache
                if cache["roles"] is None:
                    cache["roles"] = set(
                        UserRole.objects.filter(
                            user=self, is_active=True
                        ).values_list("role__name", flat=True)
                    )

            return cache["permissions"]

        # No cache available — direct query (e.g., outside request context)
        role_ids = UserRole.objects.filter(
            user=self, is_active=True
        ).values_list("role_id", flat=True)

        return set(
            RolePermission.objects.filter(
                role_id__in=role_ids
            ).values_list("permission__codename", flat=True)
        )

    def _get_rbac_cache(self):
        """Get request-level RBAC cache — V4.2 SYS-V4.2-006.

        Returns None if outside a request context (e.g., management commands).
        """
        return getattr(self, "_rbac_cache", None)


class AuthSession(models.Model):
    """Server-side revocation state for a JWT refresh/access token family."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="auth_sessions"
    )
    refresh_jti = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users_auth_session"
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["user", "revoked_at", "-last_seen_at"]),
        ]

    @property
    def is_active(self):
        from django.utils import timezone

        return self.revoked_at is None and self.expires_at > timezone.now()
