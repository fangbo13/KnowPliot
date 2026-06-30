# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Identity payload — V7.0.

Single source of truth for the ``user`` object returned on login, registration,
and ``/auth/me/``. Adds the platform-admin scope flags the V7 frontend needs
(``is_super_admin`` / ``is_org_admin`` / ``is_business_admin`` / ``admin_scope``)
so the UI never has to (mis)derive authorization from organizational role_level.
"""

from __future__ import annotations


def platform_admin_flags(user) -> dict:
    """Resolve the user's platform/organization admin scope (axis one)."""
    try:
        from apps.spaces.permissions import admin_scope, is_platform_admin
        is_super = bool(is_platform_admin(user))
        org_ids, bl_ids = admin_scope(user)
    except Exception:  # pragma: no cover - resolution must not break auth
        is_super, org_ids, bl_ids = bool(getattr(user, "is_superuser", False)), set(), set()
    return {
        "is_super_admin": is_super,
        "is_org_admin": bool(org_ids),
        "is_business_admin": bool(bl_ids),
        "admin_scope": {
            "org_ids": [str(x) for x in org_ids],
            "business_line_ids": [str(x) for x in bl_ids],
        },
    }


def identity_roles(user) -> list:
    """Legacy global RBAC role tags (admin / hr) — kept for backward compat."""
    roles = []
    if user.is_superuser or user.has_role("admin"):
        roles.append("admin")
    if user.has_role("hr"):
        roles.append("hr")
    if getattr(user, "is_hr_admin", False) and "hr" not in roles:
        roles.append("hr")
    return roles


def identity_payload(user) -> dict:
    """The full ``user`` object embedded in auth responses."""
    payload = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "is_hr_admin": user.is_hr_admin,
        "is_superuser": user.is_superuser,
        "roles": identity_roles(user),
        "permissions": list(user.get_permissions()),
        "language_preference": user.language_preference,
        "service_line": user.service_line,
        "office_location": user.office_location,
        "role_level": user.role_level,
    }
    payload.update(platform_admin_flags(user))
    return payload
