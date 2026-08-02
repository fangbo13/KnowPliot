"""Contract tests for the guest-first workspace onboarding policy."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.rbac.capabilities import SPACE_ROLE_CAPABILITIES

from .models import Organization, SpaceMembership
from .ownership import create_space_with_owner


@override_settings(WORKSPACE_JOIN_V2=False)
class GuestFirstWorkspaceRoleTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="onboarding-owner", email="onboarding-owner@example.test", password="pw"
        )
        self.guest = user_model.objects.create_user(
            username="onboarding-guest", email="onboarding-guest@example.test", password="pw"
        )
        self.admin = user_model.objects.create_user(
            username="onboarding-admin", email="onboarding-admin@example.test", password="pw"
        )
        self.target = user_model.objects.create_user(
            username="onboarding-target", email="onboarding-target@example.test", password="pw"
        )
        self.organization = Organization.objects.create(
            name="Onboarding Org", slug="onboarding-org"
        )
        self.space = create_space_with_owner(
            organization=self.organization,
            owner=self.owner,
            name="Onboarding Space",
            code="onboarding-space",
        )
        self.guest_membership = SpaceMembership.objects.create(
            space=self.space,
            user=self.guest,
            role="guest",
            status="active",
        )
        SpaceMembership.objects.create(
            space=self.space,
            user=self.admin,
            role="space_admin",
            status="active",
        )
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user)

    def test_canonical_roles_and_guest_capabilities_are_least_privilege(self):
        self.assertEqual(
            {value for value, _label in SpaceMembership.ROLE_CHOICES},
            {"owner", "space_admin", "member", "guest"},
        )
        self.assertEqual(
            SPACE_ROLE_CAPABILITIES["guest"],
            frozenset({"space.view", "document.view", "knowledge.read"}),
        )
        self.assertNotIn("chat.ask", SPACE_ROLE_CAPABILITIES["guest"])
        self.assertNotIn("reviewer", SPACE_ROLE_CAPABILITIES)
        self.assertNotIn("knowledge_admin", SPACE_ROLE_CAPABILITIES)

    def test_guest_can_complete_onboarding_once_and_member_retry_is_idempotent(self):
        self._auth(self.guest)
        url = f"/api/v1/spaces/{self.space.id}/onboarding/complete/"

        completed = self.client.post(url, {}, format="json")
        self.assertEqual(completed.status_code, 200, completed.data)
        self.guest_membership.refresh_from_db()
        self.assertEqual(self.guest_membership.role, "member")
        self.assertEqual(self.guest_membership.membership_version, 2)
        self.assertIsNotNone(self.guest_membership.onboarding_completed_at)
        self.assertTrue(
            AuditLog.objects.filter(
                action="space_onboarding_complete",
                user=self.guest,
            ).exists()
        )

        completed_at = self.guest_membership.onboarding_completed_at
        repeated = self.client.post(url, {}, format="json")
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.guest_membership.refresh_from_db()
        self.assertEqual(self.guest_membership.membership_version, 2)
        self.assertEqual(self.guest_membership.onboarding_completed_at, completed_at)

    def test_onboarding_rejects_pending_revoked_or_missing_membership(self):
        url = f"/api/v1/spaces/{self.space.id}/onboarding/complete/"
        for status in ("pending", "revoked"):
            with self.subTest(status=status):
                self.guest_membership.status = status
                self.guest_membership.save(update_fields=["status", "updated_at"])
                self._auth(self.guest)
                response = self.client.post(url, {}, format="json")
                self.assertEqual(response.status_code, 403, response.data)
        self._auth(self.target)
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 403, response.data)

    def test_legacy_email_add_normalizes_requested_elevation_to_guest(self):
        self._auth(self.owner)
        response = self.client.post(
            f"/api/v1/spaces/{self.space.id}/members/",
            {"email": self.target.email},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        membership = SpaceMembership.objects.get(space=self.space, user=self.target)
        self.assertEqual(membership.role, "guest")

    def test_space_admin_may_manage_guest_and_member_only_but_owner_can_promote_admin(self):
        self._auth(self.admin)
        denied = self.client.post(
            f"/api/v1/spaces/{self.space.id}/members/",
            {"email": self.target.email, "role": "member"},
            format="json",
        )
        self.assertEqual(denied.status_code, 400, denied.data)

        self._auth(self.owner)
        created = self.client.post(
            f"/api/v1/spaces/{self.space.id}/members/",
            {"email": self.target.email},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        promoted = self.client.patch(
            f"/api/v1/spaces/{self.space.id}/members/{self.target.id}/",
            {"role": "space_admin"},
            format="json",
        )
        self.assertEqual(promoted.status_code, 200, promoted.data)
        self.assertEqual(promoted.data["role"], "space_admin")
