"""Canonical ownership creation helpers.

The owner foreign key is the authority; the owner membership is retained only
as a compatibility mirror for existing permission and member-list consumers.
"""

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
    WorkspaceLocatorReservation,
)


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


def create_space_with_owner(
    *,
    organization,
    owner,
    join_policy="access_code",
    join_code=None,
    **space_fields,
):
    """Create a space with its canonical owner and one owner mirror atomically.

    When *join_policy* is ``access_code`` a *join_code* must be present.  If
    the caller does not supply one, a system code is auto-generated.  When
    *join_policy* is ``global`` the *join_code* is cleared (the space is
    publicly discoverable instead).
    """

    if not effective_user(owner):
        raise ValueError("eligible_owner_required")
    # Auto-generate a join_code for access_code policy when not supplied
    # (backward-compatible with callers that predate the join_policy field).
    if join_policy == "access_code" and not join_code:
        from .join_services import _generate_unique_join_code

        join_code = _generate_unique_join_code()
    with transaction.atomic():
        create_kwargs = {
            "organization": organization,
            "created_by": owner,
            "owner": owner,
            "ownership_version": 1,
            "join_policy": join_policy,
        }
        if join_policy == "access_code" and join_code:
            create_kwargs["join_code"] = join_code
            create_kwargs["join_code_updated_at"] = timezone.now()
        elif join_policy == "global":
            create_kwargs["join_code"] = None
        create_kwargs.update(space_fields)
        space = KnowledgeSpace.objects.create(**create_kwargs)
        SpaceMembership.objects.create(
            space=space,
            user=owner,
            role=SpaceMembership.ROLE_OWNER,
            status="active",
            last_accessed_at=timezone.now(),
        )
        # Every newly live workspace needs durable locator evidence. Governed
        # approval already owns a request-reserved row and transitions it after
        # this helper returns; compatibility creation paths bind a live row
        # here so ownership/retention records can never lack a locator digest.
        from .governed import normalize_locator

        normalized_locator = normalize_locator(organization.slug, space.code)
        locator = (
            WorkspaceLocatorReservation.objects.select_for_update(of=("self",))
            .filter(organization=organization, normalized_code=space.code)
            .first()
        )
        if locator is None:
            WorkspaceLocatorReservation.objects.create(
                organization=organization,
                normalized_code=space.code,
                normalized_locator=normalized_locator,
                state=WorkspaceLocatorReservation.STATE_LIVE,
                live_space=space,
            )
        elif locator.state == WorkspaceLocatorReservation.STATE_RELEASED:
            locator.normalized_locator = normalized_locator
            locator.state = WorkspaceLocatorReservation.STATE_LIVE
            locator.live_space = space
            locator.save(
                update_fields=[
                    "normalized_locator",
                    "state",
                    "live_space",
                    "updated_at",
                ]
            )
        elif locator.state != WorkspaceLocatorReservation.STATE_REQUEST_RESERVED:
            raise IntegrityError("space_locator_conflict")
    return space
