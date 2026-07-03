"""Phase 8B template catalog, revision, and isolated knowledge-pack tests."""

from copy import deepcopy
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.knowledge.models import Document, IngestionJob
from apps.spaces.models import (
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
)

from .models import (
    ScenarioTemplate,
    ScenarioTemplateApplication,
    ScenarioTemplateAsset,
    ScenarioTemplateRevision,
    TemplateCategory,
    TemplateTag,
)


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
        ScenarioTemplateApplication.objects.create(
            template=popular,
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
            snapshot={"description": "first", "template_name": "Rollback"},
            created_by=self.user,
        )
        second = ScenarioTemplateRevision.objects.create(
            template=template,
            version=2,
            snapshot={"description": "second", "template_name": "Rollback"},
            created_by=self.user,
        )
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
            {"revision": 1},
            format="json",
        )

        self.assertEqual(diff.status_code, 200)
        self.assertEqual(
            diff.data["changes"]["description"],
            {"from": "first", "to": "second"},
        )
        self.assertEqual(rollback.status_code, 200)
        template.refresh_from_db()
        self.assertEqual(template.description, "first")
        self.assertEqual(template.revisions.first().version, 3)
        for revision_id, snapshot in original_snapshots.items():
            self.assertEqual(
                ScenarioTemplateRevision.objects.get(id=revision_id).snapshot,
                snapshot,
            )


class TemplateKnowledgePackTest(Phase8BBase):
    def make_document(self, org, title="Source"):
        space = KnowledgeSpace.objects.create(
            organization=org,
            name=f"{title} Space",
            code=f"{org.slug}-{title.lower()}",
            created_by=self.user,
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

    def test_asset_is_physically_copied_and_has_independent_ingestion(self):
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
        def fake_enqueue(document, **kwargs):
            return IngestionJob.objects.create(
                document=document,
                space=document.space,
                requested_by=self.user,
                status="queued",
                celery_task_id="task-1",
            )

        with patch(
            "apps.scenario_templates.views.enqueue_document_ingestion",
            side_effect=fake_enqueue,
        ):
            response = self.client.post(
                f"/api/v1/templates/{template.id}/create-space/",
                {
                    "name": "Target",
                    "code": "target-pack",
                    "organization": str(self.org.id),
                },
                format="json",
            )

        self.assertEqual(attach.status_code, 201)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["asset_total"], 1)
        self.assertEqual(response.data["provisioning_status"], "processing")
        application = ScenarioTemplateApplication.objects.get(
            id=response.data["application_id"]
        )
        copied = application.asset_applications.get().target_document
        self.assertNotEqual(copied.id, source.id)
        self.assertEqual(copied.space_id, application.space_id)
        self.assertNotEqual(copied.file.name, source.file.name)
        self.assertFalse(copied.chunks.exists())

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

        self.assertIn(response.status_code, {403, 404})
        self.assertFalse(ScenarioTemplateAsset.objects.filter(document=foreign).exists())

    def test_partial_failure_keeps_space_and_retry_only_processes_failed_asset(self):
        template = ScenarioTemplate.objects.create(
            name="Retry Pack",
            code="retry-pack",
            organization=self.org,
            created_by=self.user,
        )
        good = self.make_document(self.org, "Good")
        bad = self.make_document(self.org, "Bad")
        for document in (good, bad):
            self.client.post(
                f"/api/v1/templates/{template.id}/assets/",
                {"document": str(document.id)},
                format="json",
            )

        calls = []

        def initial_enqueue(document, **kwargs):
            calls.append(document.title)
            if document.title == "Bad":
                raise RuntimeError("broker unavailable")
            return IngestionJob.objects.create(
                document=document,
                space=document.space,
                status="queued",
                celery_task_id="good-task",
            )

        with patch(
            "apps.scenario_templates.views.enqueue_document_ingestion",
            side_effect=initial_enqueue,
        ):
            created = self.client.post(
                f"/api/v1/templates/{template.id}/create-space/",
                {
                    "name": "Retry Target",
                    "code": "retry-target",
                    "organization": str(self.org.id),
                },
                format="json",
            )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["provisioning_status"], "partial_failure")
        application = ScenarioTemplateApplication.objects.get(
            id=created.data["application_id"]
        )
        self.assertTrue(application.space_id)
        self.assertEqual(application.space.documents.count(), 1)

        def retry_enqueue(document, **kwargs):
            calls.append(f"retry:{document.title}")
            return IngestionJob.objects.create(
                document=document,
                space=document.space,
                status="queued",
                celery_task_id="retry-task",
            )

        with patch(
            "apps.scenario_templates.views.enqueue_document_ingestion",
            side_effect=retry_enqueue,
        ):
            retried = self.client.post(
                f"/api/v1/templates/{template.id}/applications/{application.id}/retry-assets/",
                {},
                format="json",
            )

        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.data["provisioning_status"], "processing")
        self.assertEqual(calls.count("Good"), 1)
        self.assertEqual(calls.count("retry:Bad"), 1)
        self.assertNotIn("retry:Good", calls)
        self.assertEqual(application.space.documents.count(), 2)
