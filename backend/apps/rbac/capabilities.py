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
from apps.spaces.models import (
    KnowledgeSpace,
    OrganizationMembership,
    SpaceMembership,
)

BASE_CHAT_CAPABILITIES = frozenset({"chat.ask", "chat.history"})

MEMBER_CAPABILITIES = frozenset(
    {
        "chat.ask",
        "chat.export",
        "chat.history",
        "chat.share",
    }
)

SPACE_ROLE_CAPABILITIES: Mapping[str, frozenset[str]] = {
    "guest": frozenset({"chat.ask"}),
    "member": MEMBER_CAPABILITIES,
    "reviewer": BASE_CHAT_CAPABILITIES
    | {
        "audit.read",
        "quality.read",
        "quality.review",
        "workspace.manage",
    },
    "knowledge_admin": BASE_CHAT_CAPABILITIES
    | {
        "knowledge.download",
        "knowledge.index",
        "knowledge.manage",
        "knowledge.read",
        "quality.read",
        "quality.review",
        "workspace.manage",
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
    },
}

PLATFORM_CAPABILITIES = frozenset(
    {
        "platform.access",
        "platform.audit.read",
        "platform.metrics.read",
        "platform.models.manage",
        "platform.organizations.manage",
        "platform.roles.manage",
        "platform.users.manage",
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
        "governance.templates.manage",
        "governance.users.manage",
    }
)

BUSINESS_ADMIN_CAPABILITIES = frozenset(
    {
        "governance.access",
        "governance.audit.read",
        "governance.metrics.read",
        "governance.spaces.manage",
        "governance.templates.manage",
        "governance.users.manage",
    }
)


@dataclass(frozen=True)
class CapabilityGrantSnapshot:
    """Validated grants consumed by the pure response assembler."""

    platform: bool = False
    organization_ids: tuple[UUID, ...] = ()
    business_line_ids: tuple[UUID, ...] = ()
    space_roles: Mapping[UUID, str] = field(default_factory=dict)
    selected_space_id: UUID | None = None


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
    if snapshot.platform:
        capabilities.update(PLATFORM_CAPABILITIES)
    if snapshot.organization_ids:
        capabilities.update(ORGANIZATION_ADMIN_CAPABILITIES)
    if snapshot.business_line_ids:
        capabilities.update(BUSINESS_ADMIN_CAPABILITIES)
    if snapshot.selected_space_id is not None:
        capabilities.update(
            SPACE_ROLE_CAPABILITIES.get(
                snapshot.space_roles.get(snapshot.selected_space_id, ""), frozenset()
            )
        )

    return {
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


def _active_space_roles(
    user,
    *,
    platform: bool,
    organization_ids: set[UUID],
    business_line_ids: set[UUID],
) -> dict[UUID, str]:
    now = timezone.now()
    membership_rows = (
        SpaceMembership.objects.filter(
            user=user,
            status="active",
            space__status="active",
            space__organization__status="active",
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
        .filter(Q(space__business_line__isnull=True) | Q(space__business_line__status="active"))
        .values_list("space_id", "role")
    )
    membership_roles = dict(membership_rows)

    active_spaces = KnowledgeSpace.objects.filter(
        status="active",
        organization__status="active",
    ).filter(Q(business_line__isnull=True) | Q(business_line__status="active"))
    if not platform:
        access = (
            Q(id__in=membership_roles)
            | Q(organization_id__in=organization_ids)
            | Q(business_line_id__in=business_line_ids)
        )
        if getattr(settings, "ENABLE_PUBLIC_DEMO_SPACES", False):
            access |= Q(visibility="public_demo")
        active_spaces = active_spaces.filter(access)

    roles: dict[UUID, str] = {}
    for space in active_spaces.only(
        "id",
        "organization_id",
        "business_line_id",
        "visibility",
    ):
        if (
            platform
            or space.organization_id in organization_ids
            or space.business_line_id in business_line_ids
        ):
            roles[space.id] = "owner"
        elif space.id in membership_roles:
            roles[space.id] = membership_roles[space.id]
        elif (
            getattr(settings, "ENABLE_PUBLIC_DEMO_SPACES", False)
            and space.visibility == "public_demo"
        ):
            roles[space.id] = "guest"
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
    space_roles = _active_space_roles(
        user,
        platform=platform,
        organization_ids=organization_ids,
        business_line_ids=business_line_ids,
    )
    if selected_space_id is not None and selected_space_id not in space_roles:
        raise NotFound("Space not found.")

    return build_capability_payload(
        CapabilityGrantSnapshot(
            platform=platform,
            organization_ids=tuple(organization_ids),
            business_line_ids=tuple(business_line_ids),
            space_roles=space_roles,
            selected_space_id=selected_space_id,
        )
    )
