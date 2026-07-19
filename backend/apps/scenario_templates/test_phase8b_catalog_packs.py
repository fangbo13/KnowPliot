"""Phase 8B template catalog, revision, and isolated knowledge-pack tests."""

import uuid
from copy import deepcopy

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.knowledge.models import Document
from apps.spaces.models import (
    Organization,
    OrganizationMembership,
)
from apps.spaces.ownership import create_space_with_owner

from .models import (
    ScenarioTemplate,
    ScenarioTemplateApplication,
    ScenarioTemplateAsset,
    ScenarioTemplateRevision,
    TemplateCategory,
    TemplateTag,
)
from .contract import revision_snapshot


User = get_user_model()


class Phase8BBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="phase8b-admin",
            email="phase8b-admin@example.com",
            password="test",
        )
        self.org = Organization.objects.create(name="Phase 8B", slug="phase-8b")
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        self.client.force_authenticate(self.user)


class TemplateCatalogTest(Phase8BBase):
    def test_catalog_filters_tags_and_uses_explainable_popular_sort(self):
        category = TemplateCategory.objects.create(name="HR", slug="hr")
        tag = TemplateTag.objects.create(name="Policy", slug="policy")
        popular = ScenarioTemplate.objects.create(
            name="Popular",
            code="popular",
            organization=self.org,
            category=category,
            featured=False,
        )
        popular.tags.add(tag)
        recent = ScenarioTemplate.objects.create(
            name="Recent",
            code="recent",
            organization=self.org,
            category=category,
        )
        revision = ScenarioTemplateRevision.objects.create(
            template=popular,
            version=1,
            snapshot=revision_snapshot({
                "category_tree": [],
                "scenario_definitions": [],
                "quality_rubric": {},
                "workspace_defaults": {},
                "model_policy_refs": [],
            }),
            published_at=timezone.now(),
            created_by=self.user,
        )
        popular.current_revision = revision
        popular.save(update_fields=["current_revision", "updated_at"])
        ScenarioTemplateApplication.objects.create(
            template=popular,
            template_revision=revision,
            organization=self.org,
            created_by=self.user,
        )

        response = self.client.get(
            "/api/v1/templates/",
            {"category": "hr", "tags": "policy", "sort": "popular", "page": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(popular.id))
        self.assertEqual(response.data["results"][0]["category"]["slug"], "hr")
        self.assertEqual(response.data["results"][0]["tags"][0]["slug"], "policy")
        self.assertNotEqual(str(recent.id), response.data["results"][0]["id"])


class TemplateRevisionActionsTest(Phase8BBase):
    def test_diff_and_rollback_append_revision_without_mutating_history(self):
        template = ScenarioTemplate.objects.create(
            name="Rollback",
            code="rollback",
            description="first",
            organization=self.org,
            created_by=self.user,
        )
        first = ScenarioTemplateRevision.objects.create(
            template=template,
            version=1,
            snapshot=revision_snapshot({
                "category_tree": [],
                "scenario_definitions": [{"key": "first"}],
                "quality_rubric": {},
                "workspace_defaults": {},
                "model_policy_refs": [],
            }),
            published_at=timezone.now(),
            created_by=self.user,
        )
        second = ScenarioTemplateRevision.objects.create(
            template=template,
            version=2,
            snapshot=revision_snapshot({
                "category_tree": [],
                "scenario_definitions": [{"key": "second"}],
                "quality_rubric": {},
                "workspace_defaults": {},
                "model_policy_refs": [],
            }),
            created_by=self.user,
        )
        template.current_revision = first
        template.save(update_fields=["current_revision", "updated_at"])
        original_snapshots = {
            first.id: deepcopy(first.snapshot),
            second.id: deepcopy(second.snapshot),
        }

        diff = self.client.get(
            f"/api/v1/templates/{template.id}/diff/",
            {"from": 1, "to": 2},
        )
        rollback = self.client.post(
            f"/api/v1/templates/{template.id}/rollback/",
            {"revision": 1, "expected_template_version": 2},
            format="json",
        )

        self.assertEqual(diff.status_code, 200)
        self.assertIn("components", diff.data["changes"])
        self.assertEqual(rollback.status_code, 200)
        template.refresh_from_db()
        self.assertEqual(template.current_revision_id, first.id)
        self.assertEqual(template.revisions.first().version, 3)
        for revision_id, snapshot in original_snapshots.items():
            self.assertEqual(
                ScenarioTemplateRevision.objects.get(id=revision_id).snapshot,
                snapshot,
            )


class TemplateKnowledgePackTest(Phase8BBase):
    def make_document(self, org, title="Source"):
        space = create_space_with_owner(
            organization=org,
            owner=self.user,
            name=f"{title} Space",
            code=f"{org.slug}-{title.lower()}",
        )
        return Document.objects.create(
            space=space,
            title=title,
            file=SimpleUploadedFile(f"{title}.txt", b"knowledge pack content"),
            file_type="txt",
            file_size=22,
            uploaded_by=self.user,
            status="active",
        )

    def test_asset_attachment_and_document_copy_are_disabled(self):
        template = ScenarioTemplate.objects.create(
            name="Pack",
            code="pack",
            organization=self.org,
            created_by=self.user,
        )
        source = self.make_document(self.org)
        attach = self.client.post(
            f"/api/v1/templates/{template.id}/assets/",
            {"document": str(source.id)},
            format="json",
        )
        response = self.client.post(
            f"/api/v1/templates/{template.id}/create-space/",
            {"name": "Target", "code": "target-pack"},
            format="json",
        )

        self.assertEqual(attach.status_code, 409)
        self.assertEqual(attach.data["code"], "template_asset_attachment_disabled")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "template_revision_not_ready")
        self.assertFalse(ScenarioTemplateAsset.objects.exists())
        self.assertFalse(ScenarioTemplateApplication.objects.exists())
        self.assertEqual(Document.objects.filter(pk=source.pk).count(), 1)

    def test_cross_organization_document_cannot_be_attached(self):
        other = Organization.objects.create(name="Other", slug="other-phase8b")
        template = ScenarioTemplate.objects.create(
            name="Scoped",
            code="scoped-pack",
            organization=self.org,
            created_by=self.user,
        )
        foreign = self.make_document(other, "Foreign")

        response = self.client.post(
            f"/api/v1/templates/{template.id}/assets/",
            {"document": str(foreign.id)},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(ScenarioTemplateAsset.objects.filter(document=foreign).exists())

    def test_historical_asset_retry_is_disabled_without_resource_lookup(self):
        template = ScenarioTemplate.objects.create(
            name="Retry Pack",
            code="retry-pack",
            organization=self.org,
            created_by=self.user,
        )
        retried = self.client.post(
            f"/api/v1/templates/{template.id}/applications/{uuid.uuid4()}/retry-assets/",
            {},
            format="json",
        )

        self.assertEqual(retried.status_code, 503)
        self.assertEqual(retried.data["code"], "template_asset_copy_disabled")
        self.assertFalse(ScenarioTemplateAsset.objects.exists())
        self.assertFalse(ScenarioTemplateApplication.objects.exists())
