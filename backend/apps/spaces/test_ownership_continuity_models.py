import importlib
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.spaces.models import Organization, OrganizationMembership, OwnershipTransfer, SpaceMembership


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
        member = get_user_model().objects.create_user(
            username="expiring-member",
            email="expiring-member@example.test",
            password="safe-password",
        )
        membership = SpaceMembership.objects.create(
            space=space,
            user=member,
            role=SpaceMembership.ROLE_MEMBER,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        from apps.spaces.ownership import effective_space_membership

        self.assertFalse(effective_space_membership(membership))

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

    def test_platform_and_governance_authority_do_not_create_workspace_content_access(self):
        from apps.rbac.models import Role, UserRole
        from apps.spaces.ownership import create_space_with_owner
        from apps.spaces.permissions import DOCUMENT_VIEW, effective_space_role, has_space_permission

        owner = get_user_model().objects.create_user(
            username="boundary-owner", email="boundary-owner@example.test", password="safe-password"
        )
        platform = get_user_model().objects.create_user(
            username="boundary-platform", email="boundary-platform@example.test", password="safe-password"
        )
        governor = get_user_model().objects.create_user(
            username="boundary-governor", email="boundary-governor@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="Boundary Org", slug="boundary-org")
        space = create_space_with_owner(
            organization=organization, owner=owner, name="Boundary Space", code="boundary-space"
        )
        role = Role.objects.create(name="admin", label="Platform admin", scope="system")
        UserRole.objects.create(user=platform, role=role)
        OrganizationMembership.objects.create(
            user=governor,
            organization=organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )

        for actor in (platform, governor):
            with self.subTest(actor=actor.username):
                self.assertIsNone(effective_space_role(actor, space))
                self.assertFalse(has_space_permission(actor, space, DOCUMENT_VIEW))

    def test_owner_mirror_database_constraints_reject_multiple_or_ineffective_owners(self):
        from apps.spaces.ownership import create_space_with_owner

        owner = get_user_model().objects.create_user(
            username="db-owner", email="db-owner@example.test", password="safe-password"
        )
        second = get_user_model().objects.create_user(
            username="db-owner-two", email="db-owner-two@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="DB Owner Org", slug="db-owner-org")
        space = create_space_with_owner(
            organization=organization, owner=owner, name="DB Owner Space", code="db-owner-space"
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            SpaceMembership.objects.create(
                space=space,
                user=second,
                role=SpaceMembership.ROLE_OWNER,
                status="active",
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpaceMembership.objects.filter(space=space, user=owner).update(status="revoked")
        with self.assertRaises(IntegrityError), transaction.atomic():
            SpaceMembership.objects.filter(space=space, user=owner).update(expires_at=timezone.now())

    def test_transfer_database_constraint_rejects_requester_as_target(self):
        from apps.spaces.ownership import create_space_with_owner

        owner = get_user_model().objects.create_user(
            username="constraint-owner", email="constraint-owner@example.test", password="safe-password"
        )
        target = get_user_model().objects.create_user(
            username="constraint-target", email="constraint-target@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="Constraint Org", slug="constraint-org")
        space = create_space_with_owner(
            organization=organization,
            owner=owner,
            name="Constraint Space",
            code="constraint-space",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            OwnershipTransfer.objects.create(
                space=space,
                from_owner=owner,
                to_owner=target,
                requested_by=target,
                mode=OwnershipTransfer.MODE_FORCED,
                status=OwnershipTransfer.STATUS_COMPLETED,
                expected_ownership_version=1,
                reason_code="forced",
                idempotency_key=uuid.uuid4(),
                completed_at=timezone.now(),
            )

    def test_stage_c_migration_depends_on_user_metadata_and_backfills_before_non_null(self):
        migration_module = importlib.import_module(
            "apps.spaces.migrations.0010_ownership_continuity_stage_c"
        )
        dependencies = set(migration_module.Migration.dependencies)
        operation_names = [type(operation).__name__ for operation in migration_module.Migration.operations]

        self.assertIn(("users", "0004_user_offboarding_metadata"), dependencies)
        self.assertIn("RunPython", operation_names)
        self.assertLess(operation_names.index("RunPython"), operation_names.index("AlterField"))
