# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Space-scoped permissions — V6.0 (SPEC.MD §M8).

Two permission layers stack:

1. **Platform/governance RBAC** (``apps.rbac``): controls platform metadata and
   governed workflows, but never synthesizes workspace content access.

2. **Space roles** (``SpaceMembership.role``): owner / knowledge_admin /
   reviewer / member / guest, granting a fixed set of space-scoped permission
   codes per the matrix below.

The access code (``InviteCode``) only creates or re-activates a membership — it
never grants permissions beyond the membership role, so it cannot bypass RBAC.

All checks here are **server-side**. Frontend role guards are UX only.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
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

# Legacy role labels retained for compatibility responses only. They are never
# returned by ``effective_space_role`` and do not synthesize content access.
ROLE_SUPER_ADMIN = "super_admin"  # platform-wide (superuser / global 'admin')
ROLE_ORG_ADMIN = "org_admin"  # full access within one organization
ROLE_BUSINESS_ADMIN = "business_admin"  # full access within one business line

# Legacy compatibility set; effective workspace roles come only from explicit
# membership/public-demo policy.
_FULL_ACCESS_ROLES = {ROLE_SUPER_ADMIN, ROLE_ORG_ADMIN, ROLE_BUSINESS_ADMIN}


def active_space_lifecycle_q(*, prefix: str = "") -> Q:
    """One reusable lifecycle predicate for spaces and joined memberships."""

    return (
        Q(**{f"{prefix}status": "active"})
        & Q(**{f"{prefix}organization__status": "active"})
        & (
            Q(**{f"{prefix}business_line__isnull": True})
            | Q(**{f"{prefix}business_line__status": "active"})
        )
    )


def active_spaces():
    """Spaces whose complete tenant lifecycle chain is active."""

    return KnowledgeSpace.objects.filter(active_space_lifecycle_q())


def effective_space_memberships(user):
    """Active, unexpired memberships under an active tenant lifecycle chain."""

    now = timezone.now()
    return (
        SpaceMembership.objects.filter(
            active_space_lifecycle_q(prefix="space__"),
            user=user,
            status="active",
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
    )


def _space_lifecycle_is_active(space: KnowledgeSpace) -> bool:
    return bool(
        space.status == "active"
        and space.organization.status == "active"
        and (space.business_line_id is None or space.business_line.status == "active")
    )


def is_platform_admin(user) -> bool:
    """A platform Super Admin: Django superuser or global RBAC 'admin' role."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        from apps.rbac.models import UserRole

        return UserRole.objects.filter(
            user=user,
            is_active=True,
            role__name="admin",
            role__is_active=True,
        ).exists()
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
    now = timezone.now()
    rows = (
        OrganizationMembership.objects.filter(
            user=user,
            is_active=True,
            organization__status="active",
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
        .select_related("business_line")
    )
    for membership in rows:
        role = membership.role
        org_id = membership.organization_id
        business_line = membership.business_line
        if role == OrganizationMembership.ROLE_ORG_ADMIN:
            org_ids.add(org_id)
        elif (
            role == OrganizationMembership.ROLE_BUSINESS_ADMIN
            and business_line is not None
            and business_line.organization_id == org_id
            and business_line.status == "active"
        ):
            bl_ids.add(business_line.id)
    return org_ids, bl_ids


def can_create_space(user) -> bool:
    """Who may create a new space (platform-level ``space.create``).

    Platform admins or any organization admin.
    """
    if is_platform_admin(user):
        return True
    org_ids, _ = admin_scope(user)
    return bool(org_ids)


def can_restore_space(user, space: KnowledgeSpace) -> bool:
    """Authorize the exceptional transition from archived to active.

    Archived spaces are intentionally outside the normal effective-role
    boundary. Restoration therefore rechecks the explicit canonical owner
    membership while still requiring active organization and business-line
    parents.
    """

    if not user or not user.is_authenticated:
        return False
    if space.organization.status != "active":
        return False
    if space.business_line_id and space.business_line.status != "active":
        return False
    if space.owner_id != user.id:
        return False
    membership = (
        SpaceMembership.objects.filter(
            user=user,
            space=space,
            role=SpaceMembership.ROLE_OWNER,
        )
        .only("status", "expires_at")
        .first()
    )
    return bool(membership and membership.is_effective)


def effective_space_role(user, space: KnowledgeSpace) -> str | None:
    """Resolve the user's effective role in ``space``.

    Returns the explicit effective membership role, ``guest`` for an enabled
    public-demo space, or ``None``. Governance scopes never synthesize content
    access or workspace ownership.
    """
    if not user or not user.is_authenticated:
        return None
    if not _space_lifecycle_is_active(space):
        return None
    membership = (
        effective_space_memberships(user)
        .filter(space=space)
        .only("role", "status", "expires_at")
        .first()
    )
    if membership:
        return membership.role
    return None


def has_space_permission(user, space: KnowledgeSpace, perm: str) -> bool:
    """Server-side space permission check."""
    role = effective_space_role(user, space)
    if role is None:
        return False
    if role in _FULL_ACCESS_ROLES:
        return True
    return perm in ROLE_PERMISSIONS.get(role, set())


def spaces_with_permission(user, perm: str):
    """Active spaces where ``user`` currently holds one exact permission."""

    spaces = active_spaces()
    if not user or not user.is_authenticated:
        return spaces.none()
    eligible_roles = [
        role for role, permissions in ROLE_PERMISSIONS.items() if perm in permissions
    ]
    member_space_ids = effective_space_memberships(user).filter(
        role__in=eligible_roles
    ).values_list("space_id", flat=True)
    access = Q(id__in=member_space_ids)
    return spaces.filter(access).distinct()


def accessible_spaces(user):
    """Queryset of spaces the user may see."""
    spaces = active_spaces()
    member_space_ids = effective_space_memberships(user).values_list(
        "space_id", flat=True
    )
    access = Q(id__in=member_space_ids)
    return spaces.filter(access).distinct()


def ensure_workspace_writable(space: KnowledgeSpace) -> None:
    """Fence every content/grant write once the tenant lifecycle is inactive."""

    if _space_lifecycle_is_active(space):
        return
    from .governed import GovernedWorkflowError

    raise GovernedWorkflowError("workspace_not_writable")


def get_space_or_404(space_id) -> KnowledgeSpace:
    try:
        return KnowledgeSpace.objects.get(id=space_id)
    except (KnowledgeSpace.DoesNotExist, ValueError, TypeError) as exc:
        raise NotFound("Space not found.") from exc


def resolve_space_id(user, space_id, *, require_perm: str | None = None):
    """Resolve one exact space id without disclosing inaccessible spaces."""

    space = get_space_or_404(space_id)
    role = effective_space_role(user, space)
    if role is None:
        raise NotFound("Space not found.")
    if require_perm and not has_space_permission(user, space, require_perm):
        raise PermissionDenied(f"You do not have '{require_perm}' in this space.")
    return space


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

    return resolve_space_id(request.user, space_id, require_perm=require_perm)


class SpaceDocumentPermission(BasePermission):
    """Document management gated by the *active space's* permissions (V6.0).

    Maps the HTTP method to a document permission code and checks it against the
    active space (from the X-Space-Id header). Space owners and knowledge
    admins can manage their space's documents; members can only view. Platform
    and governance metadata authority never substitutes for an explicit
    workspace membership or content capability.

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
        # Raises NotFound if a space id is supplied but inaccessible.
        space = resolve_request_space(request, required=False)
        if space is None:
            return False
        perm = self.METHOD_PERM.get(request.method, DOCUMENT_VIEW)
        return has_space_permission(user, space, perm)
