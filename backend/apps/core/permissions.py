"""Custom permissions — V4.0 RBAC dual-track.

V3.8: IsHROrAdmin (single boolean flag)
V4.0: HasPermission(codename) + HasRole(role_name) (granular RBAC)

Phase 2 dual-authorization window: both RBAC and is_hr_admin are checked.
IsHROrAdmin is preserved for backward compatibility during migration.
"""

import logging

from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


class IsHROrAdmin(BasePermission):
    """Permission class for HR admin and superuser access.

    V4.0: Updated to also check RBAC 'hr' or 'admin' role.
    Phase 2 dual-authorization: RBAC role OR is_hr_admin OR is_superuser.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # RBAC check: user has 'hr' or 'admin' role
        if request.user.has_role("hr") or request.user.has_role("admin"):
            return True

        # Legacy fallback: is_hr_admin boolean or is_superuser
        return getattr(request.user, "is_hr_admin", False) or request.user.is_superuser


class HasPermission(BasePermission):
    """Permission class requiring a specific RBAC permission codename.

    Usage:
        permission_classes = [HasPermission("document.create")]
        permission_classes = [HasPermission("user.assign_role")]

    Phase 2 dual-authorization: RBAC permission OR is_hr_admin (for content
    domain) OR is_superuser (for all domains).
    """

    def __init__(self, codename: str):
        self.codename = codename

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # RBAC check
        if request.user.has_permission(self.codename):
            return True

        # Superuser bypasses all permission checks — V4.1 KB-V4.1-002: add audit trail
        if request.user.is_superuser:
            # V4.2 SYS-V4.2-007: Audit log writing must NOT block authorization.
            # If audit log creation fails (DB error, IntegrityError, etc.), the
            # superuser should still be allowed access — audit logging is a
            # side effect, not an authorization prerequisite.
            try:
                from apps.audit.views import create_audit_log
                create_audit_log(
                    user=request.user,
                    action="config_change",
                    target_type="PermissionBypass",
                    target_id=self.codename,
                    details={"bypassed_permission": self.codename, "via": "is_superuser"},
                    role_used="superuser",
                    request=request,
                )
            except Exception as audit_exc:
                logger.warning(
                    "Audit log creation failed for superuser bypass (permission=%s): %s",
                    self.codename, audit_exc,
                )
            return True

        # Phase 2 dual-authorization fallback
        if getattr(request.user, "is_hr_admin", False):
            # is_hr_admin grants content-domain permissions during migration window
            content_resources = {"document", "category", "template", "workflow", "audit"}
            resource = self.codename.split(".", 1)[0] if "." in self.codename else self.codename
            if resource in content_resources:
                return True

        return False


class HasRole(BasePermission):
    """Permission class requiring a specific RBAC role.

    Usage:
        permission_classes = [HasRole("admin")]
        permission_classes = [HasRole("hr")]

    Phase 2: is_hr_admin users are treated as 'hr' role equivalent.
    is_superuser is treated as 'admin' role equivalent.
    """

    def __init__(self, role_name: str):
        self.role_name = role_name

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # RBAC check
        if request.user.has_role(self.role_name):
            return True

        # Superuser = admin equivalent — V4.1 KB-V4.1-002: add audit trail
        if request.user.is_superuser:
            # V4.2 SYS-V4.2-007: Audit log writing must NOT block authorization.
            try:
                from apps.audit.views import create_audit_log
                create_audit_log(
                    user=request.user,
                    action="config_change",
                    target_type="RoleBypass",
                    target_id=self.role_name,
                    details={"bypassed_role": self.role_name, "via": "is_superuser"},
                    role_used="superuser",
                    request=request,
                )
            except Exception as audit_exc:
                logger.warning(
                    "Audit log creation failed for superuser bypass (role=%s): %s",
                    self.role_name, audit_exc,
                )
            return True

        # Phase 2: is_hr_admin = hr equivalent
        # V4.2 SYS-V4.2-009: Add audit record for is_hr_admin fallback (was missing)
        if self.role_name == "hr" and getattr(request.user, "is_hr_admin", False):
            try:
                from apps.audit.views import create_audit_log
                create_audit_log(
                    user=request.user,
                    action="config_change",
                    target_type="RoleFallback",
                    target_id=self.role_name,
                    details={"fallback_role": self.role_name, "via": "is_hr_admin"},
                    role_used="hr_admin_fallback",
                    request=request,
                )
            except Exception as audit_exc:
                logger.warning(
                    "Audit log creation failed for is_hr_admin fallback (role=%s): %s",
                    self.role_name, audit_exc,
                )
            return True

        return False
