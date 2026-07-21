import re

import pyotp
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership
from apps.spaces.test_utils import create_test_space


User = get_user_model()
PASSWORD = "Strong-pass-123!"
NEW_PASSWORD = "New-strong-pass-456!"
MFA_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MFA_ENCRYPTION_KEY=MFA_KEY,
    FRONTEND_URL="http://frontend.test",
)
class Phase9AAccountSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="user@example.com",
            email="user@example.com",
            password=PASSWORD,
        )
        self.org = Organization.objects.create(name="Org", slug="org")
        self.allowed_space = create_test_space(
            organization=self.org,
            name="Allowed",
            code="allowed",
        )
        self.other_space = create_test_space(
            organization=self.org,
            name="Other",
            code="other",
        )
        SpaceMembership.objects.create(
            user=self.user,
            space=self.allowed_space,
            role=SpaceMembership.ROLE_MEMBER,
            status="active",
        )

    def login(self):
        response = self.client.post(
            "/api/v1/auth/token/",
            {"email": self.user.email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_preferences_are_allowlisted_and_default_space_requires_access(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = self.client.patch(
            "/api/v1/auth/me/preferences/",
            {
                "language_preference": "zh",
                "theme_preference": "dark",
                "default_space": str(self.allowed_space.id),
                "notification_preferences": {
                    "announcements": False,
                    "quality": True,
                    "unknown": True,
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.patch(
            "/api/v1/auth/me/preferences/",
            {"default_space": str(self.other_space.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.patch(
            "/api/v1/auth/me/preferences/",
            {
                "theme_preference": "dark",
                "default_space": str(self.allowed_space.id),
                "notification_preferences": {
                    "announcements": False,
                    "quality": True,
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["theme_preference"], "dark")
        self.assertEqual(str(response.data["default_space"]), str(self.allowed_space.id))

    def test_revoked_session_rejects_existing_access_and_refresh_tokens(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        sessions = self.client.get("/api/v1/auth/sessions/")
        self.assertEqual(sessions.status_code, status.HTTP_200_OK, sessions.data)
        session_id = sessions.data[0]["id"]

        revoked = self.client.delete(f"/api/v1/auth/sessions/{session_id}/")
        self.assertEqual(revoked.status_code, status.HTTP_204_NO_CONTENT)

        self.assertEqual(
            self.client.get("/api/v1/auth/me/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.client.credentials()
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/token/refresh/",
                {"refresh": tokens["refresh"]},
                format="json",
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_password_reset_is_non_enumerating_and_sends_single_use_link(self):
        known = self.client.post(
            "/api/v1/auth/password/reset/request/",
            {"email": self.user.email},
            format="json",
        )
        unknown = self.client.post(
            "/api/v1/auth/password/reset/request/",
            {"email": "missing@example.com"},
            format="json",
        )
        self.assertEqual(known.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(unknown.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)

        match = re.search(r"uid=([^&\s]+)&token=([^\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        uid, token = match.groups()
        payload = {"uid": uid, "token": token, "new_password": NEW_PASSWORD}

        confirmed = self.client.post(
            "/api/v1/auth/password/reset/confirm/", payload, format="json"
        )
        self.assertEqual(confirmed.status_code, status.HTTP_204_NO_CONTENT)
        replay = self.client.post(
            "/api/v1/auth/password/reset/confirm/", payload, format="json"
        )
        self.assertEqual(replay.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mfa_challenge_is_single_use_and_recovery_code_is_consumed(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        setup = self.client.post(
            "/api/v1/auth/mfa/setup/",
            {"current_password": PASSWORD},
            format="json",
        )
        self.assertEqual(setup.status_code, status.HTTP_200_OK, setup.data)
        secret = setup.data["secret"]
        code = pyotp.TOTP(secret).now()
        confirmed = self.client.post(
            "/api/v1/auth/mfa/confirm/",
            {"code": code},
            format="json",
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK, confirmed.data)
        recovery_code = confirmed.data["recovery_codes"][0]

        self.client.credentials()
        first = self.client.post(
            "/api/v1/auth/token/",
            {"email": self.user.email, "password": PASSWORD},
            format="json",
        )
        self.assertTrue(first.data["mfa_required"])
        challenge = first.data["challenge"]

        completed = self.client.post(
            "/api/v1/auth/token/mfa/",
            {"challenge": challenge, "code": recovery_code},
            format="json",
        )
        self.assertEqual(completed.status_code, status.HTTP_200_OK, completed.data)
        replay = self.client.post(
            "/api/v1/auth/token/mfa/",
            {"challenge": challenge, "code": recovery_code},
            format="json",
        )
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)
