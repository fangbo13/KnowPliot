"""Authorization-first discovery and privacy-bucket tests."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    BusinessLine,
    KnowledgeSpace,
    OfficeLocation,
    Organization,
    SpaceAccessRequest,
    SpaceMembership,
    WorkGroup,
    WorkspaceUsageDaily,
    WorkspaceUsageSummary,
)
from .ownership import create_space_with_owner


class DiscoveryV2Tests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="discovery-user",
            email="discovery-user@example.com",
            password="pw",
        )
        self.owner = User.objects.create_user(
            username="discovery-owner",
            email="discovery-owner@example.com",
            password="pw",
        )
        self.org = Organization.objects.create(name="Assurance", slug="discover-assurance")
        self.line = BusinessLine.objects.create(
            organization=self.org,
            name="审计 Assurance",
            code="audit-discover",
        )
        self.group = WorkGroup.objects.create(
            business_line=self.line,
            normalized_code="methodology",
            display_name="方法论 Methodology",
        )
        self.office = OfficeLocation.objects.create(
            organization=self.org,
            normalized_code="shanghai",
            display_name="上海 Shanghai",
        )
        self.anchor = self._space(
            owner=self.owner,
            name="My workspace",
            code="my-discovery-workspace",
            visibility="organization",
        )
        SpaceMembership.objects.create(
            space=self.anchor,
            user=self.user,
            role="member",
            status="active",
        )
        self.requestable = self._space(
            owner=self.owner,
            name="Unicode 方法库",
            code="unicode-methods",
            visibility="organization",
        )
        self.private = self._space(
            owner=self.owner,
            name="Secret matching methods",
            code="secret-methods",
            visibility="private",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _space(self, *, owner, name, code, visibility):
        space = create_space_with_owner(
            organization=self.org,
            owner=owner,
            business_line=self.line,
            work_group=self.group,
            classification_state="complete",
            name=name,
            code=code,
            description=f"Safe description for {name}",
            visibility=visibility,
        )
        space.office_locations.add(self.office)
        return space

    def get(self, **params):
        return self.client.get(
            "/api/v1/spaces/discoverable/",
            {"contract_version": "2", **params},
        )

    def test_v2_authorizes_before_search_and_emits_safe_cards(self):
        response = self.get(q="方法")
        self.assertEqual(response.status_code, 200, response.data)
        ids = {item["id"] for item in response.data["results"]}
        # Both visible spaces share a matching controlled WorkGroup label;
        # discovery intentionally searches that safe classification metadata.
        self.assertIn(str(self.requestable.id), ids)
        self.assertIn(str(self.anchor.id), ids)
        card = next(
            item
            for item in response.data["results"]
            if item["id"] == str(self.requestable.id)
        )
        self.assertEqual(card["access_state"], "requestable")
        self.assertNotIn("member_count", card)
        self.assertNotIn("owner", card)
        self.assertNotIn(str(self.private.id), ids)

        private_search = self.get(q="Secret")
        self.assertEqual(private_search.status_code, 200)
        self.assertEqual(private_search.data["results"], [])

    def test_well_formed_hidden_filter_is_empty_and_invalid_uuid_is_400(self):
        other_org = Organization.objects.create(name="Other", slug="discover-other")
        other_line = BusinessLine.objects.create(
            organization=other_org,
            name="Other line",
            code="other-line",
        )
        hidden = self.get(business_line_id=str(other_line.id))
        self.assertEqual(hidden.status_code, 200, hidden.data)
        self.assertEqual(hidden.data, {"results": [], "next_cursor": None})
        invalid = self.get(work_group_id="not-a-uuid")
        self.assertEqual(invalid.status_code, 400, invalid.data)

    def test_access_state_priority_and_cursor_binding(self):
        pending = SpaceAccessRequest.objects.create(
            space=self.requestable,
            user=self.user,
            role="member",
            reason="Need access",
            status="pending",
        )
        response = self.get(access_state="pending")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item["id"] for item in response.data["results"]], [str(self.requestable.id)])
        self.assertEqual(response.data["results"][0]["access_state"], "pending")

        member = self.get(access_state="member")
        self.assertIn(str(self.anchor.id), {item["id"] for item in member.data["results"]})
        changed = self.get(cursor="eyJ2IjoxLCJzIjoiYmFkIiwibyI6MH0", sort="recent")
        self.assertEqual(changed.status_code, 400, changed.data)

    def test_frequent_is_private_and_popular_is_k_anonymous(self):
        now = timezone.now()
        WorkspaceUsageDaily.objects.create(
            user=self.user,
            space=self.anchor,
            date=now.date(),
            interaction_count=9,
            last_interacted_at=now,
        )
        WorkspaceUsageSummary.objects.create(
            user=self.user,
            space=self.anchor,
            interaction_count_30d=9,
            last_interacted_at=now,
            computed_through=now.date(),
        )
        highlights = self.client.get("/api/v1/spaces/discovery/highlights/")
        self.assertEqual(highlights.status_code, 200, highlights.data)
        self.assertEqual([item["id"] for item in highlights.data["frequent"]], [str(self.anchor.id)])
        self.assertEqual(highlights.data["popular"], [])

        User = get_user_model()
        for index in range(5):
            participant = User.objects.create_user(
                username=f"popular-{index}",
                email=f"popular-{index}@example.com",
                password="pw",
            )
            WorkspaceUsageDaily.objects.create(
                user=participant,
                space=self.requestable,
                date=now.date(),
                interaction_count=1,
                last_interacted_at=now,
            )
        popular = self.client.get("/api/v1/spaces/discovery/highlights/")
        cards = {item["id"]: item for item in popular.data["popular"]}
        self.assertEqual(cards[str(self.requestable.id)]["activity_bucket"], "5-9")
        self.assertNotIn("active_user_count", cards[str(self.requestable.id)])

    def test_switch_records_only_authorized_daily_usage(self):
        response = self.client.post(f"/api/v1/spaces/{self.anchor.id}/switch/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        daily = WorkspaceUsageDaily.objects.get(user=self.user, space=self.anchor)
        self.assertEqual(daily.interaction_count, 1)
        summary = WorkspaceUsageSummary.objects.get(user=self.user, space=self.anchor)
        self.assertEqual(summary.interaction_count_30d, 1)
        hidden = self.client.post(f"/api/v1/spaces/{self.private.id}/switch/", {}, format="json")
        self.assertEqual(hidden.status_code, 404, hidden.data)
        self.assertFalse(WorkspaceUsageDaily.objects.filter(user=self.user, space=self.private).exists())
