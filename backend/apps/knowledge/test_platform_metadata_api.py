"""Requirement-level tests for the Platform Knowledge metadata boundary."""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.spaces.models import Organization
from apps.spaces.ownership import create_space_with_owner

from .models import Document, DocumentChunk


class PlatformKnowledgeMetadataApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.platform_user = User.objects.create_superuser(
            username="platform-knowledge",
            email="platform-knowledge@example.test",
            password="pw",
        )
        self.owner = User.objects.create_user(
            username="platform-knowledge-owner",
            email="platform-knowledge-owner@example.test",
            password="pw",
        )
        self.organization = Organization.objects.create(
            name="Platform Knowledge Org",
            slug="platform-knowledge-org",
        )
        self.space = create_space_with_owner(
            organization=self.organization,
            owner=self.owner,
            name="Platform Knowledge Space",
            code="platform-knowledge-space",
            visibility="private",
        )
        self.document = Document.objects.create(
            space=self.space,
            title="Duplicate safe title",
            file="documents/secret-storage-name.txt",
            file_type="txt",
            file_size=27,
            status="active",
            version=4,
            uploaded_by=self.owner,
            content_hash="f" * 64,
            chunk_count=1,
        )
        DocumentChunk.objects.create(
            document=self.document,
            space=self.space,
            content="TOP SECRET CHUNK CONTENT",
            chunk_index=0,
        )
        self.client = APIClient()

    def test_exact_platform_capability_returns_only_the_safe_metadata_allowlist(self):
        self.client.force_authenticate(self.platform_user)

        response = self.client.get("/api/v1/admin/documents/")

        self.assertEqual(response.status_code, 200, response.data)
        row = response.data["results"][0]
        self.assertEqual(
            set(row),
            {
                "id",
                "title",
                "status",
                "version",
                "organization",
                "business_line",
                "work_group",
                "space",
                "created_at",
                "updated_at",
            },
        )
        self.assertEqual(row["space"]["id"], str(self.space.id))
        serialized = str(response.data)
        for forbidden in (
            "secret-storage-name",
            "TOP SECRET",
            "content_hash",
            "file_url",
            "download_url",
            "storage_path",
            "signed_url",
            "f" * 64,
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

        content_attempt = self.client.get(
            f"/api/v1/documents/{self.document.id}/",
            HTTP_X_SPACE_ID=str(self.space.id),
        )
        self.assertNotEqual(content_attempt.status_code, 200)

    def test_workspace_owner_without_platform_capability_cannot_use_global_inventory(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get("/api/v1/admin/documents/")

        self.assertEqual(response.status_code, 403, response.data)

    def test_archived_workspace_and_legacy_orphan_are_metadata_visible_but_forged_filter_is_empty(self):
        orphan = Document.objects.create(
            space=None,
            title="Legacy orphan",
            file="documents/legacy.txt",
            file_type="txt",
            file_size=6,
            status="archived",
            uploaded_by=self.owner,
        )
        self.space.status = "archived"
        self.space.save(update_fields=["status", "updated_at"])
        self.client.force_authenticate(self.platform_user)

        response = self.client.get("/api/v1/admin/documents/")

        self.assertEqual(response.status_code, 200, response.data)
        by_id = {row["id"]: row for row in response.data["results"]}
        self.assertEqual(
            by_id[str(orphan.id)]["space"],
            {"id": None, "code": None, "name": "Unassigned"},
        )
        self.assertIn(str(self.document.id), by_id)

        forged = self.client.get(
            "/api/v1/admin/documents/",
            {"space_id": str(uuid.uuid4())},
        )
        self.assertEqual(forged.status_code, 200, forged.data)
        self.assertEqual(forged.data["results"], [])
