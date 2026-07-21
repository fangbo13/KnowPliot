"""Requirement-level tests for the v3 governed creation contract."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditLog

from .models import (
    BusinessLine,
    GovernedActionOutbox,
    GovernedActionRequest,
    KnowledgeSpace,
    OfficeLocation,
    Organization,
    SpaceMembership,
    WorkspaceCreationPolicy,
    WorkspaceLocatorReservation,
    WorkGroup,
    WriteIdempotencyRecord,
)


@override_settings(WORKSPACE_CREATION_APPROVAL=True)
class GovernedCreationApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.requester = User.objects.create_user(
            username="creation-requester",
            email="requester@example.com",
            password="pw",
            is_staff=True,
        )
        self.reviewer = User.objects.create_user(
            username="creation-reviewer",
            email="reviewer@example.com",
            password="pw",
            is_staff=True,
        )
        self.org = Organization.objects.create(name="Assurance", slug="assurance")
        self.line = BusinessLine.objects.create(
            organization=self.org,
            name="Audit",
            code="audit",
        )
        self.group = WorkGroup.objects.create(
            business_line=self.line,
            normalized_code="methodology",
            display_name="Methodology",
        )
        self.office = OfficeLocation.objects.create(
            organization=self.org,
            normalized_code="shanghai",
            display_name="Shanghai",
        )
        self.policy = WorkspaceCreationPolicy.objects.create(
            business_line=self.line,
            revision=1,
            status=WorkspaceCreationPolicy.STATUS_ACTIVE,
            audience=WorkspaceCreationPolicy.AUDIENCE_REGISTERED_BETA,
            review_route=WorkspaceCreationPolicy.ROUTE_PLATFORM,
            reviewer_separation_required=True,
            created_by=self.reviewer,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.requester)

    def payload(self, **overrides):
        body = {
            "name": "Assurance methodology",
            "code": "assurance-methodology",
            "purpose": "Bounded methodology knowledge",
            "visibility": "private",
            "business_line_id": str(self.line.id),
            "work_group_id": str(self.group.id),
            "office_location_ids": [str(self.office.id)],
            "template_version_id": None,
        }
        body.update(overrides)
        return body

    def submit(self, *, key=None, body=None, path="/api/v1/spaces/creation-requests/"):
        return self.client.post(
            path,
            body or self.payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()),
        )

    def test_submission_is_pending_and_never_creates_space(self):
        response = self.submit()
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(KnowledgeSpace.objects.count(), 0)
        request = GovernedActionRequest.objects.get(pk=response.data["request_id"])
        self.assertIsNone(request.target_space_id)
        self.assertEqual(request.locator_reservation.state, "request_reserved")
        self.assertEqual(request.create_detail.work_group_id, self.group.id)
        self.assertEqual(
            request.create_detail.office_location_ids,
            [str(self.office.id)],
        )
        self.assertTrue(request.outbox_events.exists())
        self.assertTrue(AuditLog.objects.filter(target_id=request.id).exists())

    def test_legacy_post_spaces_is_a_202_request_adapter(self):
        response = self.submit(path="/api/v1/spaces/")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(KnowledgeSpace.objects.count(), 0)
        self.assertEqual(GovernedActionRequest.objects.count(), 1)

    def test_same_key_replays_and_changed_digest_conflicts(self):
        key = uuid.uuid4()
        first = self.submit(key=key)
        second = self.submit(key=key)
        self.assertEqual(second.status_code, 202, second.data)
        self.assertEqual(second["Idempotency-Replayed"], "true")
        self.assertEqual(second.data, first.data)
        conflict = self.submit(key=key, body=self.payload(purpose="Another purpose"))
        self.assertEqual(conflict.status_code, 409, conflict.data)
        self.assertEqual(conflict.data["code"], "idempotency_key_reused")
        self.assertEqual(WriteIdempotencyRecord.objects.count(), 1)

    def test_unknown_fields_and_cross_scope_taxonomy_are_rejected(self):
        unknown = self.submit(body=self.payload(owner=str(self.reviewer.id)))
        self.assertEqual(unknown.status_code, 400, unknown.data)
        other_org = Organization.objects.create(name="Other", slug="other")
        other_office = OfficeLocation.objects.create(
            organization=other_org,
            normalized_code="other",
            display_name="Other",
        )
        hidden = self.submit(
            body=self.payload(office_location_ids=[str(other_office.id)])
        )
        self.assertEqual(hidden.status_code, 400, hidden.data)
        self.assertEqual(KnowledgeSpace.objects.count(), 0)

    def test_self_approval_is_forbidden_and_other_reviewer_is_atomic(self):
        submitted = self.submit()
        request_id = submitted.data["request_id"]
        impact = self.client.get(
            f"/api/v1/admin/governed-requests/{request_id}/impact/"
        )
        self.assertEqual(impact.status_code, 200, impact.data)
        self_approval = self.client.post(
            f"/api/v1/admin/governed-requests/{request_id}/approve/",
            {
                "expected_request_version": 1,
                "impact_version": impact.data["impact_version"],
                "acknowledge_requester_becomes_owner": True,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(self_approval.status_code, 409, self_approval.data)
        self.assertEqual(self_approval.data["code"], "self_approval_forbidden")
        self.assertEqual(KnowledgeSpace.objects.count(), 0)

        self.client.force_authenticate(self.reviewer)
        approved = self.client.post(
            f"/api/v1/admin/governed-requests/{request_id}/approve/",
            {
                "expected_request_version": 1,
                "impact_version": impact.data["impact_version"],
                "acknowledge_requester_becomes_owner": True,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(approved.status_code, 201, approved.data)
        request = GovernedActionRequest.objects.get(pk=request_id)
        space = KnowledgeSpace.objects.get(pk=approved.data["space"]["id"])
        self.assertEqual(request.status, "completed")
        self.assertEqual(space.owner, self.requester)
        self.assertEqual(space.classification_state, "complete")
        self.assertEqual(space.work_group, self.group)
        self.assertEqual(list(space.office_locations.all()), [self.office])
        self.assertEqual(
            SpaceMembership.objects.filter(
                space=space,
                user=self.requester,
                role="owner",
                status="active",
            ).count(),
            1,
        )
        self.assertFalse(SpaceMembership.objects.filter(space=space, user=self.reviewer).exists())
        locator = WorkspaceLocatorReservation.objects.get(pk=request.locator_reservation_id)
        self.assertEqual(locator.state, "live")
        self.assertEqual(locator.live_space, space)
        self.assertTrue(
            GovernedActionOutbox.objects.filter(
                request=request,
                event_type="workspace_create_approved",
            ).exists()
        )

    def test_cancel_releases_locator_without_creating_space(self):
        submitted = self.submit()
        cancelled = self.client.post(
            f"/api/v1/spaces/creation-requests/{submitted.data['request_id']}/cancel/",
            {"expected_request_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        request = GovernedActionRequest.objects.get(pk=submitted.data["request_id"])
        self.assertEqual(request.status, "cancelled")
        self.assertEqual(request.locator_reservation.state, "released")
        self.assertEqual(KnowledgeSpace.objects.count(), 0)


class GovernedCreationDisabledTests(TestCase):
    @override_settings(WORKSPACE_CREATION_APPROVAL=False)
    def test_disabled_legacy_route_never_falls_back_to_direct_create(self):
        user = get_user_model().objects.create_user(
            username="creation-disabled",
            email="disabled@example.com",
            password="pw",
            is_staff=True,
        )
        client = APIClient()
        client.force_authenticate(user)
        response = client.post(
            "/api/v1/spaces/",
            {"name": "Unsafe", "code": "unsafe"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 503, response.data)
        self.assertEqual(response.data["code"], "workspace_creation_disabled")
        self.assertEqual(KnowledgeSpace.objects.count(), 0)
