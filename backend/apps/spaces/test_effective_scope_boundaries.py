# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Regression contracts for one effective workspace-access boundary."""

from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient

from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    SpaceMembership,
)
from apps.spaces.permissions import CHAT_ASK, resolve_request_space

User = get_user_model()


class EffectiveSpaceBoundaryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name="Effective scope organization",
            slug="effective-scope",
        )
        cls.business_line = BusinessLine.objects.create(
            organization=cls.organization,
            name="Effective scope line",
            code="EFFECTIVE",
        )
        cls.space = KnowledgeSpace.objects.create(
            organization=cls.organization,
            business_line=cls.business_line,
            name="Effective private space",
            code="effective-private",
            visibility="private",
        )
        cls.user = User.objects.create_user(
            email="effective-member@example.test",
            username="effective-member",
            password="not-used",
        )
        cls.membership = SpaceMembership.objects.create(
            user=cls.user,
            space=cls.space,
            role=SpaceMembership.ROLE_MEMBER,
        )
        cls.outsider = User.objects.create_user(
            email="effective-outsider@example.test",
            username="effective-outsider",
            password="not-used",
        )

    def setUp(self):
        self.client = APIClient()

    def listed_space_ids(self, user):
        self.client.force_authenticate(user=user)
        response = self.client.get("/api/v1/spaces/")
        self.assertEqual(response.status_code, 200, response.data)
        return {row["id"] for row in response.data}

    def resolve_chat_space(self, user, space_id):
        request = SimpleNamespace(
            user=user,
            headers={"X-Space-Id": str(space_id)},
            query_params={},
            data={},
        )
        return resolve_request_space(request, require_perm=CHAT_ASK)

    def test_active_unexpired_membership_is_listed_and_resolves_chat(self):
        self.assertIn(str(self.space.id), self.listed_space_ids(self.user))
        self.assertEqual(self.resolve_chat_space(self.user, self.space.id).id, self.space.id)

    def test_expired_membership_is_excluded_from_list_and_request_resolution(self):
        self.membership.expires_at = timezone.now() - timedelta(seconds=1)
        self.membership.save(update_fields=["expires_at"])

        self.assertNotIn(str(self.space.id), self.listed_space_ids(self.user))
        with self.assertRaises(NotFound):
            self.resolve_chat_space(self.user, self.space.id)

    def test_archived_space_or_parent_is_excluded_from_list_and_request_resolution(self):
        lifecycle_targets = [
            (self.space, "space"),
            (self.business_line, "business_line"),
            (self.organization, "organization"),
        ]
        for target, label in lifecycle_targets:
            with self.subTest(target=label):
                target.status = "archived"
                target.save(update_fields=["status"])

                self.assertNotIn(str(self.space.id), self.listed_space_ids(self.user))
                with self.assertRaises(NotFound):
                    self.resolve_chat_space(self.user, self.space.id)

                target.status = "active"
                target.save(update_fields=["status"])

    @override_settings(ENABLE_PUBLIC_DEMO_SPACES=False)
    def test_public_demo_flag_off_excludes_guest_from_list_and_request_resolution(self):
        public_space = KnowledgeSpace.objects.create(
            organization=self.organization,
            business_line=self.business_line,
            name="Disabled public demo",
            code="effective-public-disabled",
            visibility="public_demo",
        )

        self.assertNotIn(str(public_space.id), self.listed_space_ids(self.outsider))
        with self.assertRaises(NotFound):
            self.resolve_chat_space(self.outsider, public_space.id)

    @override_settings(ENABLE_PUBLIC_DEMO_SPACES=True)
    def test_active_public_demo_flag_on_grants_guest_chat_only_boundary(self):
        public_space = KnowledgeSpace.objects.create(
            organization=self.organization,
            business_line=self.business_line,
            name="Enabled public demo",
            code="effective-public-enabled",
            visibility="public_demo",
        )

        self.assertIn(str(public_space.id), self.listed_space_ids(self.outsider))
        self.assertEqual(
            self.resolve_chat_space(self.outsider, public_space.id).id,
            public_space.id,
        )
