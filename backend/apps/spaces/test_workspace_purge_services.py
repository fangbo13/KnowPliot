"""Requirement tests for the fenced workspace purge lineage."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import Notification

from .governed import GovernedWorkflowError
from .deletion_registry import _blocker_queryset
from .models import (
    GovernedActionRequest,
    Organization,
    WorkspaceDeletionRequestDetail,
    WorkspaceLocatorReservation,
    WorkspacePurgeCheckpoint,
    WorkspacePurgeJob,
    WorkspaceTombstone,
)
from .ownership import create_space_with_owner
from .purge_services import (
    NON_DATABASE_STORES,
    acknowledge_purge_store,
    claim_purge_request,
    complete_database_purge,
    due_purge_request_ids,
    fail_purge_job,
    _terminalize_notifications,
)


class WorkspacePurgeServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="purge-owner",
            email="purge-owner@example.com",
            password="pw",
        )
        self.org = Organization.objects.create(name="Purge Org", slug="purge-org")
        self.space = create_space_with_owner(
            organization=self.org,
            owner=self.owner,
            name="Purge target",
            code="purge-target",
            visibility="private",
        )
        self.archived_at = timezone.now() - timedelta(days=31)
        self.space.status = "archived"
        self.space.archived_at = self.archived_at
        self.space.lifecycle_version = 2
        self.space.save(
            update_fields=["status", "archived_at", "lifecycle_version", "updated_at"]
        )
        self.locator = WorkspaceLocatorReservation.objects.get(live_space=self.space)
        self.manifest_digest = hashlib.sha256(b"purge-manifest-v1").hexdigest()
        self.manifest = {
            "ready": True,
            "version": 1,
            "registry_digest": hashlib.sha256(b"registry-v1").hexdigest(),
            "manifest_digest": self.manifest_digest,
            "resources": [],
            "blockers": [],
            "counts": {"eligible_content": 0, "retained_evidence": 0},
            "retention_dates": [],
        }
        self.request = GovernedActionRequest.objects.create(
            action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
            requester=self.owner,
            requester_uuid=self.owner.pk,
            reviewer=self.owner,
            reviewer_uuid=self.owner.pk,
            reviewed_at=timezone.now() - timedelta(days=8),
            scope_type="workspace",
            scope_uuid=self.space.pk,
            organization=self.org,
            target_space=self.space,
            target_space_uuid=self.space.pk,
            locator_reservation=self.locator,
            status=GovernedActionRequest.STATUS_SCHEDULED,
            idempotency_key=uuid.uuid4(),
            request_digest=hashlib.sha256(b"request").hexdigest(),
            request_version=2,
            impact_revision=1,
            impact_version=hashlib.sha256(b"impact").hexdigest(),
            scheduled_for=timezone.now() - timedelta(days=1),
        )
        self.detail = WorkspaceDeletionRequestDetail.objects.create(
            request=self.request,
            locator=self.locator.normalized_locator,
            expected_lifecycle_version=self.space.lifecycle_version,
            expected_ownership_version=self.space.ownership_version,
            expected_dependency_version=self.space.dependency_version,
            archived_at=self.archived_at,
            confirmed_at=timezone.now() - timedelta(days=8),
            purge_not_before=timezone.now() - timedelta(days=1),
            retention_policy_version=self.space.retention_policy_version,
            storage_manifest_version=1,
            storage_manifest_digest=self.manifest_digest,
            confirmation_digest=hashlib.sha256(
                self.locator.normalized_locator.encode("utf-8")
            ).hexdigest(),
        )
        self.manifest_patcher = patch(
            "apps.spaces.purge_services.build_deletion_manifest",
            return_value=self.manifest,
        )
        self.manifest_patcher.start()
        self.addCleanup(self.manifest_patcher.stop)

    def test_open_task_blockers_use_explicit_job_and_checkpoint_state_fields(self):
        job = WorkspacePurgeJob.objects.create(request=self.request)
        job_entry = SimpleNamespace(
            blocker_code="open_tasks",
            model_label="spaces.WorkspacePurgeJob",
        )
        self.assertTrue(
            _blocker_queryset(job_entry, WorkspacePurgeJob.objects.all())
            .filter(pk=job.pk)
            .exists()
        )
        job.state = WorkspacePurgeJob.STATE_COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["state", "completed_at"])
        self.assertFalse(
            _blocker_queryset(job_entry, WorkspacePurgeJob.objects.all()).exists()
        )

        checkpoint = WorkspacePurgeCheckpoint.objects.create(
            job=job,
            store_code="database",
            batch_key="manifest",
        )
        checkpoint_entry = SimpleNamespace(
            blocker_code="open_tasks",
            model_label="spaces.WorkspacePurgeCheckpoint",
        )
        self.assertTrue(
            _blocker_queryset(
                checkpoint_entry,
                WorkspacePurgeCheckpoint.objects.all(),
            ).exists()
        )
        checkpoint.status = WorkspacePurgeCheckpoint.STATUS_ACKED
        checkpoint.acknowledged_at = timezone.now()
        checkpoint.save(update_fields=["status", "acknowledged_at", "updated_at"])
        self.assertFalse(
            _blocker_queryset(
                checkpoint_entry,
                WorkspacePurgeCheckpoint.objects.all(),
            ).exists()
        )

    def claim(self):
        return claim_purge_request(request_id=self.request.pk)

    def ack_external_stores(self, lease):
        for store in NON_DATABASE_STORES:
            acknowledge_purge_store(
                job_id=lease.job_id,
                store_code=store,
                generation=lease.generation,
                fence_token=lease.fence_token,
                acknowledged_digest=lease.manifest_digest,
            )

    def test_claim_is_fenced_and_creates_one_tombstone_and_five_checkpoints(self):
        self.assertEqual(due_purge_request_ids(), [self.request.pk])
        lease = self.claim()
        self.request.refresh_from_db()
        self.locator.refresh_from_db()
        self.space.refresh_from_db()
        self.assertEqual(self.request.status, GovernedActionRequest.STATUS_EXECUTING)
        self.assertEqual(self.locator.state, WorkspaceLocatorReservation.STATE_TOMBSTONED)
        self.assertIsNone(self.locator.live_space_id)
        self.assertEqual(self.space.purge_fence_generation, lease.generation)
        self.assertEqual(WorkspaceTombstone.objects.count(), 1)
        self.assertEqual(
            set(
                WorkspacePurgeCheckpoint.objects.filter(job_id=lease.job_id).values_list(
                    "store_code", flat=True
                )
            ),
            {"blob", "search", "vector", "replay", "database"},
        )

    def test_wrong_fence_or_manifest_cannot_acknowledge_a_store(self):
        lease = self.claim()
        with self.assertRaises(GovernedWorkflowError) as wrong_fence:
            acknowledge_purge_store(
                job_id=lease.job_id,
                store_code="blob",
                generation=lease.generation,
                fence_token=uuid.uuid4(),
                acknowledged_digest=lease.manifest_digest,
            )
        self.assertEqual(wrong_fence.exception.code, "purge_fence_lost")
        with self.assertRaises(GovernedWorkflowError) as wrong_manifest:
            acknowledge_purge_store(
                job_id=lease.job_id,
                store_code="blob",
                generation=lease.generation,
                fence_token=lease.fence_token,
                acknowledged_digest="0" * 64,
            )
        self.assertEqual(wrong_manifest.exception.code, "manifest_mismatch")

    def test_failure_retries_the_same_job_with_a_new_generation(self):
        first = self.claim()
        failed = fail_purge_job(
            job_id=first.job_id,
            generation=first.generation,
            fence_token=first.fence_token,
            failure_code="replay_store_unavailable",
            store_code="replay",
        )
        self.assertEqual(failed["status"], GovernedActionRequest.STATUS_FAILED)
        second = self.claim()
        self.assertEqual(second.job_id, first.job_id)
        self.assertGreater(second.generation, first.generation)
        self.assertNotEqual(second.fence_token, first.fence_token)
        self.assertEqual(WorkspacePurgeJob.objects.count(), 1)

    def test_changed_lifecycle_invalidates_scheduled_request_durably(self):
        self.space.lifecycle_version += 1
        self.space.save(update_fields=["lifecycle_version", "updated_at"])
        with self.assertRaises(GovernedWorkflowError) as caught:
            self.claim()
        self.assertEqual(caught.exception.code, "impact_changed")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, GovernedActionRequest.STATUS_INVALIDATED)
        self.assertEqual(self.request.failure_code, "impact_changed")

    def test_notification_terminalization_preserves_resource_evidence(self):
        actioned_at = timezone.now() - timedelta(days=1)
        notification = Notification.objects.create(
            recipient=self.owner,
            type=Notification.TYPE_SYSTEM,
            title="Deletion action",
            body="historical body",
            link="/workspace/action",
            action_kind="workspace_deletion_confirm",
            resource_type="workspace",
            resource_uuid=self.space.pk,
            resource_version=7,
            allowed_actions=["confirm", "cancel"],
            action_state=Notification.ACTION_ACTIONED,
            deep_link="/workspace/action",
            actioned_at=actioned_at,
        )

        updated = _terminalize_notifications(
            resource_ids=set(),
            space_id=self.space.pk,
            now=timezone.now(),
        )

        self.assertEqual(updated, 1)
        notification.refresh_from_db()
        self.assertEqual(notification.action_kind, "resource_deleted")
        self.assertEqual(notification.action_state, "stale")
        self.assertEqual(notification.allowed_actions, [])
        self.assertEqual(notification.deep_link, "")
        self.assertEqual(notification.link, "")
        self.assertEqual(notification.resource_type, "workspace")
        self.assertEqual(notification.resource_uuid, self.space.pk)
        self.assertEqual(notification.resource_version, 7)
        self.assertEqual(notification.actioned_at, actioned_at)

    def test_database_completion_requires_all_external_acks_and_deletes_space_last(self):
        lease = self.claim()
        with self.assertRaises(GovernedWorkflowError) as incomplete:
            complete_database_purge(
                job_id=lease.job_id,
                generation=lease.generation,
                fence_token=lease.fence_token,
            )
        self.assertEqual(incomplete.exception.code, "store_checkpoint_incomplete")
        self.ack_external_stores(lease)
        with patch(
            "apps.spaces.purge_services._purge_registered_database_rows",
            return_value={"deleted": 0, "detached": 0, "notifications": 0},
        ):
            result = complete_database_purge(
                job_id=lease.job_id,
                generation=lease.generation,
                fence_token=lease.fence_token,
            )
        self.assertEqual(result["status"], GovernedActionRequest.STATUS_COMPLETED)
        self.assertFalse(type(self.space).objects.filter(pk=self.space.pk).exists())
        self.request.refresh_from_db()
        tombstone = WorkspaceTombstone.objects.get(pk=result["tombstone_id"])
        self.assertIsNone(self.request.target_space_id)
        self.assertIsNotNone(tombstone.purged_at)
        self.assertEqual(tombstone.final_manifest_digest, self.manifest_digest)
