# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""V7 API chain smoke tests.

Run with:
    python manage.py test apps.users.tests_v7_smoke --settings=config.settings.local_test

Nine acceptance checks verifying the core V7 Identity / RBAC / Notification
API chain works end-to-end.  These are intentionally compact and do NOT
duplicate the exhaustive coverage in tests_v7_identity.py.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.notifications.models import Announcement
from apps.spaces.models import (
    AdminRegistrationCode,
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)
from apps.spaces.services import generate_admin_code, hash_code

User = get_user_model()
PW = "StrongPass123!"


class V7SmokeTests(APITestCase):
    """Lightweight chain test for all 9 V7 acceptance points."""

    def setUp(self):
        cache.clear()
        self.org, _ = Organization.objects.get_or_create(
            slug="default", defaults={"name": "Default Organization"},
        )
        self.bl_tax, _ = BusinessLine.objects.get_or_create(
            organization=self.org, code="tax", defaults={"name": "Tax"},
        )
        KnowledgeSpace.objects.get_or_create(
            code="general",
            defaults={
                "organization": self.org,
                "name": "General",
                "visibility": "organization",
            },
        )
        self.superuser = User.objects.create_superuser(
            username="root@smoke.com", email="root@smoke.com", password=PW,
        )

    def _make_code(self, grants_role, business_line=None, max_uses=0):
        raw = generate_admin_code("BIZ" if grants_role == "business_admin" else "ORG")
        AdminRegistrationCode.objects.create(
            code_hash=hash_code(raw),
            code_prefix=raw[:8],
            grants_role=grants_role,
            organization=self.org,
            business_line=business_line,
            max_uses=max_uses,
        )
        return raw

    # ── 1. Regular registration requires service_line ────────────────
    def test_1_registration_requires_service_line(self):
        r = self.client.post(
            "/api/v1/auth/register/",
            {"email": "smoke1@test.com", "password": PW},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    # ── 2. Regular registration returns access token + identity ──────
    def test_2_registration_returns_token_and_identity(self):
        r = self.client.post(
            "/api/v1/auth/register/",
            {"email": "smoke2@test.com", "password": PW, "service_line": "tax"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("access", r.data)
        self.assertIn("user", r.data)
        self.assertEqual(r.data["user"]["email"], "smoke2@test.com")

    # ── 3. Admin code cannot grant super_admin ───────────────────────
    def test_3_admin_code_cannot_grant_super_admin(self):
        self.client.force_authenticate(self.superuser)
        r = self.client.post(
            "/api/v1/admin/registration-codes/",
            {"grants_role": "super_admin", "organization": str(self.org.id)},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    # ── 4. Admin can create business_admin registration code ─────────
    def test_4_admin_creates_business_admin_code(self):
        self.client.force_authenticate(self.superuser)
        r = self.client.post(
            "/api/v1/admin/registration-codes/",
            {
                "grants_role": "business_admin",
                "organization": str(self.org.id),
                "business_line": str(self.bl_tax.id),
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("code", r.data)

    # ── 5. Admin-code registration grants is_business_admin ──────────
    def test_5_admin_code_grants_business_admin(self):
        raw = self._make_code("business_admin", business_line=self.bl_tax, max_uses=1)
        r = self.client.post(
            "/api/v1/auth/register-admin/",
            {"email": "smoke5@test.com", "password": PW, "code": raw},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["user"]["is_business_admin"])

    # ── 6. Notification endpoints accessible ─────────────────────────
    def test_6_notification_endpoints_accessible(self):
        user = User.objects.create_user(
            username="smoke6@test.com", email="smoke6@test.com", password=PW,
        )
        self.client.force_authenticate(user)

        r1 = self.client.get("/api/v1/notifications/")
        self.assertIn(r1.status_code, [200, 301], r1.data if r1.status_code != 301 else "redirect")

        r2 = self.client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("count", r2.data)

    # ── 7. Announcement with audience=all succeeds ───────────────────
    def test_7_announcement_audience_all(self):
        self.client.force_authenticate(self.superuser)
        r = self.client.post(
            "/api/v1/notifications/announcements/",
            {"title": "Smoke V7", "body": "Smoke test", "audience": "all", "version": "V7-smoke"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(Announcement.objects.filter(version="V7-smoke").exists())

    # ── 8. Scoped announcement without audience_ref → 400 ────────────
    def test_8_scoped_announcement_requires_audience_ref(self):
        self.client.force_authenticate(self.superuser)
        for audience in ["org", "business_line", "role"]:
            r = self.client.post(
                "/api/v1/notifications/announcements/",
                {"title": "Scoped", "body": "Missing ref", "audience": audience},
                format="json",
            )
            self.assertEqual(
                r.status_code, 400,
                f"audience={audience} should require audience_ref but got {r.status_code}: {r.data}",
            )

    # ── 9. Pending user can be activated ─────────────────────────────
    @override_settings(REQUIRE_SIGNUP_APPROVAL=True)
    def test_9_pending_user_activation(self):
        # Register a pending user.
        reg = self.client.post(
            "/api/v1/auth/register/",
            {"email": "smoke9@test.com", "password": PW, "service_line": "tax"},
            format="json",
        )
        self.assertEqual(reg.status_code, 201, reg.data)
        self.assertTrue(reg.data.get("pending", False))

        pending = User.objects.get(email="smoke9@test.com")
        self.assertFalse(pending.is_active)

        # Super admin activates.
        self.client.force_authenticate(self.superuser)
        act = self.client.post(f"/api/v1/rbac/users/{pending.id}/activate/")
        self.assertEqual(act.status_code, 200, act.data)

        pending.refresh_from_db()
        self.assertTrue(pending.is_active)
