"""Canonical ownership creation helpers.

The owner foreign key is the authority; the owner membership is retained only
as a compatibility mirror for existing permission and member-list consumers.
"""

from django.db import models, transaction
from django.utils import timezone

from .models import BusinessLine, KnowledgeSpace, Organization, OrganizationMembership, SpaceMembership


def effective_user(user) -> bool:
    """Return whether a principal may currently hold governance responsibility."""

    return bool(user and user.is_active)


def effective_space_membership(membership: SpaceMembership | None) -> bool:
    """Return whether a membership may currently grant a space responsibility."""

    return bool(membership and effective_user(membership.user) and membership.is_effective)


def canonical_owner(space: KnowledgeSpace):
    """Return the effective authoritative owner, or ``None`` for an anomaly."""

    if not space.owner_id or not effective_user(space.owner):
        return None
    membership = SpaceMembership.objects.select_related("user").filter(
        space=space,
        user_id=space.owner_id,
        role=SpaceMembership.ROLE_OWNER,
    ).first()
    return space.owner if effective_space_membership(membership) else None


def effective_platform_admin(user) -> bool:
    if not effective_user(user):
        return False
    if user.is_superuser:
        return True
    from apps.rbac.models import UserRole

    return UserRole.objects.filter(
        user=user,
        is_active=True,
        role__name="admin",
        role__is_active=True,
    ).exists()


def effective_org_admin(user, organization: Organization) -> bool:
    return effective_user(user) and OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        business_line__isnull=True,
        role=OrganizationMembership.ROLE_ORG_ADMIN,
        is_active=True,
    ).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=timezone.now())
    ).exists()


def effective_business_admin(user, business_line: BusinessLine) -> bool:
    return effective_user(user) and OrganizationMembership.objects.filter(
        user=user,
        organization=business_line.organization,
        business_line=business_line,
        role=OrganizationMembership.ROLE_BUSINESS_ADMIN,
        is_active=True,
    ).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gte=timezone.now())
    ).exists()


def create_space_with_owner(*, organization, owner, **space_fields):
    """Create a space with its canonical owner and one owner mirror atomically."""

    with transaction.atomic():
        space = KnowledgeSpace.objects.create(
            organization=organization,
            created_by=owner,
            owner=owner,
            ownership_version=1,
            **space_fields,
        )
        SpaceMembership.objects.create(
            space=space,
            user=owner,
            role=SpaceMembership.ROLE_OWNER,
            status="active",
            last_accessed_at=timezone.now(),
        )
    return space
