"""Controlled taxonomy and immutable creation-policy API tests."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    BusinessLine,
    OfficeLocation,
    Organization,
    WorkGroup,
    WorkspaceCreationPolicy,
)


class TaxonomyPolicyApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="taxonomy-platform-admin",
            email="taxonomy-admin@example.com",
            password="pw",
        )
        self.user = User.objects.create_user(
            username="taxonomy-user",
            email="taxonomy-user@example.com",
            password="pw",
        )
        self.org = Organization.objects.create(name="Taxonomy Org", slug="taxonomy-org")
        self.line = BusinessLine.objects.create(
            organization=self.org,
            name="Assurance",
            code="assurance",
        )
        self.group = WorkGroup.objects.create(
            business_line=self.line,
            normalized_code="team-a",
            display_name="Team A",
        )
        self.office = OfficeLocation.objects.create(
            organization=self.org,
            normalized_code="shanghai",
            display_name="Shanghai",
        )
        self.client = APIClient()

    def key(self):
        return {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}

    def test_creation_selectors_fail_closed_without_active_policy(self):
        self.client.force_authenticate(self.user)
        empty = self.client.get(
            "/api/v1/spaces/taxonomy/business-lines/",
            {"context": "creation"},
        )
        self.assertEqual(empty.status_code, 200, empty.data)
        self.assertEqual(empty.data["results"], [])
        WorkspaceCreationPolicy.objects.create(
            business_line=self.line,
            revision=1,
            status="active",
            audience="registered_beta",
            review_route="platform",
            reviewer_separation_required=True,
        )
        visible = self.client.get(
            "/api/v1/spaces/taxonomy/business-lines/",
            {"context": "creation", "q": "Assur"},
        )
        self.assertEqual(visible.status_code, 200, visible.data)
        self.assertEqual([row["id"] for row in visible.data["results"]], [str(self.line.id)])
        groups = self.client.get(
            "/api/v1/spaces/taxonomy/work-groups/",
            {"context": "creation", "scope_id": str(self.line.id)},
        )
        self.assertEqual([row["id"] for row in groups.data["results"]], [str(self.group.id)])

    def test_taxonomy_mutations_are_shape_strict_and_idempotent(self):
        self.client.force_authenticate(self.admin)
        key = self.key()
        body = {
            "parent_id": str(self.line.id),
            "normalized_code": "ag-12345",
            "display_name": "Assurance Group 12345",
        }
        first = self.client.post(
            "/api/v1/admin/taxonomy/work-groups/", body, format="json", **key
        )
        self.assertEqual(first.status_code, 201, first.data)
        replay = self.client.post(
            "/api/v1/admin/taxonomy/work-groups/", body, format="json", **key
        )
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(WorkGroup.objects.filter(normalized_code="ag-12345").count(), 1)
        forged = self.client.post(
            "/api/v1/admin/taxonomy/work-groups/",
            {**body, "authorization_scope": str(self.org.id)},
            format="json",
            **self.key(),
        )
        self.assertEqual(forged.status_code, 400, forged.data)

    def test_taxonomy_patch_uses_version_and_forbids_parent_move(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/v1/admin/taxonomy/work-groups/{self.group.id}/",
            {
                "expected_version": getattr(self.group, "version", 1),
                "display_name": "New team name",
                "active": False,
            },
            format="json",
            **self.key(),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.group.refresh_from_db()
        self.assertEqual(self.group.display_name, "New team name")
        self.assertFalse(self.group.active)
        move = self.client.patch(
            f"/api/v1/admin/taxonomy/work-groups/{self.group.id}/",
            {"expected_version": response.data["version"], "parent_id": str(self.line.id)},
            format="json",
            **self.key(),
        )
        self.assertEqual(move.status_code, 400, move.data)

    def test_policy_revisions_activate_atomically_and_retire_prior(self):
        self.client.force_authenticate(self.admin)
        create_body = {
            "business_line_id": str(self.line.id),
            "audience": "registered_beta",
            "review_route": "platform",
            "effective_from": None,
            "effective_until": None,
            "reviewer_separation_required": True,
        }
        first = self.client.post(
            "/api/v1/admin/workspace-creation-policies/",
            create_body,
            format="json",
            **self.key(),
        )
        self.assertEqual(first.status_code, 201, first.data)
        activated = self.client.post(
            f"/api/v1/admin/workspace-creation-policies/{first.data['id']}/activate/",
            {"expected_policy_version": first.data["policy_version"]},
            format="json",
            **self.key(),
        )
        self.assertEqual(activated.status_code, 200, activated.data)
        self.assertEqual(activated.data["status"], "active")
        second = self.client.post(
            "/api/v1/admin/workspace-creation-policies/",
            create_body,
            format="json",
            **self.key(),
        )
        self.assertEqual(second.data["revision"], 2)
        activated_second = self.client.post(
            f"/api/v1/admin/workspace-creation-policies/{second.data['id']}/activate/",
            {"expected_policy_version": second.data["policy_version"]},
            format="json",
            **self.key(),
        )
        self.assertEqual(activated_second.status_code, 200, activated_second.data)
        self.assertEqual(
            WorkspaceCreationPolicy.objects.filter(
                business_line=self.line,
                status="active",
            ).count(),
            1,
        )
        self.assertEqual(
            WorkspaceCreationPolicy.objects.get(pk=first.data["id"]).status,
            "retired",
        )
