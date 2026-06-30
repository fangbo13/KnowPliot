# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""V7.0 identity / RBAC / notification tests.

Run with:
    python manage.py test apps.users.tests_v7_identity --settings=config.settings.test

Covers the V7 acceptance criteria (docs/KnowPilot_V7_Identity_RBAC_Spec.md §13):
  - regular registration requires a Service Line and lands in a default space;
  - admin-code registration grants OrganizationMembership; Super Admin is never
    obtainable via any registration entry point;
  - email invitations redeem on registration;
  - notifications + announcements feed and read-state;
  - admin-code issuance authorization (super vs org-admin vs employee).
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.notifications.models import Announcement, Notification
from apps.spaces.models import (
    AdminRegistrationCode,
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceEmailInvite,
    SpaceMembership,
)
from apps.spaces.services import generate_admin_code, hash_code

User = get_user_model()

PW = "StrongPass123!"


class V7IdentityTests(APITestCase):
    def setUp(self):
        cache.clear()  # reset signup throttle between test methods
        self.org, _ = Organization.objects.get_or_create(
            slug="default", defaults={"name": "Default Organization"}
        )
        self.bl_tax, _ = BusinessLine.objects.get_or_create(
            organization=self.org, code="tax", defaults={"name": "Tax"}
        )
        self.general, _ = KnowledgeSpace.objects.get_or_create(
            code="general",
            defaults={
                "organization": self.org,
                "name": "General",
                "visibility": "organization",
            },
        )
        self.assurance_space, _ = KnowledgeSpace.objects.get_or_create(
            code="assurance-onboarding",
            defaults={
                "organization": self.org,
                "name": "Assurance Onboarding",
                "visibility": "business_line",
            },
        )
        self.superuser = User.objects.create_superuser(
            username="root@test.com", email="root@test.com", password=PW
        )

    def _make_code(self, grants_role, business_line=None, max_uses=0):
        raw = generate_admin_code("BIZ" if grants_role == "business_admin" else "ORG")
        AdminRegistrationCode.objects.create(
            code_hash=hash_code(raw), code_prefix=raw[:8], grants_role=grants_role,
            organization=self.org, business_line=business_line, max_uses=max_uses,
        )
        return raw

    # ── Regular registration ─────────────────────────────────────────

    def test_regular_registration_requires_service_line(self):
        r = self.client.post("/api/v1/auth/register/", {"email": "a@test.com", "password": PW}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("service_line", r.data.get("detail", r.data))

    def test_regular_registration_success(self):
        r = self.client.post(
            "/api/v1/auth/register/",
            {"email": "alice@test.com", "password": PW, "service_line": "assurance"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("access", r.data)
        self.assertEqual(r.data["user"]["service_line"], "assurance")
        self.assertFalse(r.data["user"]["is_super_admin"])

        alice = User.objects.get(email="alice@test.com")
        # Service Line 'assurance' -> 'assurance-onboarding' default space.
        self.assertTrue(
            SpaceMembership.objects.filter(user=alice, space=self.assurance_space).exists()
        )
        self.assertTrue(Notification.objects.filter(recipient=alice, type="welcome").exists())

    def test_duplicate_email_rejected(self):
        User.objects.create(username="dup@test.com", email="dup@test.com")
        r = self.client.post(
            "/api/v1/auth/register/",
            {"email": "dup@test.com", "password": PW, "service_line": "tax"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    @override_settings(REQUIRE_SIGNUP_APPROVAL=True)
    def test_pending_signup_can_be_approved(self):
        r = self.client.post(
            "/api/v1/auth/register/",
            {"email": "pending@test.com", "password": PW, "service_line": "tax"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["pending"])

        pending = User.objects.get(email="pending@test.com")
        self.assertFalse(pending.is_active)

        self.client.force_authenticate(self.superuser)
        approved = self.client.post(f"/api/v1/rbac/users/{pending.id}/activate/")
        self.assertEqual(approved.status_code, 200, approved.data)
        pending.refresh_from_db()
        self.assertTrue(pending.is_active)
        self.assertTrue(
            Notification.objects.filter(recipient=pending, type="account").exists()
        )

    # ── Admin-code registration ──────────────────────────────────────

    def test_admin_registration_grants_business_admin(self):
        raw = self._make_code("business_admin", business_line=self.bl_tax, max_uses=1)
        r = self.client.post(
            "/api/v1/auth/register-admin/",
            {"email": "bob@test.com", "password": PW, "code": raw},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["user"]["is_business_admin"])
        bob = User.objects.get(email="bob@test.com")
        self.assertTrue(
            OrganizationMembership.objects.filter(
                user=bob, role="business_admin", business_line=self.bl_tax
            ).exists()
        )

    def test_invalid_admin_code_no_orphan_user(self):
        r = self.client.post(
            "/api/v1/auth/register-admin/",
            {"email": "mallory@test.com", "password": PW, "code": "BIZ-totally-invalid"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(email="mallory@test.com").exists())

    def test_admin_code_cannot_grant_super_admin(self):
        """The issue endpoint must reject grants_role=super_admin (not in choices)."""
        self.client.force_authenticate(self.superuser)
        r = self.client.post(
            "/api/v1/admin/registration-codes/",
            {"grants_role": "super_admin", "organization": str(self.org.id)},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    # ── Email invitation redemption ──────────────────────────────────

    def test_email_invite_redeemed_on_registration(self):
        SpaceEmailInvite.objects.create(
            email="carol@test.com", space=self.general,
            role=SpaceMembership.ROLE_KNOWLEDGE_ADMIN, invited_by=self.superuser,
        )
        r = self.client.post(
            "/api/v1/auth/register/",
            {"email": "carol@test.com", "password": PW, "service_line": "tax"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        carol = User.objects.get(email="carol@test.com")
        m = SpaceMembership.objects.filter(user=carol, space=self.general).first()
        self.assertIsNotNone(m)
        self.assertEqual(m.role, SpaceMembership.ROLE_KNOWLEDGE_ADMIN)
        self.assertTrue(Notification.objects.filter(recipient=carol, type="space_invite").exists())

    # ── Notifications + announcements ────────────────────────────────

    def test_notification_feed_and_announcement(self):
        # alice registers -> gets a welcome notification
        self.client.post(
            "/api/v1/auth/register/",
            {"email": "alice@test.com", "password": PW, "service_line": "assurance"},
            format="json",
        )
        alice = User.objects.get(email="alice@test.com")

        # Super admin publishes a version announcement to everyone.
        self.client.force_authenticate(self.superuser)
        r = self.client.post(
            "/api/v1/notifications/announcements/",
            {"title": "V7.0 released", "body": "Identity system", "audience": "all", "version": "V7.0"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(Announcement.objects.filter(version="V7.0").exists())

        # alice sees welcome + announcement; unread >= 2; read-all -> 0.
        self.client.force_authenticate(alice)
        feed = self.client.get("/api/v1/notifications/").data["results"]
        kinds = {it["kind"] for it in feed}
        self.assertIn("notification", kinds)
        self.assertIn("announcement", kinds)

        count = self.client.get("/api/v1/notifications/unread-count/").data["count"]
        self.assertGreaterEqual(count, 2)

        self.client.post("/api/v1/notifications/read-all/")
        self.assertEqual(self.client.get("/api/v1/notifications/unread-count/").data["count"], 0)

    # ── Admin-code issuance authorization ────────────────────────────

    def test_employee_cannot_issue_codes(self):
        emp = User.objects.create(username="emp@test.com", email="emp@test.com")
        self.client.force_authenticate(emp)
        r = self.client.post(
            "/api/v1/admin/registration-codes/",
            {"grants_role": "business_admin", "organization": str(self.org.id),
             "business_line": str(self.bl_tax.id)},
            format="json",
        )
        self.assertEqual(r.status_code, 403)

    def test_org_admin_can_only_issue_business_admin(self):
        org_admin = User.objects.create(username="oa@test.com", email="oa@test.com")
        OrganizationMembership.objects.create(
            user=org_admin, organization=self.org, role="org_admin"
        )
        self.client.force_authenticate(org_admin)

        # business_admin within own org -> allowed
        r1 = self.client.post(
            "/api/v1/admin/registration-codes/",
            {"grants_role": "business_admin", "organization": str(self.org.id),
             "business_line": str(self.bl_tax.id)},
            format="json",
        )
        self.assertEqual(r1.status_code, 201, r1.data)
        self.assertIn("code", r1.data)

        # org_admin code -> forbidden for an org admin
        r2 = self.client.post(
            "/api/v1/admin/registration-codes/",
            {"grants_role": "org_admin", "organization": str(self.org.id)},
            format="json",
        )
        self.assertEqual(r2.status_code, 403)
