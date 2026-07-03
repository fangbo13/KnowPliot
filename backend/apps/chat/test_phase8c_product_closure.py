"""Phase 8C pinned sessions and safe export tests."""

import subprocess
import sys
import unittest
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership

from .models import ChatSession, Message


User = get_user_model()
BACKEND_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = BACKEND_ROOT.parent / "frontend" / "dist"


class V10ProductSmokeScriptTest(SimpleTestCase):
    @unittest.skipUnless(FRONTEND_DIST.exists(), "frontend build is not mounted")
    def test_v10_smoke_validates_frontend_build(self):
        result = subprocess.run(
            [
                sys.executable,
                str(BACKEND_ROOT / "scripts" / "smoke_v10_product.py"),
                "--frontend-dist",
                str(FRONTEND_DIST),
                "--check-build-only",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "pass"', result.stdout)


class SessionProductClosureTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="phase8c",
            email="phase8c@example.com",
            password="test",
        )
        self.other = User.objects.create_user(
            username="phase8c-other",
            email="phase8c-other@example.com",
            password="test",
        )
        self.org = Organization.objects.create(name="Phase 8C", slug="phase-8c")
        self.space = KnowledgeSpace.objects.create(
            organization=self.org,
            name="Phase 8C",
            code="phase-8c",
        )
        SpaceMembership.objects.create(
            user=self.user,
            space=self.space,
            role=SpaceMembership.ROLE_MEMBER,
        )
        self.session = ChatSession.objects.create(
            user=self.user,
            space=self.space,
            title="Export me",
        )
        Message.objects.create(
            session=self.session,
            space=self.space,
            role="user",
            content="<script>alert('x')</script> Question",
        )
        Message.objects.create(
            session=self.session,
            space=self.space,
            role="assistant",
            content="Safe answer",
        )
        self.client.force_authenticate(self.user)

    def test_patch_pin_and_list_pinned_before_recent(self):
        newer = ChatSession.objects.create(
            user=self.user,
            space=self.space,
            title="Newer",
        )
        response = self.client.patch(
            f"/api/v1/chat/sessions/{self.session.id}/",
            {"is_pinned": True},
            format="json",
        )
        listing = self.client.get(
            "/api/v1/chat/sessions/",
            HTTP_X_SPACE_ID=str(self.space.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_pinned"])
        self.assertEqual(listing.data["results"][0]["id"], str(self.session.id))
        self.assertNotEqual(listing.data["results"][0]["id"], str(newer.id))

    def test_markdown_and_html_exports_validate_owner_and_escape_html(self):
        markdown = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "markdown"},
        )
        html = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "html"},
        )

        self.assertEqual(markdown.status_code, 200)
        self.assertIn("# Export me", markdown.content.decode())
        self.assertIn("attachment;", markdown["Content-Disposition"])
        self.assertEqual(html.status_code, 200)
        body = html.content.decode()
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("javascript:", body.lower())

        self.client.force_authenticate(self.other)
        denied = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "markdown"},
        )
        self.assertEqual(denied.status_code, 404)

    def test_export_denies_owner_after_space_access_is_revoked(self):
        membership = SpaceMembership.objects.get(user=self.user, space=self.space)
        membership.status = "revoked"
        membership.save(update_fields=["status"])

        response = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "markdown"},
        )

        self.assertEqual(response.status_code, 403)

    def test_export_rejects_unknown_format(self):
        response = self.client.get(
            f"/api/v1/chat/sessions/{self.session.id}/export/",
            {"format": "pdf"},
        )
        self.assertEqual(response.status_code, 400)
