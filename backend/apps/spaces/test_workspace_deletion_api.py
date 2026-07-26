"""Requirement-level tests for the v3 archive and permanent-delete contract."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    GovernedActionRequest,
    Organization,
    SpaceMembership,
    WorkspaceDeletionRequestDetail,
    WorkspaceLocatorReservation,
    WriteIdempotencyRecord,
)
from .ownership import create_space_with_owner


def _ready_manifest(*, space):
    return {
        "ready": True,
        "version": 1,
        "registry_digest": hashlib.sha256(b"test-registry-v1").hexdigest(),
        "manifest_digest": hashlib.sha256(f"manifest:{space.id}".encode()).hexdigest(),
        "resources": [],
        "blockers": [],
        "counts": {
            "eligible_content": 0,
            "retained_evidence": 0,
        },
        "retention_dates": [],
    }


@override_settings(WORKSPACE_PERMANENT_DELETE=True)
class WorkspaceDeletionApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="delete-owner",
            email="delete-owner@example.com",
            password="pw",
        )
        self.platform_admin = User.objects.create_user(
            username="delete-platform",
            email="delete-platform@example.com",
            password="pw",
            is_staff=True,
            is_superuser=True,
        )
        self.org = Organization.objects.create(name="Assurance", slug="assurance")
        self.space = create_space_with_owner(
            organization=self.org,
            owner=self.owner,
            name="Deletion target",
            code="deletion-target",
            visibility="private",
        )
        self.locator = WorkspaceLocatorReservation.objects.get(live_space=self.space)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.registry_patcher = patch(
            "apps.spaces.deletion_services.build_deletion_manifest",
            side_effect=_ready_manifest,
        )
        self.registry_patcher.start()
        self.addCleanup(self.registry_patcher.stop)

    @property
    def impact_url(self):
        return f"/api/v1/spaces/{self.space.id}/deletion-impact/"

    @property
    def requests_url(self):
        return f"/api/v1/spaces/{self.space.id}/deletion-requests/"

    def archive(self):
        return self.client.post(
            f"/api/v1/spaces/{self.space.id}/archive/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

    def impact(self):
        return self.client.get(self.impact_url)

    def submit_request(self, impact, *, key=None, body=None):
        payload = body or {
            "impact_version": impact.data["impact_version"],
            "expected_lifecycle_version": impact.data["expected_lifecycle_version"],
            "expected_ownership_version": impact.data["expected_ownership_version"],
        }
        return self.client.post(
            self.requests_url,
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(key or uuid.uuid4()),
        )

    def create_pending_request(self):
        archived = self.archive()
        self.assertEqual(archived.status_code, 200, archived.data)
        impact = self.impact()
        self.assertEqual(impact.status_code, 200, impact.data)
        submitted = self.submit_request(impact)
        self.assertEqual(submitted.status_code, 202, submitted.data)
        return impact, submitted

    def test_platform_authority_does_not_substitute_for_owner(self):
        self.client.force_authenticate(self.platform_admin)
        response = self.client.get(self.impact_url)
        self.assertEqual(response.status_code, 404, response.data)
        self.client.force_authenticate(self.owner)
        response = self.impact()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["confirmation_phrase"], "assurance/deletion-target")

    def test_archive_increments_lifecycle_and_request_requires_archived_state(self):
        impact = self.impact()
        self.assertEqual(impact.status_code, 200, impact.data)
        unarchived = self.submit_request(impact)
        self.assertEqual(unarchived.status_code, 409, unarchived.data)
        self.assertEqual(unarchived.data["code"], "workspace_not_archived")

        archived = self.archive()
        self.assertEqual(archived.status_code, 200, archived.data)
        self.space.refresh_from_db()
        self.assertEqual(self.space.status, "archived")
        self.assertEqual(self.space.lifecycle_version, 2)

    def test_safe_failure_is_committed_and_replayed_after_outer_transaction(self):
        impact = self.impact()
        self.assertEqual(impact.status_code, 200, impact.data)
        key = uuid.uuid4()
        first = self.submit_request(impact, key=key)
        self.assertEqual(first.status_code, 409, first.data)
        self.assertEqual(first.data["code"], "workspace_not_archived")

        replay = self.submit_request(impact, key=key)
        self.assertEqual(replay.status_code, 409, replay.data)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(replay.data, first.data)
        operation = WriteIdempotencyRecord.objects.get(key=key)
        self.assertEqual(
            operation.disposition,
            WriteIdempotencyRecord.DISPOSITION_FAILED,
        )
        self.assertEqual(operation.failure_code, "workspace_not_archived")

    def test_submit_is_shape_strict_idempotent_and_persists_typed_detail(self):
        self.archive()
        impact = self.impact()
        key = uuid.uuid4()
        first = self.submit_request(impact, key=key)
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(first.data["status"], "pending")
        replay = self.submit_request(impact, key=key)
        self.assertEqual(replay.status_code, 202, replay.data)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(replay.data, first.data)

        row = GovernedActionRequest.objects.get(pk=first.data["request_id"])
        detail = WorkspaceDeletionRequestDetail.objects.get(request=row)
        self.assertEqual(row.target_space_uuid, self.space.id)
        self.assertEqual(row.locator_reservation, self.locator)
        self.assertEqual(detail.locator, "assurance/deletion-target")
        self.assertEqual(detail.expected_lifecycle_version, 2)
        self.assertEqual(WriteIdempotencyRecord.objects.count(), 1)

        unknown = self.submit_request(
            impact,
            body={
                "impact_version": impact.data["impact_version"],
                "expected_lifecycle_version": 2,
                "expected_ownership_version": 1,
                "purge_not_before": timezone.now().isoformat(),
            },
        )
        self.assertEqual(unknown.status_code, 400, unknown.data)

    def test_confirm_requires_exact_phrase_and_never_persists_plaintext(self):
        impact, submitted = self.create_pending_request()
        request_id = submitted.data["request_id"]
        url = f"/api/v1/spaces/{self.space.id}/deletion-requests/{request_id}/confirm/"
        base = {
            "expected_request_version": 1,
            "impact_version": impact.data["impact_version"],
            "expected_lifecycle_version": 2,
            "expected_ownership_version": 1,
            "acknowledge_permanent": True,
        }
        mismatch = self.client.post(
            url,
            {**base, "confirmation_phrase": "Assurance/deletion-target"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(mismatch.status_code, 409, mismatch.data)
        self.assertEqual(mismatch.data["code"], "confirmation_mismatch")

        confirmed_at = timezone.now()
        confirmed = self.client.post(
            url,
            {**base, "confirmation_phrase": "assurance/deletion-target"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(confirmed.status_code, 202, confirmed.data)
        self.assertEqual(confirmed.data["status"], "scheduled")
        self.assertGreaterEqual(
            timezone.datetime.fromisoformat(confirmed.data["purge_not_before"]),
            confirmed_at + timedelta(days=7),
        )
        row = GovernedActionRequest.objects.get(pk=request_id)
        self.assertEqual(row.status, GovernedActionRequest.STATUS_SCHEDULED)
        self.assertNotIn("assurance/deletion-target", str(row.__dict__))
        self.assertEqual(
            row.delete_detail.confirmation_digest,
            hashlib.sha256("assurance/deletion-target".encode()).hexdigest(),
        )

    def test_cancel_does_not_restore_and_restore_requires_no_live_request(self):
        _, submitted = self.create_pending_request()
        request_id = submitted.data["request_id"]
        blocked_restore = self.client.post(
            f"/api/v1/spaces/{self.space.id}/restore/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(blocked_restore.status_code, 409, blocked_restore.data)
        self.assertEqual(blocked_restore.data["code"], "deletion_request_active")

        cancelled = self.client.post(
            f"/api/v1/spaces/{self.space.id}/deletion-requests/{request_id}/cancel/",
            {"expected_request_version": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        self.assertEqual(cancelled.data["status"], "cancelled")
        self.space.refresh_from_db()
        self.assertEqual(self.space.status, "archived")

        restored = self.client.post(
            f"/api/v1/spaces/{self.space.id}/restore/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(restored.status_code, 200, restored.data)
        self.space.refresh_from_db()
        self.assertEqual(self.space.status, "active")
        self.assertEqual(self.space.lifecycle_version, 3)

    def test_status_is_non_disclosing_and_uses_owner_snapshot(self):
        _, submitted = self.create_pending_request()
        url = f"/api/v1/spaces/deletion-requests/{submitted.data['request_id']}/"
        self.client.force_authenticate(self.platform_admin)
        hidden = self.client.get(url)
        self.assertEqual(hidden.status_code, 404, hidden.data)
        self.client.force_authenticate(self.owner)
        visible = self.client.get(url)
        self.assertEqual(visible.status_code, 200, visible.data)
        self.assertEqual(visible.data["request_id"], submitted.data["request_id"])
        self.assertEqual(visible.data["status"], "pending")

    def _install_drifting_retained_manifest(self):
        """Swap the stable manifest mock for one whose retained-evidence
        resources drift on every call while the frozen ``manifest_digest``
        stays constant.

        This mirrors production, where append-only audit / outbox / notification
        lineage (all ``retained_evidence``) legitimately grows between impact
        issuance and submit/confirm. Such growth must NOT invalidate a still
        valid impact, exactly as ``build_deletion_manifest`` already guarantees
        for ``manifest_digest`` by excluding retained resources.
        """

        stable_digest = hashlib.sha256(f"manifest:{self.space.id}".encode()).hexdigest()
        registry_digest = hashlib.sha256(b"test-registry-v1").hexdigest()
        counter = {"n": 0}

        def _manifest(*, space):
            counter["n"] += 1
            return {
                "ready": True,
                "version": 1,
                "registry_digest": registry_digest,
                "manifest_digest": stable_digest,
                "resources": [
                    {
                        "model": "chat.modelinvocation",
                        "space_field": "space",
                        "disposition": "retained_evidence",
                        "schema_revision": 13,
                        "count": counter["n"],
                        "rows_digest": hashlib.sha256(
                            str(counter["n"]).encode()
                        ).hexdigest(),
                    }
                ],
                "blockers": [],
                "counts": {"eligible_content": 0, "retained_evidence": counter["n"]},
                "retention_dates": [],
            }

        drift = patch(
            "apps.spaces.deletion_services.build_deletion_manifest",
            side_effect=_manifest,
        )
        drift.start()
        self.addCleanup(drift.stop)

    def test_retained_evidence_growth_does_not_block_submit(self):
        # Regression: archiving an (empty) workspace and then submitting the
        # permanent-delete request must not fail with ``impact_changed`` merely
        # because retained-evidence lineage grew between the impact read and the
        # submit. The frozen ``manifest_digest`` is unchanged, so the impact is
        # still valid.
        self._install_drifting_retained_manifest()
        archived = self.archive()
        self.assertEqual(archived.status_code, 200, archived.data)
        impact = self.impact()
        self.assertEqual(impact.status_code, 200, impact.data)
        submitted = self.submit_request(impact)
        self.assertEqual(submitted.status_code, 202, submitted.data)
        self.assertEqual(submitted.data["status"], "pending")

    def test_retained_evidence_growth_does_not_block_confirm(self):
        # Regression: the confirm step recomputes the impact after the submit
        # itself enqueued outbox lineage (retained evidence). That growth must
        # not spuriously trip ``impact_changed`` on confirm.
        self._install_drifting_retained_manifest()
        archived = self.archive()
        self.assertEqual(archived.status_code, 200, archived.data)
        impact = self.impact()
        self.assertEqual(impact.status_code, 200, impact.data)
        submitted = self.submit_request(impact)
        self.assertEqual(submitted.status_code, 202, submitted.data)
        request_id = submitted.data["request_id"]
        confirmed = self.client.post(
            f"/api/v1/spaces/{self.space.id}/deletion-requests/{request_id}/confirm/",
            {
                "expected_request_version": 1,
                "impact_version": impact.data["impact_version"],
                "expected_lifecycle_version": impact.data["expected_lifecycle_version"],
                "expected_ownership_version": impact.data["expected_ownership_version"],
                "confirmation_phrase": "assurance/deletion-target",
                "acknowledge_permanent": True,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(confirmed.status_code, 202, confirmed.data)
        self.assertEqual(confirmed.data["status"], "scheduled")
