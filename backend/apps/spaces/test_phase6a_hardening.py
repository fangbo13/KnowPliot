"""Phase 6A production hardening baseline tests."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.spaces.admin_operations import collect_system_health
from apps.spaces.models import BusinessLine, Organization, OrganizationMembership
from apps.spaces.test_utils import create_test_space


User = get_user_model()


class Phase6AHardeningBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Hardening Org", slug="hardening-org")
        cls.line = BusinessLine.objects.create(
            organization=cls.org, name="Hardening Line", code="hardening-line"
        )
        cls.space = create_test_space(
            organization=cls.org,
            business_line=cls.line,
            name="Hardening Space",
            code="hardening-space",
        )
        cls.admin = User.objects.create_user(
            username="hardening-admin",
            email="hardening-admin@example.com",
            password="test",
        )
        cls.member = User.objects.create_user(
            username="hardening-member",
            email="hardening-member@example.com",
            password="test",
        )
        OrganizationMembership.objects.create(
            user=cls.admin,
            organization=cls.org,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )


class ProductionHealthPayloadTest(Phase6AHardeningBase):
    @override_settings(
        DEBUG=False,
        ALLOWED_HOSTS=["knowpilot.example.com"],
        CORS_ALLOW_ALL_ORIGINS=False,
        CSRF_COOKIE_SECURE=True,
        SESSION_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=True,
        STATIC_ROOT="/srv/knowpilot/static",
        MEDIA_ROOT="/srv/knowpilot/media",
    )
    @patch("apps.spaces.admin_operations._check_redis")
    @patch("apps.spaces.admin_operations._check_celery")
    def test_health_payload_includes_production_readiness_checks(self, celery, redis):
        celery.return_value = None
        redis.return_value = None

        payload = collect_system_health()

        self.assertIn("migrations", payload["services"])
        self.assertIn("static_files", payload["services"])
        self.assertIn("media_storage", payload["services"])
        self.assertIn("security_config", payload["services"])
        self.assertIn("export_limits", payload["services"])
        self.assertEqual(payload["services"]["security_config"]["status"], "configured")
        self.assertNotIn("knowpilot.example.com", str(payload["services"]["security_config"]))

    @override_settings(DEBUG=True, ALLOWED_HOSTS=["*"], CORS_ALLOW_ALL_ORIGINS=True)
    def test_security_config_reports_missing_items_without_secret_values(self):
        payload = collect_system_health()

        security = payload["services"]["security_config"]
        self.assertEqual(security["status"], "degraded")
        self.assertIn("DEBUG", security["missing"])
        self.assertIn("CORS_ALLOW_ALL_ORIGINS", security["missing"])
        self.assertNotIn("SECRET_KEY", str(security))


class StableErrorResponseTest(Phase6AHardeningBase):
    def test_admin_permission_denied_uses_stable_detail_and_code(self):
        self.client.force_authenticate(self.member)

        response = self.client.get("/api/v1/admin/health/")

        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.data)
        self.assertIn("code", response.data)
        self.assertEqual(response.data["code"], "permission_denied")
