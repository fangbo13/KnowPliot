# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""RBAC models — V4.0 dual-track permission system.

Defines the Role-Permission-UserRole triplet that replaces the
legacy `is_hr_admin: boolean` flag with a granular, auditable RBAC system.

Roles:
  - hr:  Content domain manager (22 codenames)
  - admin: System domain super-set (35 codenames, includes all HR perms)

Design:
  Phase 2 dual-authorization window — both `is_hr_admin` and RBAC
  permissions are checked. `is_hr_admin` column is kept until Phase 4
  deprecation cleanup.
"""

import uuid

from django.conf import settings
from django.db import models


class Role(models.Model):
    """RBAC Role — e.g. 'hr' (content scope) or 'admin' (system scope)."""

    SCOPE_CHOICES = [
        ("content", "Content Domain"),
        ("system", "System Domain"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=20, unique=True, help_text="Role slug: 'hr' or 'admin'")
    label = models.CharField(max_length=100, help_text="Human-readable role name")
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, help_text="Domain scope")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rbac_role"
        ordering = ["name"]

    def __str__(self):
        return f"{self.label} ({self.name})"


class Permission(models.Model):
    """RBAC Permission codename — e.g. 'document.create', 'user.assign_role'.

    Each codename maps to a resource + action pair. The 35 codenames
    cover 6 domains: document, category, template, workflow, user,
    config, audit, health.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codename = models.CharField(max_length=60, unique=True, help_text="e.g. 'document.create'")
    resource = models.CharField(max_length=30, help_text="e.g. 'document'")
    action = models.CharField(max_length=30, help_text="e.g. 'create' or 'manage_service_lines'")
    label = models.CharField(max_length=200, help_text="Human-readable description")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rbac_permission"
        unique_together = [("resource", "action")]
        ordering = ["resource", "action"]

    def __str__(self):
        return self.codename


class RolePermission(models.Model):
    """Maps a Role to its Permission codenames.

    HR role gets 22 permissions (content domain).
    Admin role gets all 35 permissions (content + system domains).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="permission_roles")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rbac_rolepermission"
        unique_together = [("role", "permission")]

    def __str__(self):
        return f"{self.role.name} → {self.permission.codename}"


class UserRole(models.Model):
    """Assigns a Role to a User, with audit trail (assigned_by).

    A user can have multiple active roles. The assigned_by field
    tracks who granted the role for compliance auditing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_roles",
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_assignments",
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "rbac_userrole"
        unique_together = [("user", "role")]

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.user.email} → {self.role.name} ({status})"
