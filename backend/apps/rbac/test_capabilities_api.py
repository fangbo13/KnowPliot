# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""API contracts for the tenant-safe capability resolver."""

from datetime import timedelta
from uuid import UUID

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.rbac.capabilities import (
    ARCHIVED_OWNER_CAPABILITIES,
    BUSINESS_ADMIN_CAPABILITIES,
    ORGANIZATION_ADMIN_CAPABILITIES,
    PLATFORM_CAPABILITIES,
    SPACE_ROLE_CAPABILITIES,
)
from apps.rbac.models import Role, UserRole
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)
from apps.spaces.permissions import admin_scope, is_platform_admin
from apps.spaces.ownership import create_space_with_owner

User = get_user_model()
ENDPOINT = "/api/v1/rbac/me/capabilities/"


class CapabilityEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name="Active organization",
            slug="capabilities-active",
        )
        cls.business_line = BusinessLine.objects.create(
            organization=cls.organization,
            name="Active line",
            code="CAP-A",
        )
        cls.users = {}
        for role in ("owner", "knowledge_admin", "reviewer", "member", "guest"):
            cls.users[role] = User.objects.create_user(
                email=f"cap-{role}@example.test",
                username=f"cap-{role}",
                password="not-used",
            )
        cls.space = create_space_with_owner(
            organization=cls.organization,
            owner=cls.users["owner"],
            business_line=cls.business_line,
            name="Private capability space",
            code="capabilities-private",
            visibility="private",
        )
        for role in ("knowledge_admin", "reviewer", "member", "guest"):
            SpaceMembership.objects.create(user=cls.users[role], space=cls.space, role=role)
        cls.other_organization = Organization.objects.create(
            name="Other organization",
            slug="capabilities-other",
        )
        cls.other_owner = User.objects.create_user(
            email="cap-other-owner@example.test",
            username="cap-other-owner",
            password="not-used",
        )
        cls.other_space = create_space_with_owner(
            organization=cls.other_organization,
            owner=cls.other_owner,
            name="Other private space",
            code="capabilities-other-private",
            visibility="private",
        )

        cls.org_admin = User.objects.create_user(
            email="cap-org@example.test",
            username="cap-org",
            password="not-used",
        )
        OrganizationMembership.objects.create(
            user=cls.org_admin,
            organization=cls.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )

        cls.business_admin = User.objects.create_user(
            email="cap-business@example.test",
            username="cap-business",
            password="not-used",
        )
        OrganizationMembership.objects.create(
            user=cls.business_admin,
            organization=cls.organization,
            business_line=cls.business_line,
            role=OrganizationMembership.ROLE_BUSINESS_ADMIN,
        )

        cls.superuser = User.objects.create_superuser(
            email="cap-super@example.test",
            username="cap-super",
            password="not-used",
        )
        cls.global_admin = User.objects.create_user(
            email="cap-global@example.test",
            username="cap-global",
            password="not-used",
        )
        cls.admin_role = Role.objects.create(
            name="admin",
            label="Global administrator",
            scope="system",
        )
        UserRole.objects.create(user=cls.global_admin, role=cls.admin_role)

        cls.unscoped_legacy = User.objects.create_user(
            email="cap-legacy@example.test",
            username="cap-legacy",
            password="not-used",
            is_hr_admin=True,
            role_level="manager",
        )
        cls.hr_role = Role.objects.create(
            name="hr",
            label="Legacy HR",
            scope="content",
        )
        UserRole.objects.create(user=cls.unscoped_legacy, role=cls.hr_role)

    def setUp(self):
        self.client = APIClient()

    def get_capabilities(self, user=None, space_id=None):
        self.client.force_authenticate(user=user)
        query = {} if space_id is None else {"space_id": str(space_id)}
        return self.client.get(ENDPOINT, query)

    def test_authentication_is_required(self):
        response = self.get_capabilities()
        self.assertEqual(response.status_code, 401)

    def test_every_space_role_returns_the_locked_allow_and_deny_matrix(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                response = self.get_capabilities(user, self.space.id)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(
                    response.data["capabilities"],
                    sorted(SPACE_ROLE_CAPABILITIES[role] | {"workspace.creation.request"}),
                )
                self.assertEqual(response.data["scopes"]["space_ids"], [str(self.space.id)])
                expected_console = (
                    f"/workspace/{self.space.id}/manage"
                    if role in {"owner", "knowledge_admin", "reviewer"}
                    else "/chat"
                )
                self.assertEqual(response.data["default_console"], expected_console)

        for role in ("knowledge_admin", "reviewer", "guest"):
            response = self.get_capabilities(self.users[role], self.space.id)
            self.assertNotIn("chat.share", response.data["capabilities"])
            self.assertNotIn("chat.export", response.data["capabilities"])

    @override_settings(DEEP_ANSWER_MODE=True)
    @patch("apps.spaces.generation_policy.deep_mode_available", return_value=True)
    def test_governed_deep_is_added_for_member_but_guest_is_always_denied(self, _deep_ready):
        member = self.get_capabilities(self.users["member"], self.space.id)
        guest = self.get_capabilities(self.users["guest"], self.space.id)

        self.assertEqual(member.status_code, 200)
        self.assertIn("chat.deep", member.data["capabilities"])
        self.assertEqual(guest.status_code, 200)
        self.assertNotIn("chat.deep", guest.data["capabilities"])

    def test_organization_admin_is_governance_scoped_without_workspace_content_capabilities(self):
        response = self.get_capabilities(self.org_admin, self.space.id)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["scopes"]["organization_ids"], [str(self.organization.id)])
        self.assertEqual(response.data["scopes"]["business_line_ids"], [])
        self.assertEqual(
            response.data["capabilities"],
            sorted(ORGANIZATION_ADMIN_CAPABILITIES | {"workspace.creation.request"}),
        )
        self.assertEqual(response.data["scopes"]["space_ids"], [])
        self.assertEqual(response.data["default_console"], "/governance")
        self.assertNotIn("platform.access", response.data["capabilities"])
        self.assertNotIn("chat.ask", response.data["capabilities"])
        self.assertNotIn("knowledge.read", response.data["capabilities"])

    def test_business_admin_cannot_receive_organization_or_platform_authority(self):
        response = self.get_capabilities(self.business_admin, self.space.id)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["scopes"]["organization_ids"], [])
        self.assertEqual(
            response.data["scopes"]["business_line_ids"],
            [str(self.business_line.id)],
        )
        self.assertEqual(
            response.data["capabilities"],
            sorted(BUSINESS_ADMIN_CAPABILITIES | {"workspace.creation.request"}),
        )
        self.assertEqual(response.data["scopes"]["space_ids"], [])
        self.assertEqual(response.data["default_console"], "/governance")
        self.assertNotIn("governance.organization.settings.manage", response.data["capabilities"])
        self.assertNotIn("platform.access", response.data["capabilities"])

    def test_superuser_and_active_global_admin_role_are_platform_authority(self):
        for user in (self.superuser, self.global_admin):
            with self.subTest(user=user.username):
                response = self.get_capabilities(user, self.space.id)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertTrue(response.data["scopes"]["platform"])
                self.assertEqual(response.data["default_console"], "/platform-admin")
                self.assertTrue(
                    set(response.data["capabilities"]).issuperset(PLATFORM_CAPABILITIES)
                )
                self.assertEqual(response.data["scopes"]["space_ids"], [])
                self.assertNotIn("chat.ask", response.data["capabilities"])
                self.assertNotIn("knowledge.read", response.data["capabilities"])

    @override_settings(WORKSPACE_PERMANENT_DELETE=True)
    def test_delete_capability_is_canonical_owner_only_and_archived_owner_is_bounded(self):
        active_owner = self.get_capabilities(self.users["owner"], self.space.id)
        platform = self.get_capabilities(self.superuser, self.space.id)

        self.assertIn("workspace.delete.permanent", active_owner.data["capabilities"])
        self.assertNotIn("workspace.delete.permanent", platform.data["capabilities"])

        self.space.status = "archived"
        self.space.archived_at = timezone.now()
        self.space.save(update_fields=["status", "archived_at", "updated_at"])
        archived_owner = self.get_capabilities(self.users["owner"], self.space.id)

        self.assertEqual(archived_owner.status_code, 200, archived_owner.data)
        self.assertEqual(
            set(archived_owner.data["capabilities"]),
            set(ARCHIVED_OWNER_CAPABILITIES)
            | {"workspace.creation.request", "workspace.delete.permanent"},
        )
        for unauthorized in (self.superuser, self.users["member"]):
            with self.subTest(user=unauthorized.username):
                denied = self.get_capabilities(unauthorized, self.space.id)
                self.assertEqual(denied.status_code, 404, denied.data)

    @override_settings(THINKING_MODE=True)
    @patch("apps.spaces.generation_policy.thinking_mode_available", return_value=True, create=True)
    def test_thinking_requires_explicit_non_guest_membership(self, _thinking_ready):
        member = self.get_capabilities(self.users["member"], self.space.id)
        guest = self.get_capabilities(self.users["guest"], self.space.id)
        platform = self.get_capabilities(self.superuser, self.space.id)

        self.assertIn("chat.thinking", member.data["capabilities"])
        self.assertNotIn("chat.thinking", guest.data["capabilities"])
        self.assertNotIn("chat.thinking", platform.data["capabilities"])

    def test_inactive_global_role_does_not_grant_platform_authority(self):
        self.admin_role.is_active = False
        self.admin_role.save(update_fields=["is_active"])

        response = self.get_capabilities(self.global_admin)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["scopes"]["platform"])
        self.assertEqual(response.data["capabilities"], ["workspace.creation.request"])
        self.assertEqual(response.data["default_console"], "/chat")

    def test_authoritative_platform_check_rejects_an_inactive_global_role(self):
        self.admin_role.is_active = False
        self.admin_role.save(update_fields=["is_active"])

        self.assertFalse(is_platform_admin(self.global_admin))

    def test_authoritative_admin_scope_rejects_inactive_expired_and_archived_grants(self):
        organization_membership = OrganizationMembership.objects.get(user=self.org_admin)
        organization_membership.is_active = False
        organization_membership.save(update_fields=["is_active"])
        self.assertEqual(admin_scope(self.org_admin), (set(), set()))

        organization_membership.is_active = True
        organization_membership.expires_at = timezone.now() - timedelta(seconds=1)
        organization_membership.save(update_fields=["is_active", "expires_at"])
        self.assertEqual(admin_scope(self.org_admin), (set(), set()))

        self.business_line.status = "archived"
        self.business_line.save(update_fields=["status"])
        self.assertEqual(admin_scope(self.business_admin), (set(), set()))

        self.organization.status = "archived"
        self.organization.save(update_fields=["status"])
        self.assertEqual(admin_scope(self.org_admin), (set(), set()))

    def test_unscoped_legacy_flags_and_role_level_never_grant_new_capabilities(self):
        response = self.get_capabilities(self.unscoped_legacy)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["scopes"],
            {
                "platform": False,
                "organization_ids": [],
                "business_line_ids": [],
                "space_ids": [],
            },
        )
        self.assertEqual(response.data["capabilities"], ["workspace.creation.request"])
        self.assertEqual(response.data["default_console"], "/chat")
        hidden = self.get_capabilities(self.unscoped_legacy, self.space.id)
        self.assertEqual(hidden.status_code, 404)

    def test_inactive_and_expired_space_memberships_are_not_accessible(self):
        user = self.users["member"]
        membership = SpaceMembership.objects.get(user=user, space=self.space)

        membership.status = "revoked"
        membership.save(update_fields=["status"])
        inactive = self.get_capabilities(user, self.space.id)
        self.assertEqual(inactive.status_code, 404)

        membership.status = "active"
        membership.expires_at = timezone.now() - timedelta(seconds=1)
        membership.save(update_fields=["status", "expires_at"])
        expired = self.get_capabilities(user, self.space.id)
        self.assertEqual(expired.status_code, 404)

    def test_inactive_and_expired_governance_memberships_are_not_scopes(self):
        membership = OrganizationMembership.objects.get(user=self.org_admin)
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        inactive = self.get_capabilities(self.org_admin)
        self.assertEqual(inactive.status_code, 200, inactive.data)
        self.assertEqual(inactive.data["scopes"]["organization_ids"], [])
        self.assertNotIn("governance.access", inactive.data["capabilities"])

        membership.is_active = True
        membership.expires_at = timezone.now() - timedelta(seconds=1)
        membership.save(update_fields=["is_active", "expires_at"])
        expired = self.get_capabilities(self.org_admin, self.space.id)
        self.assertEqual(expired.status_code, 404)

    def test_archived_organization_business_line_or_space_is_never_an_effective_scope(self):
        self.space.status = "archived"
        self.space.save(update_fields=["status"])
        archived_space = self.get_capabilities(self.users["owner"])
        self.assertNotIn(str(self.space.id), archived_space.data["scopes"]["space_ids"])
        archived_owner = self.get_capabilities(self.users["owner"], self.space.id)
        self.assertEqual(archived_owner.status_code, 200, archived_owner.data)
        self.assertEqual(
            set(archived_owner.data["capabilities"]),
            set(ARCHIVED_OWNER_CAPABILITIES) | {"workspace.creation.request"},
        )

        self.space.status = "active"
        self.space.save(update_fields=["status"])
        self.business_line.status = "archived"
        self.business_line.save(update_fields=["status"])
        archived_line = self.get_capabilities(self.business_admin)
        self.assertEqual(archived_line.data["scopes"]["business_line_ids"], [])
        self.assertNotIn(str(self.space.id), archived_line.data["scopes"]["space_ids"])

        self.business_line.status = "active"
        self.business_line.save(update_fields=["status"])
        self.organization.status = "archived"
        self.organization.save(update_fields=["status"])
        archived_org = self.get_capabilities(self.org_admin)
        self.assertEqual(archived_org.data["scopes"]["organization_ids"], [])
        self.assertNotIn(str(self.space.id), archived_org.data["scopes"]["space_ids"])

    def test_inaccessible_invalid_and_nonexistent_space_ids_share_not_found_policy(self):
        outsider = User.objects.create_user(
            email="cap-outsider@example.test",
            username="cap-outsider",
            password="not-used",
        )
        responses = [
            self.get_capabilities(outsider, self.space.id),
            self.get_capabilities(outsider, "not-a-uuid"),
            self.get_capabilities(
                outsider,
                UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            ),
        ]
        baseline = responses[0].data

        for response in responses:
            with self.subTest(status=response.status_code):
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.data, baseline)
                self.assertEqual(response.data["detail"], "Space not found.")

    @override_settings(ENABLE_PUBLIC_DEMO_SPACES=True)
    def test_active_public_demo_does_not_synthesize_guest_or_chat_authority(self):
        public_space = create_space_with_owner(
            organization=self.other_organization,
            owner=self.other_owner,
            name="Public demo",
            code="capabilities-public",
            visibility="public_demo",
        )
        outsider = User.objects.create_user(
            email="cap-public@example.test",
            username="cap-public",
            password="not-used",
        )

        response = self.get_capabilities(outsider, public_space.id)

        self.assertEqual(response.status_code, 404, response.data)

    @override_settings(ENABLE_PUBLIC_DEMO_SPACES=False)
    def test_public_demo_flag_disabled_does_not_create_guest_authority(self):
        public_space = create_space_with_owner(
            organization=self.other_organization,
            owner=self.other_owner,
            name="Disabled public demo",
            code="capabilities-public-disabled",
            visibility="public_demo",
        )
        outsider = User.objects.create_user(
            email="cap-public-off@example.test",
            username="cap-public-off",
            password="not-used",
        )

        response = self.get_capabilities(outsider, public_space.id)

        self.assertEqual(response.status_code, 404)
