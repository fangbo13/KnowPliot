from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.spaces.models import Organization, OrganizationMembership, SpaceMembership


class OwnershipContinuityModelTests(TestCase):
    def test_create_space_sets_canonical_owner_and_single_owner_mirror(self):
        from apps.spaces.ownership import create_space_with_owner

        user = get_user_model().objects.create_user(
            username="owner", email="owner@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="Owner Org", slug="owner-org")

        space = create_space_with_owner(
            organization=organization,
            owner=user,
            name="Owned space",
            code="owned-space",
        )

        self.assertEqual(space.owner, user)
        self.assertEqual(space.created_by, user)
        self.assertEqual(space.ownership_version, 1)
        self.assertEqual(
            list(
                SpaceMembership.objects.filter(
                    space=space,
                    status="active",
                    role=SpaceMembership.ROLE_OWNER,
                ).values_list("user_id", flat=True)
            ),
            [user.id],
        )

    def test_canonical_owner_requires_an_active_user_and_effective_owner_mirror(self):
        from apps.spaces.ownership import canonical_owner, create_space_with_owner

        user = get_user_model().objects.create_user(
            username="inactive-owner", email="inactive-owner@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="Inactive Org", slug="inactive-org")
        space = create_space_with_owner(
            organization=organization, owner=user, name="Owned", code="inactive-owned"
        )

        self.assertEqual(canonical_owner(space), user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertIsNone(canonical_owner(space))

        user.is_active = True
        user.save(update_fields=["is_active"])
        SpaceMembership.objects.filter(space=space, user=user).update(expires_at=timezone.now())
        self.assertIsNone(canonical_owner(space))

    def test_effective_scope_admin_predicates_reject_inactive_assignments(self):
        from apps.spaces.ownership import (
            effective_business_admin,
            effective_org_admin,
            effective_platform_admin,
        )
        from apps.spaces.models import BusinessLine

        user = get_user_model().objects.create_user(
            username="governor", email="governor@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="Governance Org", slug="governance-org")
        line = BusinessLine.objects.create(organization=organization, name="Line", code="line")
        org_membership = OrganizationMembership.objects.create(
            user=user, organization=organization, role=OrganizationMembership.ROLE_ORG_ADMIN
        )
        business_membership = OrganizationMembership.objects.create(
            user=user,
            organization=organization,
            business_line=line,
            role=OrganizationMembership.ROLE_BUSINESS_ADMIN,
        )

        self.assertTrue(effective_org_admin(user, organization))
        self.assertTrue(effective_business_admin(user, line))
        self.assertFalse(effective_platform_admin(user))
        org_membership.is_active = False
        org_membership.save(update_fields=["is_active"])
        business_membership.is_active = False
        business_membership.save(update_fields=["is_active"])
        self.assertFalse(effective_org_admin(user, organization))
        self.assertFalse(effective_business_admin(user, line))

    def test_effective_platform_admin_includes_active_global_admin_role(self):
        from apps.rbac.models import Role, UserRole
        from apps.spaces.ownership import effective_platform_admin

        user = get_user_model().objects.create_user(
            username="platform-role", email="platform-role@example.test", password="safe-password"
        )
        role = Role.objects.create(name="admin", label="Platform admin", scope="system")
        UserRole.objects.create(user=user, role=role)

        self.assertTrue(effective_platform_admin(user))
