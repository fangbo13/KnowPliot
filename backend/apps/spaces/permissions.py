"""Space-scoped permissions — V6.0 (SPEC.MD §M8).

Two permission layers stack:

1. **Platform RBAC** (``apps.rbac``): global roles ``admin`` / ``hr`` and the
   Django ``is_superuser`` flag. A platform admin / superuser is treated as
   **Super Admin** with full access to every space.

2. **Space roles** (``SpaceMembership.role``): owner / knowledge_admin /
   reviewer / member / guest, granting a fixed set of space-scoped permission
   codes per the matrix below.

The access code (``InviteCode``) only creates or re-activates a membership — it
never grants permissions beyond the membership role, so it cannot bypass RBAC.

All checks here are **server-side**. Frontend role guards are UX only.
"""

from __future__ import annotations

from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission

from .models import KnowledgeSpace, OrganizationMembership, SpaceMembership

# ── Space-scoped permission codes ────────────────────────────────────
SPACE_VIEW = "space.view"
SPACE_UPDATE = "space.update"
SPACE_ARCHIVE = "space.archive"
SPACE_INVITE = "space.invite"
SPACE_MANAGE_MEMBERS = "space.manage_members"
DOCUMENT_VIEW = "document.view"
DOCUMENT_UPLOAD = "document.upload"
DOCUMENT_UPDATE = "document.update"
DOCUMENT_DELETE = "document.delete"
DOCUMENT_REINDEX = "document.reindex"
DOCUMENT_DOWNLOAD = "document.download"
CHAT_ASK = "chat.ask"
CHAT_VIEW_HISTORY = "chat.view_history"
CHAT_SHARE = "chat.share"
CHAT_EXPORT = "chat.export"
AUDIT_VIEW = "audit.view"

# ``space.create`` is a *platform* action (not bound to an existing space) —
# enforced separately via ``can_create_space``.

_OWNER_PERMS = {
    SPACE_VIEW, SPACE_UPDATE, SPACE_ARCHIVE, SPACE_INVITE, SPACE_MANAGE_MEMBERS,
    DOCUMENT_VIEW, DOCUMENT_UPLOAD, DOCUMENT_UPDATE, DOCUMENT_DELETE,
    DOCUMENT_REINDEX, DOCUMENT_DOWNLOAD,
    CHAT_ASK, CHAT_VIEW_HISTORY, CHAT_SHARE, CHAT_EXPORT,
    AUDIT_VIEW,
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    SpaceMembership.ROLE_OWNER: set(_OWNER_PERMS),
    SpaceMembership.ROLE_KNOWLEDGE_ADMIN: {
        SPACE_VIEW,
        DOCUMENT_VIEW, DOCUMENT_UPLOAD, DOCUMENT_UPDATE, DOCUMENT_DELETE,
        DOCUMENT_REINDEX, DOCUMENT_DOWNLOAD,
        CHAT_ASK, CHAT_VIEW_HISTORY,
    },
    SpaceMembership.ROLE_REVIEWER: {
        SPACE_VIEW,
        DOCUMENT_VIEW, DOCUMENT_DOWNLOAD,
        CHAT_ASK, CHAT_VIEW_HISTORY,
        AUDIT_VIEW,
    },
    SpaceMembership.ROLE_MEMBER: {
        SPACE_VIEW,
        DOCUMENT_VIEW,
        CHAT_ASK, CHAT_VIEW_HISTORY, CHAT_SHARE, CHAT_EXPORT,
    },
    SpaceMembership.ROLE_GUEST: {
        SPACE_VIEW,
        DOCUMENT_VIEW,
        CHAT_ASK,
    },
}

# Synthetic roles granting full access within a scope.
ROLE_SUPER_ADMIN = "super_admin"  # platform-wide (superuser / global 'admin')
ROLE_ORG_ADMIN = "org_admin"  # full access within one organization
ROLE_BUSINESS_ADMIN = "business_admin"  # full access within one business line

# Roles that bypass the per-role permission matrix (full access in scope).
_FULL_ACCESS_ROLES = {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_BUSINESS_ADMIN}


def is_platform_admin(user) -> bool:
    """A platform Super Admin: Django superuser or global RBAC 'admin' role."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        return user.has_role("admin")
    except Exception:
        return False


def admin_scope(user) -> tuple[set, set]:
    """Return (org_ids, business_line_ids) the user administers.

    org_admin -> the org's id; business_admin -> the business line's id.
    """
    if not user or not user.is_authenticated:
        return set(), set()
    org_ids: set = set()
    bl_ids: set = set()
    rows = OrganizationMembership.objects.filter(user=user).values_list(
        "role", "organization_id", "business_line_id"
    )
    for role, org_id, bl_id in rows:
        if role == OrganizationMembership.ROLE_ORG_ADMIN:
            org_ids.add(org_id)
        elif role == OrganizationMembership.ROLE_BUSINESS_ADMIN and bl_id:
            bl_ids.add(bl_id)
    return org_ids, bl_ids


def can_create_space(user) -> bool:
    """Who may create a new space (platform-level ``space.create``).

    Platform admins or any organization admin.
    """
    if is_platform_admin(user):
        return True
    org_ids, _ = admin_scope(user)
    return bool(org_ids)


def effective_space_role(user, space: KnowledgeSpace) -> str | None:
    """Resolve the user's effective role in ``space``.

    Returns ``ROLE_SUPER_ADMIN`` for platform admins, the membership role for
    active members, ``guest`` for public-demo spaces, else ``None`` (no access).
    """
    if not user or not user.is_authenticated:
        return None
    if is_platform_admin(user):
        return ROLE_SUPER_ADMIN
    # Org-/business-line admins have full access within their scope.
    org_ids, bl_ids = admin_scope(user)
    if space.organization_id in org_ids:
        return ROLE_ORG_ADMIN
    if space.business_line_id and space.business_line_id in bl_ids:
        return ROLE_BUSINESS_ADMIN
    membership = (
        SpaceMembership.objects.filter(space=space, user=user, status="active")
        .only("role", "status", "expires_at")
        .first()
    )
    if membership and membership.is_effective:
        return membership.role
    if space.visibility == "public_demo" and space.status == "active":
        return SpaceMembership.ROLE_GUEST
    return None


def has_space_permission(user, space: KnowledgeSpace, perm: str) -> bool:
    """Server-side space permission check."""
    role = effective_space_role(user, space)
    if role is None:
        return False
    if role in _FULL_ACCESS_ROLES:
        return True
    # Archived spaces are read-only: deny write/admin perms even to owners.
    if space.status != "active" and perm not in {
        SPACE_VIEW, DOCUMENT_VIEW, DOCUMENT_DOWNLOAD, CHAT_VIEW_HISTORY, AUDIT_VIEW,
    }:
        return False
    return perm in ROLE_PERMISSIONS.get(role, set())


def accessible_spaces(user):
    """Queryset of spaces the user may see."""
    if is_platform_admin(user):
        return KnowledgeSpace.objects.all()
    member_space_ids = SpaceMembership.objects.filter(
        user=user, status="active"
    ).values_list("space_id", flat=True)
    org_ids, bl_ids = admin_scope(user)
    return KnowledgeSpace.objects.filter(
        Q(id__in=list(member_space_ids))
        | Q(visibility="public_demo", status="active")
        | Q(organization_id__in=list(org_ids))
        | Q(business_line_id__in=list(bl_ids))
    ).distinct()


def get_space_or_404(space_id) -> KnowledgeSpace:
    try:
        return KnowledgeSpace.objects.get(id=space_id)
    except (KnowledgeSpace.DoesNotExist, ValueError, TypeError):
        raise NotFound("Space not found.")


def resolve_request_space(request, *, require_perm: str | None = None, required: bool = True):
    """Resolve the active space for a request.

    Reads the ``X-Space-Id`` header first, then ``?space=`` / body ``space``.
    Validates the user can access it (and optionally has ``require_perm``).

    Returns the ``KnowledgeSpace`` or ``None`` (only when ``required=False`` and
    no space id was supplied). Raises ``NotFound`` / ``PermissionDenied``.
    """
    space_id = (
        request.headers.get("X-Space-Id")
        or request.query_params.get("space")
        or (request.data.get("space") if hasattr(request, "data") and isinstance(request.data, dict) else None)
    )
    if not space_id:
        if required:
            raise PermissionDenied("No active space selected. Choose a space first.")
        return None

    space = get_space_or_404(space_id)
    role = effective_space_role(request.user, space)
    if role is None:
        # Do not reveal existence of spaces the user cannot access.
        raise NotFound("Space not found.")
    if require_perm and not has_space_permission(request.user, space, require_perm):
        raise PermissionDenied(f"You do not have '{require_perm}' in this space.")
    return space


class SpaceDocumentPermission(BasePermission):
    """Document management gated by the *active space's* permissions (V6.0).

    Maps the HTTP method to a document permission code and checks it against the
    active space (from the X-Space-Id header). Platform admins bypass. Space
    owners and knowledge admins can manage their space's documents; members can
    only view. When no space is selected, only platform admins may proceed.

    Replaces the old global ``IsHROrAdmin`` gate, which could not express
    "knowledge admin of space X" without granting access to every space.
    """

    METHOD_PERM = {
        "GET": DOCUMENT_VIEW,
        "HEAD": DOCUMENT_VIEW,
        "OPTIONS": DOCUMENT_VIEW,
        "POST": DOCUMENT_UPLOAD,
        "PUT": DOCUMENT_UPDATE,
        "PATCH": DOCUMENT_UPDATE,
        "DELETE": DOCUMENT_DELETE,
    }

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if is_platform_admin(user):
            return True
        # Raises NotFound if a space id is supplied but inaccessible.
        space = resolve_request_space(request, required=False)
        if space is None:
            return False
        perm = self.METHOD_PERM.get(request.method, DOCUMENT_VIEW)
        return has_space_permission(user, space, perm)
