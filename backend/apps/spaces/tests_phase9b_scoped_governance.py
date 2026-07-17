from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification
from apps.spaces.models import (
    BusinessLine,
    GovernancePolicy,
    KnowledgeSpace,
    ModelProfile,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)
from apps.spaces.permissions import DOCUMENT_UPLOAD, has_space_permission

User = get_user_model()


class Phase9BScopedGovernanceTests(APITestCase):
    def setUp(self):
        self.super_admin = User.objects.create_superuser(
            username="root@example.com", email="root@example.com", password="Strong-pass-123!"
        )
        self.org_admin = User.objects.create_user(
            username="admin@example.com", email="admin@example.com", password="Strong-pass-123!"
        )
        self.member = User.objects.create_user(
            username="member@example.com", email="member@example.com", password="Strong-pass-123!"
        )
        self.org = Organization.objects.create(name="Audit Org", slug="audit-org")
        self.line_a = BusinessLine.objects.create(organization=self.org, name="Audit", code="audit")
        self.line_b = BusinessLine.objects.create(organization=self.org, name="Tax", code="tax")
        self.other_org = Organization.objects.create(name="Other Org", slug="other-org")
        self.space = KnowledgeSpace.objects.create(
            organization=self.org,
            business_line=self.line_a,
            name="Private space",
            code="private-space",
            visibility="organization",
        )
        OrganizationMembership.objects.create(
            user=self.org_admin,
            organization=self.org,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        SpaceMembership.objects.create(
            user=self.org_admin,
            space=self.space,
            role=SpaceMembership.ROLE_OWNER,
        )

    def test_platform_admin_can_create_archive_and_restore_organization(self):
        self.client.force_authenticate(self.super_admin)
        created = self.client.post(
            "/api/v1/admin/organizations/",
            {"name": "New Org", "slug": "new-org"},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        organization_id = created.data["id"]
        archived = self.client.post(f"/api/v1/admin/organizations/{organization_id}/archive/")
        self.assertEqual(archived.status_code, status.HTTP_200_OK, archived.data)
        restored = self.client.post(f"/api/v1/admin/organizations/{organization_id}/restore/")
        self.assertEqual(restored.status_code, status.HTTP_200_OK, restored.data)

    def test_org_admin_can_update_archive_and_restore_own_business_line(self):
        self.client.force_authenticate(self.org_admin)
        updated = self.client.patch(
            f"/api/v1/admin/business-lines/{self.line_a.id}/",
            {"description": "Updated scope"},
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK, updated.data)
        archived = self.client.post(f"/api/v1/admin/business-lines/{self.line_a.id}/archive/")
        self.assertEqual(archived.status_code, status.HTTP_200_OK, archived.data)
        restored = self.client.post(f"/api/v1/admin/business-lines/{self.line_a.id}/restore/")
        self.assertEqual(restored.status_code, status.HTTP_200_OK, restored.data)

    def test_org_admin_can_transfer_only_inside_own_organization(self):
        self.client.force_authenticate(self.org_admin)
        moved = self.client.post(
            f"/api/v1/spaces/{self.space.id}/transfer/",
            {"business_line": str(self.line_b.id)},
            format="json",
        )
        self.assertEqual(moved.status_code, status.HTTP_200_OK, moved.data)
        forbidden = self.client.post(
            f"/api/v1/spaces/{self.space.id}/transfer/",
            {"organization": str(self.other_org.id)},
            format="json",
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_org_admin_can_bind_models_only_inside_own_organization(self):
        profile = ModelProfile.objects.create(
            name="Governed deep",
            provider="openai-compatible",
            model_id="deep-1",
        )
        other_space = KnowledgeSpace.objects.create(
            organization=self.other_org,
            name="Other private space",
            code="other-private-space",
            visibility="organization",
        )
        self.client.force_authenticate(self.org_admin)

        profiles = self.client.get("/api/v1/admin/model-profiles/")
        self.assertEqual(profiles.status_code, status.HTTP_200_OK, profiles.data)
        self.assertEqual(profiles.data["results"][0]["id"], str(profile.id))

        created = self.client.post(
            "/api/v1/admin/governance/policies/",
            {
                "space": str(self.space.id),
                "values": {"deep_model_profile_id": str(profile.id)},
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertTrue(
            GovernancePolicy.objects.filter(space=self.space, revision=1).exists()
        )

        forbidden = self.client.post(
            "/api/v1/admin/governance/policies/",
            {"space": str(other_space.id), "values": {"retrieval_top_k": 4}},
            format="json",
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_archived_space_can_be_restored_by_owner(self):
        self.space.status = "archived"
        self.space.save(update_fields=["status"])
        self.client.force_authenticate(self.org_admin)
        response = self.client.post(f"/api/v1/spaces/{self.space.id}/restore/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.space.refresh_from_db()
        self.assertEqual(self.space.status, "active")

    def test_access_request_is_idempotent_and_approval_creates_membership(self):
        self.client.force_authenticate(self.member)
        first = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/",
            {"role": "member", "reason": "Project work"},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        repeated = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/",
            {"role": "member", "reason": "Project work"},
            format="json",
        )
        self.assertEqual(repeated.status_code, status.HTTP_200_OK, repeated.data)
        self.assertEqual(first.data["id"], repeated.data["id"])

        self.client.force_authenticate(self.org_admin)
        approved = self.client.post(
            f"/api/v1/admin/spaces/{self.space.id}/access-requests/{first.data['id']}/approve/"
        )
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        self.assertTrue(
            SpaceMembership.objects.filter(
                user=self.member, space=self.space, status="active", role="member"
            ).exists()
        )

    def test_access_request_rejection_persists_a_review_reason(self):
        self.client.force_authenticate(self.member)
        requested = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/",
            {"role": "member", "reason": "Temporary need"},
            format="json",
        )
        self.client.force_authenticate(self.org_admin)

        rejected = self.client.post(
            f"/api/v1/admin/spaces/{self.space.id}/access-requests/{requested.data['id']}/reject/",
            {"reason": "Use the approved project workspace instead."},
            format="json",
        )

        self.assertEqual(rejected.status_code, status.HTTP_200_OK, rejected.data)
        self.assertEqual(rejected.data["status"], "rejected")
        self.assertEqual(
            rejected.data["rejection_reason"],
            "Use the approved project workspace instead.",
        )

    def test_owner_can_transfer_ownership_and_clone_configuration(self):
        target = User.objects.create_user(
            username="target@example.com", email="target@example.com", password="Strong-pass-123!"
        )
        SpaceMembership.objects.create(user=target, space=self.space, role="member")
        self.client.force_authenticate(self.org_admin)
        transferred = self.client.post(
            f"/api/v1/spaces/{self.space.id}/transfer-owner/", {"user": str(target.id)}, format="json"
        )
        self.assertEqual(transferred.status_code, status.HTTP_200_OK, transferred.data)
        cloned = self.client.post(
            f"/api/v1/spaces/{self.space.id}/clone/",
            {"name": "Cloned space", "code": "cloned-space", "copy_documents": False},
            format="json",
        )
        self.assertEqual(cloned.status_code, status.HTTP_201_CREATED, cloned.data)
        clone = KnowledgeSpace.objects.get(code="cloned-space")
        self.assertEqual(clone.organization_id, self.space.organization_id)
        self.assertTrue(SpaceMembership.objects.filter(space=clone, user=self.org_admin, role="owner").exists())

    def test_archived_parent_makes_child_space_read_only(self):
        self.org.status = "archived"
        self.org.save(update_fields=["status"])
        self.assertFalse(has_space_permission(self.org_admin, self.space, DOCUMENT_UPLOAD))

    def test_discoverable_spaces_excludes_private_and_already_joined_spaces(self):
        home = KnowledgeSpace.objects.create(
            organization=self.org,
            business_line=self.line_a,
            name="Member home",
            code="member-home",
            visibility="private",
        )
        SpaceMembership.objects.create(user=self.member, space=home, role="member")
        discoverable = KnowledgeSpace.objects.create(
            organization=self.org,
            business_line=self.line_a,
            name="Discoverable space",
            code="discoverable-space",
            visibility="organization",
        )
        private = KnowledgeSpace.objects.create(
            organization=self.org,
            business_line=self.line_a,
            name="Private only",
            code="private-only",
            visibility="private",
        )
        self.client.force_authenticate(self.member)
        response = self.client.get("/api/v1/spaces/discoverable/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        returned_ids = {row["id"] for row in response.data}
        self.assertIn(str(discoverable.id), returned_ids)
        self.assertNotIn(str(private.id), returned_ids)
        self.assertNotIn(str(home.id), returned_ids)

    def test_access_request_approval_notifies_requester(self):
        self.client.force_authenticate(self.member)
        requested = self.client.post(
            f"/api/v1/spaces/{self.space.id}/access-requests/", {"role": "member"}, format="json"
        )
        self.assertEqual(requested.status_code, status.HTTP_201_CREATED, requested.data)
        self.client.force_authenticate(self.org_admin)
        approved = self.client.post(
            f"/api/v1/admin/spaces/{self.space.id}/access-requests/{requested.data['id']}/approve/"
        )
        self.assertEqual(approved.status_code, status.HTTP_200_OK, approved.data)
        self.assertTrue(Notification.objects.filter(recipient=self.member, type="space_access_approved").exists())

    def test_scoped_user_directory_hides_other_organization_users(self):
        SpaceMembership.objects.create(user=self.member, space=self.space, role="member")
        outsider = User.objects.create_user(
            username="outside@example.com", email="outside@example.com", password="Strong-pass-123!"
        )
        outside_space = KnowledgeSpace.objects.create(
            organization=self.other_org,
            name="Outside",
            code="outside-space",
            visibility="private",
        )
        SpaceMembership.objects.create(user=outsider, space=outside_space, role="owner")
        self.client.force_authenticate(self.org_admin)
        listed = self.client.get("/api/v1/admin/users/")
        self.assertEqual(listed.status_code, status.HTTP_200_OK, listed.data)
        rows = listed.data.get("results", listed.data)
        user_ids = {row["id"] for row in rows}
        self.assertIn(str(self.member.id), user_ids)
        self.assertNotIn(str(outsider.id), user_ids)

        denied = self.client.post(
            f"/api/v1/admin/users/{self.member.id}/assignments/",
            {"scope": "organization", "scope_id": str(self.org.id), "role": "org_admin"},
            format="json",
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
