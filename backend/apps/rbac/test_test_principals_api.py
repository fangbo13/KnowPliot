"""Operator-only inventory contract for explicitly marked test principals."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.spaces.models import Organization, OrganizationMembership
from apps.spaces.test_utils import create_test_space


User = get_user_model()


class TestPrincipalInventoryApiTests(APITestCase):
    def setUp(self):
        self.platform = User.objects.create_superuser(
            username="test-principal-platform",
            email="test-principal-platform@example.test",
            password="pw",
        )
        self.employee = User.objects.create_user(
            username="test-principal-employee",
            email="test-principal-employee@example.test",
            password="pw",
        )
        self.expired = User.objects.create_user(
            username="expired-explicit-test",
            email="expired-explicit-test@example.test",
            password="pw",
            account_purpose="test",
            test_principal_expires_at=timezone.now() - timedelta(days=1),
            test_run_id="internal-beta-run-1",
        )
        User.objects.create_user(
            username="future-explicit-test",
            email="future-explicit-test@example.test",
            password="pw",
            account_purpose="test",
            test_principal_expires_at=timezone.now() + timedelta(days=1),
        )
        self.name_only = User.objects.create_user(
            username="name-only-test-account",
            email="name-only-test-account@example.test",
            password="pw",
        )
        inactive = User.objects.create_user(
            username="inactive-explicit-test",
            email="inactive-explicit-test@example.test",
            password="pw",
            account_purpose="test",
            test_principal_expires_at=timezone.now() - timedelta(days=1),
        )
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])

        self.org = Organization.objects.create(
            name="Test principal organization",
            slug="test-principal-organization",
        )
        create_test_space(
            organization=self.org,
            owner=self.expired,
            name="Owned by expired test principal",
            code="expired-test-owned",
        )
        OrganizationMembership.objects.create(
            user=self.expired,
            organization=self.org,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )

    def test_inventory_is_platform_only_exact_and_read_only(self):
        self.client.force_authenticate(self.employee)
        denied = self.client.get(
            "/api/v1/admin/test-principals/?state=expired_active"
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.platform)
        response = self.client.get(
            "/api/v1/admin/test-principals/?state=expired_active"
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(len(response.json()["results"]), 1)
        item = response.json()["results"][0]
        self.assertEqual(item["id"], str(self.expired.id))
        self.assertEqual(item["test_run_id"], "internal-beta-run-1")
        self.assertTrue(item["is_active"])
        self.assertTrue(item["has_owner_blocker"])
        self.assertTrue(item["has_admin_blocker"])
        self.assertEqual(
            item["ownership_impact_url"],
            f"/api/v1/admin/users/{self.expired.id}/offboarding-impact/",
        )
        self.assertNotIn("password", item)
        self.assertIsNone(response.json()["next_cursor"])

        method = self.client.post(
            "/api/v1/admin/test-principals/",
            {"ids": [str(self.expired.id)]},
            content_type="application/json",
        )
        self.assertEqual(method.status_code, 405)
        self.expired.refresh_from_db()
        self.assertTrue(self.expired.is_active)

    def test_inventory_rejects_unbounded_states_and_invalid_cursors(self):
        self.client.force_authenticate(self.platform)
        invalid_state = self.client.get(
            "/api/v1/admin/test-principals/?state=all"
        )
        invalid_cursor = self.client.get(
            "/api/v1/admin/test-principals/?state=expired_active&cursor=not-a-uuid"
        )
        self.assertEqual(invalid_state.status_code, 400)
        self.assertEqual(invalid_state.json()["code"], "invalid_state")
        self.assertEqual(invalid_cursor.status_code, 400)
        self.assertEqual(invalid_cursor.json()["code"], "invalid_cursor")

    def test_approved_exact_allowlist_never_uses_name_pattern_inference(self):
        self.client.force_authenticate(self.platform)
        with override_settings(
            TEST_PRINCIPAL_LEGACY_ALLOWLIST=[str(self.name_only.id)]
        ):
            response = self.client.get(
                "/api/v1/admin/test-principals/?state=expired_active"
            )

        self.assertEqual(response.status_code, 200, response.json())
        by_id = {item["id"]: item for item in response.json()["results"]}
        self.assertIn(str(self.name_only.id), by_id)
        item = by_id[str(self.name_only.id)]
        self.assertEqual(item["inventory_source"], "approved_exact_allowlist")
        self.assertIsNone(item["expires_at"])
