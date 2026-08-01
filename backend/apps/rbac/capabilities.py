# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Server-owned capability vocabulary and deterministic response assembly.

The public capability response is deliberately flat.  Scope IDs describe where
the grants apply; they do not replace scope-qualified permission checks at the
resource endpoint.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.rbac.models import UserRole
from apps.spaces.models import OrganizationMembership, SpaceMembership
from apps.spaces.permissions import active_spaces, effective_space_memberships

MEMBER_CAPABILITIES = frozenset(
    {
        "chat.ask",
        "chat.export",
        "chat.history",
        "chat.share",
        "workspace.ownership.transfer.accept",
        "space.view",
        "document.view",
    }
)

SPACE_ROLE_CAPABILITIES: Mapping[str, frozenset[str]] = {
    "guest": frozenset({"space.view", "document.view", "knowledge.read"}),
    "member": MEMBER_CAPABILITIES | {"knowledge.read", "knowledge.manage"},
    "space_admin": MEMBER_CAPABILITIES
    | {
        "audit.read",
        "knowledge.download",
        "knowledge.index",
        "knowledge.manage",
        "knowledge.read",
        "quality.read",
        "quality.review",
        "taxonomy.manage",
        "workspace.access_requests.manage",
        "workspace.invites.manage",
        "workspace.manage",
        "workspace.members.manage",
    },
    "owner": MEMBER_CAPABILITIES
    | {
        "audit.read",
        "knowledge.download",
        "knowledge.index",
        "knowledge.manage",
        "knowledge.read",
        "quality.read",
        "quality.review",
        "workspace.access_requests.manage",
        "workspace.invites.manage",
        "workspace.lifecycle.manage",
        "workspace.manage",
        "workspace.members.manage",
        "workspace.settings.manage",
        "workspace.ownership.read",
        "workspace.ownership.transfer.request",
    },
}

# An archived workspace remains reachable only to its canonical owner for the
# bounded lifecycle/deletion workflow.  In particular, this set deliberately
# excludes chat, Knowledge content, invitations, members, settings, and every
# grant-creating capability.
ARCHIVED_OWNER_CAPABILITIES = frozenset(
    {
        "audit.read",
        "workspace.lifecycle.manage",
        "workspace.ownership.read",
        "workspace.ownership.transfer.request",
    }
)

PLATFORM_CAPABILITIES = frozenset(
    {
        "platform.access",
        "platform.audit.read",
        "platform.knowledge.read",
        "platform.metrics.read",
        "platform.models.manage",
        "platform.organizations.manage",
        "platform.roles.manage",
        "platform.taxonomy.manage",
        "platform.templates.manage",
        "platform.users.manage",
        "platform.users.offboard",
        "platform.workspace_creation_policies.manage",
        "platform.workspace_creation_requests.manage",
        "workspace.ownership.read",
        "workspace.ownership.transfer.force",
        "governance.admin_succession.manage",
        "governance.users.suspend",
    }
)

ORGANIZATION_ADMIN_CAPABILITIES = frozenset(
    {
        "governance.access",
        "governance.audit.read",
        "governance.business_lines.manage",
        "governance.metrics.read",
        "governance.models.bind",
        "governance.organization.settings.manage",
        "governance.spaces.manage",
        "governance.taxonomy.manage",
        "governance.templates.manage",
        "governance.users.manage",
        "workspace.ownership.read",
        "workspace.ownership.transfer.force",
        "governance.admin_succession.manage",
        "governance.users.suspend",
    }
)

BUSINESS_ADMIN_CAPABILITIES = frozenset(
    {
        "governance.access",
        "governance.audit.read",
        "governance.metrics.read",
        "governance.spaces.manage",
        "governance.taxonomy.manage",
        "governance.templates.manage",
        "governance.users.manage",
        "workspace.ownership.read",
        "workspace.ownership.transfer.force",
        "governance.users.suspend",
    }
)


@dataclass(frozen=True)
class CapabilityGrantSnapshot:
    """Validated grants consumed by the pure response assembler."""

    platform: bool = False
    account_active: bool = False
    organization_ids: tuple[UUID, ...] = ()
    business_line_ids: tuple[UUID, ...] = ()
    space_roles: Mapping[UUID, str] = field(default_factory=dict)
    selected_space_id: UUID | None = None
    deep_space_ids: tuple[UUID, ...] = ()
    thinking_space_ids: tuple[UUID, ...] = ()
    canonical_owner_space_ids: tuple[UUID, ...] = ()
    archived_owner_space_ids: tuple[UUID, ...] = ()


def _sorted_ids(values) -> list[str]:
    return sorted({str(value) for value in values})


def _default_console(snapshot: CapabilityGrantSnapshot) -> str:
    if snapshot.platform:
        return "/platform-admin"
    if snapshot.organization_ids or snapshot.business_line_ids:
        return "/governance"

    selected_role = snapshot.space_roles.get(snapshot.selected_space_id)
    if selected_role and "workspace.manage" in SPACE_ROLE_CAPABILITIES.get(
        selected_role, frozenset()
    ):
        return f"/workspace/{snapshot.selected_space_id}/manage"

    manageable_spaces = sorted(
        str(space_id)
        for space_id, role in snapshot.space_roles.items()
        if "workspace.manage" in SPACE_ROLE_CAPABILITIES.get(role, frozenset())
    )
    if manageable_spaces:
        return f"/workspace/{manageable_spaces[0]}/manage"
    return "/chat"


def build_capability_payload(snapshot: CapabilityGrantSnapshot) -> dict:
    """Build the stable API payload from already-validated grants."""

    capabilities: set[str] = set()
    if snapshot.account_active:
        capabilities.add("workspace.creation.request")
    if snapshot.platform:
        capabilities.update(PLATFORM_CAPABILITIES)
    if snapshot.organization_ids:
        capabilities.update(ORGANIZATION_ADMIN_CAPABILITIES)
    if snapshot.business_line_ids:
        capabilities.update(BUSINESS_ADMIN_CAPABILITIES)
    if snapshot.selected_space_id is not None:
        selected_role = snapshot.space_roles.get(snapshot.selected_space_id, "")
        archived_owner = (
            selected_role == "owner"
            and snapshot.selected_space_id in snapshot.archived_owner_space_ids
        )
        capabilities.update(
            ARCHIVED_OWNER_CAPABILITIES
            if archived_owner
            else SPACE_ROLE_CAPABILITIES.get(selected_role, frozenset())
        )
        if (
            selected_role == "owner"
            and snapshot.selected_space_id in snapshot.canonical_owner_space_ids
            and bool(getattr(settings, "WORKSPACE_PERMANENT_DELETE", False))
        ):
            capabilities.add("workspace.delete.permanent")
        if (
            not archived_owner
            and selected_role != "guest"
            and snapshot.selected_space_id in snapshot.deep_space_ids
            and "chat.ask" in capabilities
        ):
            capabilities.add("chat.deep")
        if (
            not archived_owner
            and selected_role != "guest"
            and snapshot.selected_space_id in snapshot.thinking_space_ids
            and "chat.ask" in capabilities
        ):
            capabilities.add("chat.thinking")

    from apps.core.readiness import _configuration_revision

    return {
        "navigation_mode": (
            "capability" if bool(getattr(settings, "CAPABILITY_NAV", False)) else "legacy"
        ),
        "configuration_revision": _configuration_revision(),
        # Availability describes rollout/readiness inputs only. Authorization
        # remains the exact capability set assembled above.
        "feature_availability": {
            "deep": bool(getattr(settings, "DEEP_ANSWER_MODE", False)),
            "thinking": bool(getattr(settings, "THINKING_MODE", False)),
            "workspace_creation_approval": bool(
                getattr(settings, "WORKSPACE_CREATION_APPROVAL", False)
            ),
            "workspace_join_v2": bool(getattr(settings, "WORKSPACE_JOIN_V2", False)),
            "workspace_permanent_delete": bool(
                getattr(settings, "WORKSPACE_PERMANENT_DELETE", False)
            ),
        },
        "scopes": {
            "platform": snapshot.platform,
            "organization_ids": _sorted_ids(snapshot.organization_ids),
            "business_line_ids": _sorted_ids(snapshot.business_line_ids),
            "space_ids": _sorted_ids(snapshot.space_roles),
        },
        "capabilities": sorted(capabilities),
        "default_console": _default_console(snapshot),
    }


def _active_governance_scopes(user) -> tuple[set[UUID], set[UUID]]:
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
    organization_ids: set[UUID] = set()
    business_line_ids: set[UUID] = set()
    for membership in rows:
        if membership.role == OrganizationMembership.ROLE_ORG_ADMIN:
            organization_ids.add(membership.organization_id)
            continue
        business_line = membership.business_line
        if (
            membership.role == OrganizationMembership.ROLE_BUSINESS_ADMIN
            and business_line is not None
            and business_line.organization_id == membership.organization_id
            and business_line.status == "active"
        ):
            business_line_ids.add(business_line.id)
    return organization_ids, business_line_ids


def _is_platform_authority(user) -> bool:
    if user.is_superuser:
        return True
    return UserRole.objects.filter(
        user=user,
        is_active=True,
        role__name="admin",
        role__is_active=True,
    ).exists()


def _active_space_roles(user) -> dict[UUID, str]:
    """Return explicit effective memberships plus policy guest access only.

    Platform and governance scopes may govern metadata/workflows, but they do
    not synthesize a workspace role or content/chat authority.
    """

    membership_rows = effective_space_memberships(user).values_list("space_id", "role")
    membership_roles = dict(membership_rows)

    spaces = active_spaces().filter(id__in=membership_roles)

    roles: dict[UUID, str] = {}
    for space in spaces.only(
        "id",
        "organization_id",
        "business_line_id",
        "visibility",
    ):
        if space.id in membership_roles:
            roles[space.id] = membership_roles[space.id]
    return roles


def _parse_selected_space_id(space_id) -> UUID | None:
    if space_id in (None, ""):
        return None
    try:
        return UUID(str(space_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise NotFound("Space not found.") from exc


def resolve_capabilities(user, *, space_id=None) -> dict:
    """Resolve authoritative grants without consulting legacy profile fields."""

    selected_space_id = _parse_selected_space_id(space_id)
    platform = _is_platform_authority(user)
    organization_ids, business_line_ids = _active_governance_scopes(user)
    space_roles = _active_space_roles(user)
    from apps.spaces.models import KnowledgeSpace

    selected_space = None
    canonical_owner_space_ids: tuple[UUID, ...] = ()
    archived_owner_space_ids: tuple[UUID, ...] = ()
    if selected_space_id is not None:
        selected_space = active_spaces().filter(pk=selected_space_id).first()
        if selected_space is None:
            archived_space = KnowledgeSpace.objects.filter(
                pk=selected_space_id,
                status="archived",
                owner=user,
            ).first()
            archived_owner_mirror = bool(
                archived_space
                and SpaceMembership.objects.filter(
                    space=archived_space,
                    user=user,
                    role=SpaceMembership.ROLE_OWNER,
                    status="active",
                    expires_at__isnull=True,
                ).exists()
            )
            if archived_owner_mirror:
                selected_space = archived_space
                space_roles[selected_space_id] = SpaceMembership.ROLE_OWNER
                canonical_owner_space_ids = (selected_space_id,)
                archived_owner_space_ids = (selected_space_id,)
            else:
                raise NotFound("Space not found.")
        governed = bool(
            selected_space
            and not archived_owner_space_ids
            and (
                platform
                or selected_space.organization_id in organization_ids
                or selected_space.business_line_id in business_line_ids
            )
        )
        if selected_space_id not in space_roles and not governed:
            raise NotFound("Space not found.")

        if (
            not archived_owner_space_ids
            and space_roles.get(selected_space_id) == SpaceMembership.ROLE_OWNER
            and selected_space.owner_id == user.id
        ):
            canonical_owner_space_ids = (selected_space_id,)

    deep_space_ids: tuple[UUID, ...] = ()
    thinking_space_ids: tuple[UUID, ...] = ()
    selected_role = space_roles.get(selected_space_id)
    if selected_space_id is not None and selected_role and selected_role != "guest":
        from apps.spaces.generation_policy import deep_mode_available, thinking_mode_available

        if selected_space is not None and deep_mode_available(selected_space):
            deep_space_ids = (selected_space_id,)
        if selected_space is not None and thinking_mode_available(selected_space):
            thinking_space_ids = (selected_space_id,)

    return build_capability_payload(
        CapabilityGrantSnapshot(
            platform=platform,
            account_active=bool(user and user.is_active),
            organization_ids=tuple(organization_ids),
            business_line_ids=tuple(business_line_ids),
            space_roles=space_roles,
            selected_space_id=selected_space_id,
            deep_space_ids=deep_space_ids,
            thinking_space_ids=thinking_space_ids,
            canonical_owner_space_ids=canonical_owner_space_ids,
            archived_owner_space_ids=archived_owner_space_ids,
        )
    )
