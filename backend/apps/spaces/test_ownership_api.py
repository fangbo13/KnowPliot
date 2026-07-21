import uuid

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.spaces.models import Organization, OrganizationMembership, SpaceMembership
from apps.spaces.ownership import create_space_with_owner


class OwnershipApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            username="owner", email="owner@example.test", password="safe-password"
        )
        self.successor = user_model.objects.create_user(
            username="successor", email="successor@example.test", password="safe-password"
        )
        organization = Organization.objects.create(name="API Org", slug="api-org")
        self.space = create_space_with_owner(
            organization=organization, owner=self.owner, name="API Space", code="api-space"
        )
        SpaceMembership.objects.create(
            space=self.space, user=self.successor, role=SpaceMembership.ROLE_MEMBER, status="active"
        )
        self.guest = user_model.objects.create_user(
            username="guest", email="guest@example.test", password="safe-password"
        )
        SpaceMembership.objects.create(
            space=self.space, user=self.guest, role=SpaceMembership.ROLE_GUEST, status="active"
        )

    def test_ownership_detail_and_voluntary_candidates_expose_safe_eligible_users_only(self):
        self.client.force_authenticate(self.owner)

        ownership = self.client.get(f"/api/v1/spaces/{self.space.id}/ownership/")
        candidates = self.client.get(
            f"/api/v1/spaces/{self.space.id}/ownership-candidates/?purpose=voluntary&q=success"
        )

        self.assertEqual(ownership.status_code, 200)
        self.assertEqual(ownership.data["owner"]["id"], str(self.owner.id))
        self.assertNotIn("email", ownership.data["owner"])
        self.assertEqual(candidates.status_code, 200)
        self.assertEqual([row["id"] for row in candidates.data["results"]], [str(self.successor.id)])

    def test_candidate_endpoint_pages_server_filtered_results(self):
        second = get_user_model().objects.create_user(
            username="successor-two", email="successor-two@example.test", password="safe-password"
        )
        SpaceMembership.objects.create(
            space=self.space, user=second, role=SpaceMembership.ROLE_MEMBER, status="active"
        )
        self.client.force_authenticate(self.owner)

        first_page = self.client.get(
            f"/api/v1/spaces/{self.space.id}/ownership-candidates/?purpose=voluntary&limit=1"
        )
        second_page = self.client.get(
            f"/api/v1/spaces/{self.space.id}/ownership-candidates/?purpose=voluntary&limit=1&offset={first_page.data['next']}"
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.data["next"], 1)
        self.assertEqual(second_page.status_code, 200)
        self.assertIsNone(second_page.data["next"])
        self.assertNotEqual(first_page.data["results"][0]["id"], second_page.data["results"][0]["id"])

    def test_target_may_decline_and_requester_may_cancel_without_owner_change(self):
        self.client.force_authenticate(self.owner)
        first = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/",
            {"to_user_id": str(self.successor.id), "expected_ownership_version": 1, "reason_code": "voluntary"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.client.force_authenticate(self.successor)
        declined = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/{first.data['id']}/decline/", {}, format="json"
        )
        self.client.force_authenticate(self.owner)
        second = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/",
            {"to_user_id": str(self.successor.id), "expected_ownership_version": 1, "reason_code": "voluntary"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        cancelled = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/{second.data['id']}/cancel/", {}, format="json"
        )

        self.space.refresh_from_db()
        self.assertEqual(declined.status_code, 200)
        self.assertEqual(declined.data["status"], "declined")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["status"], "cancelled")
        self.assertEqual(self.space.owner_id, self.owner.id)

    def test_voluntary_transfer_request_is_pending_until_target_accepts(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/",
            {
                "to_user_id": str(self.successor.id),
                "expected_ownership_version": 1,
                "reason_code": "voluntary",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.space.refresh_from_db()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(self.space.owner_id, self.owner.id)

    def test_legacy_transfer_owner_delegates_to_voluntary_transfer_with_deprecation_headers(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            f"/api/v1/spaces/{self.space.id}/transfer-owner/",
            {"user": str(self.successor.id)},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.space.refresh_from_db()
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response["Deprecation"], "true")
        self.assertIn("ownership-transfers", response["Link"])
        self.assertEqual(self.space.owner_id, self.owner.id)

    def test_target_accept_endpoint_completes_pending_transfer(self):
        self.client.force_authenticate(self.owner)
        requested = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/",
            {
                "to_user_id": str(self.successor.id),
                "expected_ownership_version": 1,
                "reason_code": "voluntary",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.client.force_authenticate(self.successor)
        response = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/{requested.data['id']}/accept/",
            {},
            format="json",
        )

        self.space.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(self.space.owner_id, self.successor.id)

    def test_successor_can_list_only_their_pending_ownership_transfers(self):
        self.client.force_authenticate(self.owner)
        requested = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/",
            {
                "to_user_id": str(self.successor.id),
                "expected_ownership_version": 1,
                "reason_code": "voluntary",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.client.force_authenticate(self.successor)
        response = self.client.get("/api/v1/spaces/ownership-transfers/pending/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [requested.data["id"]])
        self.assertEqual(response.data["results"][0]["space"]["display_name"], self.space.name)
        self.assertNotIn("email", response.data["results"][0])

    def test_org_admin_can_force_transfer_through_dedicated_endpoint(self):
        governor = get_user_model().objects.create_user(
            username="governor", email="governor@example.test", password="safe-password"
        )
        OrganizationMembership.objects.create(
            user=governor,
            organization=self.space.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=self.successor,
            name="Successor home",
            code="api-successor-home",
        )
        self.client.force_authenticate(governor)

        response = self.client.post(
            f"/api/v1/spaces/{self.space.id}/ownership-transfers/force/",
            {
                "to_user_id": str(self.successor.id),
                "expected_ownership_version": 1,
                "reason_code": "employment_ended",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.space.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["mode"], "forced")
        self.assertEqual(self.space.owner_id, self.successor.id)

    def test_forced_candidates_exclude_the_acting_governor(self):
        governor = get_user_model().objects.create_user(
            username="candidate-governor", email="candidate-governor@example.test", password="safe-password"
        )
        OrganizationMembership.objects.create(
            user=governor,
            organization=self.space.organization,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        create_space_with_owner(
            organization=self.space.organization,
            owner=governor,
            name="Candidate governor home",
            code="candidate-governor-home",
        )
        self.client.force_authenticate(governor)

        response = self.client.get(
            f"/api/v1/spaces/{self.space.id}/ownership-candidates/?purpose=forced"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn(str(governor.id), {row["id"] for row in response.data["results"]})

    def test_member_and_admin_mutations_cannot_grant_owner_role(self):
        invitee = get_user_model().objects.create_user(
            username="owner-bypass", email="owner-bypass@example.test", password="safe-password"
        )
        self.client.force_authenticate(self.owner)

        created = self.client.post(
            f"/api/v1/spaces/{self.space.id}/members/",
            {"email": invitee.email, "role": SpaceMembership.ROLE_OWNER},
            format="json",
        )
        updated = self.client.patch(
            f"/api/v1/spaces/{self.space.id}/members/{self.successor.id}/",
            {"role": SpaceMembership.ROLE_OWNER},
            format="json",
        )

        platform = get_user_model().objects.create_superuser(
            username="owner-bypass-platform",
            email="owner-bypass-platform@example.test",
            password="safe-password",
        )
        self.client.force_authenticate(platform)
        admin_created = self.client.post(
            f"/api/v1/admin/users/{invitee.id}/assignments/",
            {"scope": "space", "scope_id": str(self.space.id), "role": SpaceMembership.ROLE_OWNER},
            format="json",
        )

        for response in (created, updated, admin_created):
            with self.subTest(response=response.data):
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.data["error_code"], "ownership_workflow_required")
        self.assertFalse(SpaceMembership.objects.filter(space=self.space, user=invitee).exists())
        self.assertEqual(
            SpaceMembership.objects.get(space=self.space, user=self.successor).role,
            SpaceMembership.ROLE_MEMBER,
        )

    def test_member_delete_cannot_remove_canonical_owner(self):
        self.client.force_authenticate(self.owner)

        response = self.client.delete(f"/api/v1/spaces/{self.space.id}/members/{self.owner.id}/")

        self.space.refresh_from_db()
        membership = SpaceMembership.objects.get(space=self.space, user=self.owner)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.space.owner_id, self.owner.id)
        self.assertEqual(membership.status, "active")
