"""Requirement-level tests for the SPEC-v3 template clone contract."""

from __future__ import annotations

import uuid
from copy import deepcopy
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, connection, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.spaces.creation_services import (
    approve_creation_request,
    submit_creation_request,
)
from apps.spaces.models import (
    BusinessLine,
    OfficeLocation,
    Organization,
    WorkGroup,
    WorkspaceCreationPolicy,
)

from .contract import normalize_components, revision_snapshot, snapshot_hash
from .models import (
    ScenarioTemplate,
    ScenarioTemplateApplication,
    ScenarioTemplateAsset,
    ScenarioTemplateRevision,
    TemplateAssetApplication,
)


def safe_components(*, label="baseline"):
    return {
        "category_tree": [{"key": "policy", "label": label}],
        "scenario_definitions": [
            {"key": "ask", "prompt": f"Answer from {label} policy."}
        ],
        "quality_rubric": {"required_citations": True},
        "workspace_defaults": {
            "default_language": "zh-CN",
            "default_visibility": "private",
        },
        "model_policy_refs": ["policy-stable-id"],
    }


class TemplateComponentContractTests(SimpleTestCase):
    def test_hash_is_deterministic_and_excluded_data_keys_are_rejected(self):
        first = revision_snapshot(safe_components())
        reordered = {
            "model_policy_refs": ["policy-stable-id"],
            "workspace_defaults": {
                "default_visibility": "private",
                "default_language": "zh-CN",
            },
            "quality_rubric": {"required_citations": True},
            "scenario_definitions": [
                {"prompt": "Answer from baseline policy.", "key": "ask"}
            ],
            "category_tree": [{"label": "baseline", "key": "policy"}],
        }

        self.assertEqual(snapshot_hash(first), snapshot_hash(revision_snapshot(reordered)))
        with self.assertRaises(DjangoValidationError):
            normalize_components(
                {
                    **safe_components(),
                    "workspace_defaults": {"documents": [str(uuid.uuid4())]},
                }
            )
        with self.assertRaises(DjangoValidationError):
            normalize_components({**safe_components(), "members": []})


@override_settings(TEMPLATE_ASSET_COPY_ENABLED=False)
class TemplateRevisionApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="template-v3-admin",
            email="template-v3-admin@example.test",
            password="pw",
        )
        self.org = Organization.objects.create(name="Template V3", slug="template-v3")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def make_template(self, *, code="v3-template"):
        return ScenarioTemplate.objects.create(
            name="V3 Template",
            code=code,
            organization=self.org,
            created_by=self.admin,
        )

    def publish(self, template, *, version=1, label="published"):
        revision = ScenarioTemplateRevision.objects.create(
            template=template,
            version=version,
            snapshot=revision_snapshot(safe_components(label=label)),
            published_at=timezone.now(),
            created_by=self.admin,
        )
        template.current_revision = revision
        template.save(update_fields=["current_revision", "updated_at"])
        return revision

    def test_canonical_template_create_shape_starts_with_unpublished_draft(self):
        response = self.client.post(
            "/api/v1/templates/",
            {
                "scope_type": "organization",
                "scope_id": str(self.org.id),
                "key": "canonical-template",
                "display_name": "Canonical Template",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        template = ScenarioTemplate.objects.get(code="canonical-template")
        revision = template.revisions.get()
        self.assertEqual(template.organization_id, self.org.id)
        self.assertIsNone(template.current_revision_id)
        self.assertIsNone(revision.published_at)
        self.assertRegex(revision.snapshot_hash, r"^[0-9a-f]{64}$")

    def test_create_preview_activate_and_published_row_immutability(self):
        template = self.make_template()
        created = self.client.post(
            f"/api/v1/templates/{template.id}/revisions/",
            {"expected_template_version": 0, "components": safe_components()},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.assertEqual(created.status_code, 201, created.data)
        self.assertRegex(created.data["snapshot_hash"], r"^[0-9a-f]{64}$")
        self.assertIsNone(created.data["published_at"])
        preview = self.client.get(
            f"/api/v1/templates/{template.id}/revisions/{created.data['id']}/preview/"
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertIn("documents", preview.data["excluded_components"])
        self.assertNotIn("assets", repr(preview.data).lower())

        activated = self.client.post(
            f"/api/v1/templates/{template.id}/revisions/{created.data['id']}/activate/",
            {
                "expected_template_version": 1,
                "expected_revision_hash": created.data["snapshot_hash"],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(activated.status_code, 200, activated.data)
        template.refresh_from_db()
        revision = ScenarioTemplateRevision.objects.get(pk=created.data["id"])
        self.assertEqual(template.current_revision_id, revision.id)
        self.assertIsNotNone(revision.published_at)

        revision.snapshot = revision_snapshot(safe_components(label="mutated"))
        with self.assertRaises(DjangoValidationError):
            revision.save()
        with self.assertRaises(DjangoValidationError):
            revision.delete()

    def test_update_rollback_and_clone_append_drafts_without_moving_current(self):
        template = self.make_template(code="source-template")
        published = self.publish(template, label="source")
        original = deepcopy(published.snapshot)

        updated = self.client.patch(
            f"/api/v1/templates/{template.id}/",
            {"description": "metadata update"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        template.refresh_from_db()
        self.assertEqual(template.current_revision_id, published.id)
        self.assertEqual(template.revisions.count(), 2)

        missing_version = self.client.post(
            f"/api/v1/templates/{template.id}/rollback/",
            {"revision": 1},
            format="json",
        )
        self.assertEqual(missing_version.status_code, 400, missing_version.data)
        rolled_back = self.client.post(
            f"/api/v1/templates/{template.id}/rollback/",
            {"revision": 1, "expected_template_version": 2},
            format="json",
        )
        self.assertEqual(rolled_back.status_code, 200, rolled_back.data)
        template.refresh_from_db()
        published.refresh_from_db()
        self.assertEqual(template.current_revision_id, published.id)
        self.assertEqual(published.snapshot, original)
        self.assertEqual(template.revisions.order_by("-version").first().version, 3)

        cloned = self.client.post(
            f"/api/v1/templates/{template.id}/clone/",
            {
                "name": "Safe Clone",
                "code": "safe-clone",
                "organization": str(self.org.id),
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(cloned.status_code, 201, cloned.data)
        clone = ScenarioTemplate.objects.get(code="safe-clone")
        clone_revision = clone.revisions.get()
        self.assertIsNone(clone.current_revision_id)
        self.assertEqual(clone_revision.snapshot_hash, published.snapshot_hash)
        self.assertFalse(clone.assets.exists())

    def test_asset_attach_and_retry_are_fail_closed(self):
        template = self.make_template(code="asset-compatibility")
        attach = self.client.post(
            f"/api/v1/templates/{template.id}/assets/",
            {"document": str(uuid.uuid4())},
            format="json",
        )
        retry = self.client.post(
            f"/api/v1/templates/{template.id}/applications/{uuid.uuid4()}/retry-assets/",
            {},
            format="json",
        )

        self.assertEqual(attach.status_code, 409, attach.data)
        self.assertEqual(attach.data["code"], "template_asset_attachment_disabled")
        self.assertEqual(retry.status_code, 503, retry.data)
        self.assertEqual(retry.data["code"], "template_asset_copy_disabled")
        self.assertFalse(ScenarioTemplateAsset.objects.exists())
        self.assertFalse(TemplateAssetApplication.objects.exists())

    @patch("apps.spaces.creation_services.submit_creation_request")
    def test_create_space_adapter_pins_current_not_latest_draft(self, submit):
        submit.return_value = {"request_id": str(uuid.uuid4()), "status": "pending"}
        template = self.make_template(code="pin-current")
        current = self.publish(template, label="current")
        ScenarioTemplateRevision.objects.create(
            template=template,
            version=2,
            snapshot=revision_snapshot(safe_components(label="unpublished-draft")),
            created_by=self.admin,
        )

        response = self.client.post(
            f"/api/v1/templates/{template.id}/create-space/",
            {
                "name": "Requested Space",
                "code": "requested-space",
                "business_line_id": str(uuid.uuid4()),
                "work_group_id": str(uuid.uuid4()),
                "office_location_ids": [str(uuid.uuid4())],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(
            submit.call_args.kwargs["payload"]["template_version_id"],
            str(current.id),
        )


@override_settings(TEMPLATE_ASSET_COPY_ENABLED=False)
class GovernedTemplatePinTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.requester = User.objects.create_user(
            username="template-pin-requester",
            email="template-pin-requester@example.test",
            password="pw",
        )
        self.reviewer = User.objects.create_user(
            username="template-pin-reviewer",
            email="template-pin-reviewer@example.test",
            password="pw",
            is_staff=True,
        )
        self.org = Organization.objects.create(name="Pinned Org", slug="pinned-org")
        self.line = BusinessLine.objects.create(
            organization=self.org,
            name="Pinned Line",
            code="pinned-line",
        )
        self.group = WorkGroup.objects.create(
            business_line=self.line,
            normalized_code="pinned-group",
            display_name="Pinned Group",
        )
        self.office = OfficeLocation.objects.create(
            organization=self.org,
            normalized_code="pinned-office",
            display_name="Pinned Office",
        )
        WorkspaceCreationPolicy.objects.create(
            business_line=self.line,
            revision=1,
            status=WorkspaceCreationPolicy.STATUS_ACTIVE,
            audience=WorkspaceCreationPolicy.AUDIENCE_REGISTERED_BETA,
            review_route=WorkspaceCreationPolicy.ROUTE_PLATFORM,
            reviewer_separation_required=True,
            created_by=self.reviewer,
        )
        self.template = ScenarioTemplate.objects.create(
            name="Pinned Template",
            code="pinned-template",
            organization=self.org,
            created_by=self.reviewer,
        )
        self.pinned = ScenarioTemplateRevision.objects.create(
            template=self.template,
            version=1,
            snapshot=revision_snapshot(safe_components(label="pinned")),
            published_at=timezone.now(),
            created_by=self.reviewer,
        )
        self.template.current_revision = self.pinned
        self.template.save(update_fields=["current_revision", "updated_at"])

    def test_approval_uses_exact_submitted_revision_without_copying_content(self):
        submitted = submit_creation_request(
            actor=self.requester,
            idempotency_key=uuid.uuid4(),
            payload={
                "name": "Pinned Workspace",
                "code": "pinned-workspace",
                "purpose": "Use one immutable revision",
                "visibility": "private",
                "business_line_id": str(self.line.id),
                "work_group_id": str(self.group.id),
                "office_location_ids": [str(self.office.id)],
                "template_version_id": str(self.pinned.id),
            },
        )
        application_draft = ScenarioTemplateRevision.objects.create(
            template=self.template,
            version=2,
            snapshot=revision_snapshot(safe_components(label="later")),
            published_at=timezone.now(),
            created_by=self.reviewer,
        )
        self.template.current_revision = application_draft
        self.template.save(update_fields=["current_revision", "updated_at"])

        from apps.spaces.models import GovernedActionRequest

        request_row = GovernedActionRequest.objects.get(pk=submitted["request_id"])
        approved = approve_creation_request(
            reviewer=self.reviewer,
            request_id=request_row.id,
            expected_version=request_row.request_version,
            impact_version=request_row.impact_version,
            acknowledge_requester_becomes_owner=True,
            idempotency_key=uuid.uuid4(),
        )

        application = ScenarioTemplateApplication.objects.get(
            space_id=approved["space"]["id"]
        )
        self.assertEqual(application.template_revision_id, self.pinned.id)
        self.assertEqual(application.asset_total, 0)
        self.assertEqual(application.task_ids, [])
        self.assertFalse(application.asset_applications.exists())
        self.assertEqual(
            application.template_snapshot["revision_hash"],
            self.pinned.snapshot_hash,
        )


@skipUnless(connection.vendor == "postgresql", "PostgreSQL trigger evidence only")
class PublishedRevisionPostgreSQLGuardTests(TestCase):
    def test_database_rejects_queryset_update_and_delete_of_published_row(self):
        template = ScenarioTemplate.objects.create(
            name="PG immutable",
            code="pg-immutable-template",
        )
        revision = ScenarioTemplateRevision.objects.create(
            template=template,
            version=1,
            snapshot=revision_snapshot(safe_components()),
            published_at=timezone.now(),
        )

        with self.assertRaises(DatabaseError), transaction.atomic():
            ScenarioTemplateRevision.objects.filter(pk=revision.pk).update(
                change_note="bypass"
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            ScenarioTemplateRevision.objects.filter(pk=revision.pk).delete()
