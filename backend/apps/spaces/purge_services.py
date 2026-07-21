"""Fenced, resumable workspace purge dispatcher and database finalizer.

The public deletion API only schedules work. These functions are worker-side
entry points: candidate discovery is unlocked, while every claim/finalization
re-acquires the governed graph and revalidates the frozen manifest.
"""

from __future__ import annotations

import hashlib
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, models, transaction
from django.utils import timezone

from .deletion_registry import build_deletion_manifest, registered_queryset
from .governed import (
    GovernedWorkflowError,
    durable_governed_transaction,
    enqueue_transition_outbox,
    record_transition_audit,
)
from .models import (
    GovernedActionRequest,
    GovernedActionOutbox,
    KnowledgeSpace,
    Organization,
    OwnershipTransfer,
    SpaceAccessCode,
    SpaceAccessRequest,
    SpaceInvitation,
    SpaceMembership,
    WorkspaceDeletionRequestDetail,
    WorkspaceLocatorReservation,
    WorkspacePurgeCheckpoint,
    WorkspacePurgeDependency,
    WorkspacePurgeJob,
    WorkspaceRetentionHold,
    WorkspaceTombstone,
)


PURGE_STORE_CODES = ("blob", "search", "vector", "replay", "database")
NON_DATABASE_STORES = PURGE_STORE_CODES[:-1]
DEFAULT_LEASE = timedelta(minutes=5)


@dataclass(frozen=True)
class PurgeLease:
    job_id: uuid.UUID
    request_id: uuid.UUID
    generation: int
    fence_token: uuid.UUID
    expires_at: object
    manifest_version: int
    manifest_digest: str


def due_purge_request_ids(*, now=None, limit: int = 50) -> list[uuid.UUID]:
    """Read candidate IDs without row locks, as required by the lock order."""

    now = now or timezone.now()
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    scheduled = models.Q(
        status=GovernedActionRequest.STATUS_SCHEDULED,
        scheduled_for__lte=now,
    )
    retryable = models.Q(
        status=GovernedActionRequest.STATUS_FAILED,
        purge_job__state=WorkspacePurgeJob.STATE_FAILED,
    )
    return list(
        GovernedActionRequest.objects.filter(
            scheduled | retryable,
            action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
        )
        .order_by("scheduled_for", "created_at", "pk")
        .values_list("pk", flat=True)[:limit]
    )


def _evaluate_locked(queryset):
    return list(
        queryset.select_for_update(of=("self",)).order_by("pk").values_list(
            "pk", flat=True
        )
    )


def _lock_dispatch_graph(*, request_id) -> tuple[GovernedActionRequest, KnowledgeSpace]:
    """Acquire the applicable §20.3 lock order for one purge claim."""

    snapshot = (
        GovernedActionRequest.objects.filter(
            pk=request_id,
            action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
        )
        .values(
            "requester_uuid",
            "reviewer_uuid",
            "organization_id",
            "business_line_id",
            "locator_reservation_id",
            "target_space_id",
        )
        .first()
    )
    if not snapshot or snapshot["target_space_id"] is None:
        raise GovernedWorkflowError("purge_request_not_claimable")

    User = get_user_model()
    actor_ids = sorted(
        {
            value
            for value in (snapshot["requester_uuid"], snapshot["reviewer_uuid"])
            if value is not None
        },
        key=str,
    )
    _evaluate_locked(User.objects.filter(pk__in=actor_ids))
    _evaluate_locked(Organization.objects.filter(pk=snapshot["organization_id"]))
    if snapshot["business_line_id"]:
        BusinessLine = apps.get_model("spaces", "BusinessLine")
        _evaluate_locked(BusinessLine.objects.filter(pk=snapshot["business_line_id"]))
    _evaluate_locked(
        WorkspaceLocatorReservation.objects.filter(
            pk=snapshot["locator_reservation_id"]
        )
    )
    space = (
        KnowledgeSpace.objects.select_for_update(of=("self",))
        .select_related("organization", "business_line")
        .filter(pk=snapshot["target_space_id"])
        .order_by("pk")
        .first()
    )
    if space is None:
        raise GovernedWorkflowError("purge_request_not_claimable")

    _evaluate_locked(SpaceMembership.objects.filter(space=space))
    _evaluate_locked(OwnershipTransfer.objects.filter(space=space))
    _evaluate_locked(SpaceAccessCode.objects.filter(space=space))
    for label in ("spaces.InviteCode", "spaces.SpaceEmailInvite"):
        model = apps.get_model(label)
        _evaluate_locked(model.objects.filter(space=space))
    _evaluate_locked(SpaceInvitation.objects.filter(space=space))
    _evaluate_locked(SpaceAccessRequest.objects.filter(space=space))

    row = (
        GovernedActionRequest.objects.select_for_update(of=("self",))
        .select_related("delete_detail", "locator_reservation")
        .filter(pk=request_id)
        .order_by("pk")
        .get()
    )
    _evaluate_locked(WorkspaceDeletionRequestDetail.objects.filter(request=row))

    for label in ("chat.ChatSession", "chat.ChatTurn"):
        model = apps.get_model(label)
        _evaluate_locked(model.objects.filter(space=space))

    entries = WorkspacePurgeDependency.objects.filter(
        active=True,
        required=True,
        registration_state=WorkspacePurgeDependency.STATE_READY,
        blocker_code__gt="",
    ).order_by("lock_order", "model_label", "space_field")
    for entry in entries:
        try:
            _evaluate_locked(registered_queryset(entry, space=space))
        except Exception as exc:
            raise GovernedWorkflowError("storage_manifest_unavailable") from exc

    _evaluate_locked(WorkspaceRetentionHold.objects.filter(space=space))
    _evaluate_locked(WorkspaceTombstone.objects.filter(original_space_uuid=space.pk))
    _evaluate_locked(WorkspacePurgeJob.objects.filter(request=row))
    job_ids = WorkspacePurgeJob.objects.filter(request=row).values_list("pk", flat=True)
    _evaluate_locked(WorkspacePurgeCheckpoint.objects.filter(job_id__in=job_ids))
    Notification = apps.get_model("notifications", "Notification")
    _evaluate_locked(
        Notification.objects.filter(
            resource_type="workspace", resource_uuid=space.pk
        )
    )
    _evaluate_locked(GovernedActionOutbox.objects.filter(request=row))
    return row, space


def _invalidate_scheduled_request(*, row, code: str) -> None:
    old = row.status
    updated = GovernedActionRequest.objects.filter(
        pk=row.pk,
        status=GovernedActionRequest.STATUS_SCHEDULED,
        request_version=row.request_version,
    ).update(
        status=GovernedActionRequest.STATUS_INVALIDATED,
        failure_code=code,
        completed_at=timezone.now(),
        request_version=models.F("request_version") + 1,
        updated_at=timezone.now(),
    )
    if updated != 1:
        raise GovernedWorkflowError("stale_request_version")
    row.refresh_from_db()
    record_transition_audit(
        actor=row.reviewer or row.requester,
        request=row,
        event="workspace_delete_invalidated",
        old_status=old,
        new_status=row.status,
        details={"failure_code": code},
    )
    enqueue_transition_outbox(
        request=row,
        event_type="workspace_delete_invalidated",
        transition_version=row.request_version,
        recipient=row.requester,
        payload={"request_id": str(row.pk), "status": row.status, "failure_code": code},
    )


def claim_purge_request(*, request_id, now=None, lease_duration=DEFAULT_LEASE) -> PurgeLease:
    """CAS-claim a scheduled or failed purge after full locked revalidation."""

    now = now or timezone.now()
    with durable_governed_transaction():
        row, space = _lock_dispatch_graph(request_id=request_id)
        if row.status == GovernedActionRequest.STATUS_SCHEDULED:
            if row.scheduled_for is None or row.scheduled_for > now:
                raise GovernedWorkflowError("retention_not_elapsed")
        elif row.status != GovernedActionRequest.STATUS_FAILED:
            raise GovernedWorkflowError("purge_request_not_claimable")

        detail = row.delete_detail
        current = build_deletion_manifest(space=space)
        if not current.get("ready"):
            if row.status == GovernedActionRequest.STATUS_SCHEDULED:
                _invalidate_scheduled_request(row=row, code="storage_manifest_unavailable")
            raise GovernedWorkflowError("storage_manifest_unavailable")
        blockers = current.get("blockers", [])
        if blockers:
            code = str(blockers[0].get("kind") or "storage_manifest_unavailable")
            if row.status == GovernedActionRequest.STATUS_SCHEDULED:
                _invalidate_scheduled_request(row=row, code=code)
            raise GovernedWorkflowError(code, details={"blockers": blockers})

        versions_changed = (
            space.status != "archived"
            or space.archived_at != detail.archived_at
            or space.lifecycle_version != detail.expected_lifecycle_version
            or space.ownership_version != detail.expected_ownership_version
            or space.dependency_version != detail.expected_dependency_version
            or space.retention_policy_version != detail.retention_policy_version
        )
        manifest_changed = (
            current["manifest_version"] if "manifest_version" in current else current["version"]
        ) != detail.storage_manifest_version or current["manifest_digest"] != detail.storage_manifest_digest
        if versions_changed or manifest_changed:
            code = "ownership_changed" if space.ownership_version != detail.expected_ownership_version else "impact_changed"
            if row.status == GovernedActionRequest.STATUS_SCHEDULED:
                _invalidate_scheduled_request(row=row, code=code)
            raise GovernedWorkflowError(code)

        retention_dates = [value for value in (detail.purge_not_before, space.retention_until) if value]
        if not retention_dates or max(retention_dates) > now:
            raise GovernedWorkflowError("retention_not_elapsed")

        locator = row.locator_reservation
        locator_digest = hashlib.sha256(
            unicodedata.normalize("NFC", locator.normalized_locator).encode("utf-8")
        ).hexdigest()
        tombstone, _ = WorkspaceTombstone.objects.get_or_create(
            original_space_uuid=space.pk,
            defaults={
                "organization_uuid": space.organization_id,
                "request": row,
                "locator_reservation": locator,
                "locator_digest": locator_digest,
                "normalized_locator": locator.normalized_locator,
                "archived_at": detail.archived_at,
                "manifest_version": current["version"],
                "final_manifest_digest": current["manifest_digest"],
            },
        )
        if tombstone.request_id != row.pk or tombstone.locator_reservation_id != locator.pk:
            raise GovernedWorkflowError("tombstone_conflict")
        locator.state = WorkspaceLocatorReservation.STATE_TOMBSTONED
        locator.live_space = None
        locator.active_request = None
        locator.tombstone = tombstone
        locator.save(
            update_fields=["state", "live_space", "active_request", "tombstone", "updated_at"]
        )

        old = row.status
        next_version = row.request_version + 1
        updated = GovernedActionRequest.objects.filter(
            pk=row.pk, status=old, request_version=row.request_version
        ).update(
            status=GovernedActionRequest.STATUS_EXECUTING,
            started_at=row.started_at or now,
            failure_code="",
            request_version=next_version,
            updated_at=now,
        )
        if updated != 1:
            raise GovernedWorkflowError("stale_request_version")
        row.refresh_from_db()

        job, created = WorkspacePurgeJob.objects.get_or_create(
            request=row,
            defaults={
                "state": WorkspacePurgeJob.STATE_RUNNING,
                "attempt": 1,
                "lease_generation": 1,
                "lease_expires_at": now + lease_duration,
                "request_version_snapshot": row.request_version,
                "lifecycle_version_snapshot": space.lifecycle_version,
                "ownership_version_snapshot": space.ownership_version,
                "impact_version_snapshot": row.impact_version,
                "retention_not_before": detail.purge_not_before,
                "manifest_version": current["version"],
                "manifest_digest": current["manifest_digest"],
                "started_at": now,
            },
        )
        if not created:
            if (
                job.state != WorkspacePurgeJob.STATE_FAILED
                or job.manifest_version != current["version"]
                or job.manifest_digest != current["manifest_digest"]
            ):
                raise GovernedWorkflowError("purge_job_conflict")
            job.state = WorkspacePurgeJob.STATE_RUNNING
            job.attempt += 1
            job.lease_generation += 1
            job.lease_expires_at = now + lease_duration
            job.session_fence_token = uuid.uuid4()
            job.request_version_snapshot = row.request_version
            job.failure_code = ""
            job.completed_at = None
            job.save(
                update_fields=[
                    "state",
                    "attempt",
                    "lease_generation",
                    "lease_expires_at",
                    "session_fence_token",
                    "request_version_snapshot",
                    "failure_code",
                    "completed_at",
                ]
            )

        for store in PURGE_STORE_CODES:
            checkpoint, _ = WorkspacePurgeCheckpoint.objects.get_or_create(
                job=job,
                store_code=store,
                batch_key="manifest",
                defaults={
                    "expected_digest": job.manifest_digest,
                    "lease_generation": job.lease_generation,
                },
            )
            if checkpoint.expected_digest != job.manifest_digest:
                raise GovernedWorkflowError("manifest_mismatch")
            if checkpoint.status != WorkspacePurgeCheckpoint.STATUS_ACKED:
                checkpoint.status = WorkspacePurgeCheckpoint.STATUS_PENDING
                checkpoint.lease_generation = job.lease_generation
                checkpoint.acknowledged_digest = ""
                checkpoint.acknowledged_at = None
                checkpoint.save(
                    update_fields=[
                        "status",
                        "lease_generation",
                        "acknowledged_digest",
                        "acknowledged_at",
                        "updated_at",
                    ]
                )
            elif checkpoint.lease_generation != job.lease_generation:
                checkpoint.lease_generation = job.lease_generation
                checkpoint.save(update_fields=["lease_generation", "updated_at"])

        space.storage_manifest_version = current["version"]
        space.storage_manifest_digest = current["manifest_digest"]
        space.storage_manifest_generated_at = now
        space.purge_fence_generation = job.lease_generation
        space.save(
            update_fields=[
                "storage_manifest_version",
                "storage_manifest_digest",
                "storage_manifest_generated_at",
                "purge_fence_generation",
                "updated_at",
            ]
        )
        detail.tombstone_uuid = tombstone.pk
        detail.purge_job_uuid = job.pk
        detail.save(update_fields=["tombstone_uuid", "purge_job_uuid"])

        record_transition_audit(
            actor=row.reviewer or row.requester,
            request=row,
            event="workspace_purge_started",
            old_status=old,
            new_status=row.status,
            details={"manifest_version": job.manifest_version},
        )
        enqueue_transition_outbox(
            request=row,
            event_type="workspace_purge_started",
            transition_version=row.request_version,
            recipient=row.requester,
            payload={"request_id": str(row.pk), "status": row.status},
        )
        return PurgeLease(
            job_id=job.pk,
            request_id=row.pk,
            generation=job.lease_generation,
            fence_token=job.session_fence_token,
            expires_at=job.lease_expires_at,
            manifest_version=job.manifest_version,
            manifest_digest=job.manifest_digest,
        )


def _lock_job_lineage(*, job_id) -> tuple[GovernedActionRequest, WorkspacePurgeJob]:
    snapshot = WorkspacePurgeJob.objects.filter(pk=job_id).values("request_id").first()
    if not snapshot:
        raise GovernedWorkflowError("purge_job_not_found", status_code=404)
    request_row = (
        GovernedActionRequest.objects.select_for_update(of=("self",))
        .filter(pk=snapshot["request_id"])
        .order_by("pk")
        .get()
    )
    job = (
        WorkspacePurgeJob.objects.select_for_update(of=("self",))
        .filter(pk=job_id)
        .order_by("pk")
        .get()
    )
    return request_row, job


def _verify_lease(
    job: WorkspacePurgeJob,
    *,
    generation: int,
    fence_token,
    now=None,
) -> None:
    now = now or timezone.now()
    try:
        parsed_token = uuid.UUID(str(fence_token))
    except (TypeError, ValueError, AttributeError) as exc:
        raise GovernedWorkflowError("purge_fence_lost") from exc
    if (
        job.state != WorkspacePurgeJob.STATE_RUNNING
        or job.lease_generation != generation
        or job.session_fence_token != parsed_token
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
    ):
        raise GovernedWorkflowError("purge_fence_lost")


def renew_purge_lease(
    *,
    job_id,
    generation: int,
    fence_token,
    now=None,
    lease_duration=DEFAULT_LEASE,
) -> PurgeLease:
    now = now or timezone.now()
    with transaction.atomic():
        request_row, job = _lock_job_lineage(job_id=job_id)
        _verify_lease(
            job,
            generation=generation,
            fence_token=fence_token,
            now=now,
        )
        job.lease_expires_at = now + lease_duration
        job.save(update_fields=["lease_expires_at"])
        return PurgeLease(
            job_id=job.pk,
            request_id=request_row.pk,
            generation=job.lease_generation,
            fence_token=job.session_fence_token,
            expires_at=job.lease_expires_at,
            manifest_version=job.manifest_version,
            manifest_digest=job.manifest_digest,
        )


def acknowledge_purge_store(
    *,
    job_id,
    store_code: str,
    generation: int,
    fence_token,
    acknowledged_digest: str,
    item_count: int = 0,
    byte_count: int = 0,
    last_cursor: str = "",
    now=None,
) -> dict:
    """Acknowledge one external store/batch under the active fenced lease."""

    if store_code not in NON_DATABASE_STORES:
        raise GovernedWorkflowError("invalid_purge_store", status_code=400)
    if (
        isinstance(item_count, bool)
        or not isinstance(item_count, int)
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or item_count < 0
        or byte_count < 0
    ):
        raise GovernedWorkflowError("invalid_purge_count", status_code=400)
    if not isinstance(last_cursor, str) or len(last_cursor) > 500:
        raise GovernedWorkflowError("invalid_purge_cursor", status_code=400)
    now = now or timezone.now()
    with transaction.atomic():
        _, job = _lock_job_lineage(job_id=job_id)
        _verify_lease(
            job,
            generation=generation,
            fence_token=fence_token,
            now=now,
        )
        checkpoint = (
            WorkspacePurgeCheckpoint.objects.select_for_update(of=("self",))
            .filter(job=job, store_code=store_code, batch_key="manifest")
            .order_by("pk")
            .get()
        )
        if checkpoint.lease_generation != generation:
            raise GovernedWorkflowError("purge_fence_lost")
        if acknowledged_digest != checkpoint.expected_digest:
            raise GovernedWorkflowError("manifest_mismatch")
        if checkpoint.status == WorkspacePurgeCheckpoint.STATUS_ACKED:
            if checkpoint.acknowledged_digest != acknowledged_digest:
                raise GovernedWorkflowError("manifest_mismatch")
        else:
            checkpoint.status = WorkspacePurgeCheckpoint.STATUS_ACKED
            checkpoint.acknowledged_digest = acknowledged_digest
            checkpoint.item_count = item_count
            checkpoint.byte_count = byte_count
            checkpoint.last_cursor = last_cursor
            checkpoint.attempts += 1
            checkpoint.acknowledged_at = now
            checkpoint.save(
                update_fields=[
                    "status",
                    "acknowledged_digest",
                    "item_count",
                    "byte_count",
                    "last_cursor",
                    "attempts",
                    "acknowledged_at",
                    "updated_at",
                ]
            )
        return {
            "job_id": str(job.pk),
            "store": store_code,
            "status": checkpoint.status,
            "generation": generation,
            "item_count": checkpoint.item_count,
            "byte_count": checkpoint.byte_count,
        }


def fail_purge_job(
    *,
    job_id,
    generation: int,
    fence_token,
    failure_code: str,
    store_code: str | None = None,
    now=None,
) -> dict:
    """Persist a retryable failure on the same request/job lineage."""

    if not isinstance(failure_code, str) or not failure_code or len(failure_code) > 80:
        raise GovernedWorkflowError("invalid_failure_code", status_code=400)
    if store_code is not None and store_code not in PURGE_STORE_CODES:
        raise GovernedWorkflowError("invalid_purge_store", status_code=400)
    now = now or timezone.now()
    with transaction.atomic():
        row, job = _lock_job_lineage(job_id=job_id)
        _verify_lease(
            job,
            generation=generation,
            fence_token=fence_token,
            now=now,
        )
        checkpoints = WorkspacePurgeCheckpoint.objects.select_for_update(
            of=("self",)
        ).filter(job=job)
        _evaluate_locked(checkpoints)
        if store_code:
            checkpoints.filter(
                store_code=store_code,
                status__in=(
                    WorkspacePurgeCheckpoint.STATUS_PENDING,
                    WorkspacePurgeCheckpoint.STATUS_RUNNING,
                ),
            ).update(
                status=WorkspacePurgeCheckpoint.STATUS_FAILED,
                attempts=models.F("attempts") + 1,
                lease_generation=generation,
                updated_at=now,
            )
        old = row.status
        updated = GovernedActionRequest.objects.filter(
            pk=row.pk,
            status=GovernedActionRequest.STATUS_EXECUTING,
            request_version=row.request_version,
        ).update(
            status=GovernedActionRequest.STATUS_FAILED,
            failure_code=failure_code,
            request_version=models.F("request_version") + 1,
            updated_at=now,
        )
        if updated != 1:
            raise GovernedWorkflowError("stale_request_version")
        job.state = WorkspacePurgeJob.STATE_FAILED
        job.failure_code = failure_code
        job.lease_expires_at = None
        job.save(update_fields=["state", "failure_code", "lease_expires_at"])
        row.refresh_from_db()
        record_transition_audit(
            actor=row.reviewer or row.requester,
            request=row,
            event="workspace_purge_failed",
            old_status=old,
            new_status=row.status,
            details={"failure_code": failure_code, "store": store_code or ""},
        )
        enqueue_transition_outbox(
            request=row,
            event_type="workspace_purge_failed",
            transition_version=row.request_version,
            recipient=row.requester,
            payload={
                "request_id": str(row.pk),
                "status": row.status,
                "failure_code": failure_code,
            },
        )
        return {
            "request_id": str(row.pk),
            "job_id": str(job.pk),
            "status": row.status,
            "failure_code": failure_code,
        }


_PURGE_CORE_MODELS = {
    "spaces.governedactionrequest",
    "spaces.workspacelocatorreservation",
    "spaces.workspacetombstone",
    "spaces.workspacepurgejob",
    "spaces.workspacepurgecheckpoint",
}


def _model_field(model, name: str):
    try:
        return model._meta.get_field(name)
    except Exception:
        for field in model._meta.concrete_fields:
            if getattr(field, "attname", None) == name:
                return field
    raise GovernedWorkflowError("purge_registry_invalid")


def _field_default(field, *, now):
    if field.is_relation:
        return None
    if isinstance(field, (models.CharField, models.TextField, models.FileField)):
        return ""
    if isinstance(field, models.JSONField):
        return field.get_default()
    if isinstance(field, models.BooleanField):
        return False
    if isinstance(field, models.DateTimeField) and field.name.endswith("scrubbed_at"):
        return now
    if field.null:
        return None
    return field.get_default()


def _snapshot_change(*, instance, field_name: str, space, tombstone, now):
    field = _model_field(instance.__class__, field_name)
    current = getattr(instance, field.attname)
    if current not in (None, ""):
        return None
    if field_name in {"space_uuid", "original_space_uuid", "target_space_uuid"}:
        return space.pk
    if field_name == "organization_uuid":
        return space.organization_id
    if field_name == "locator_digest":
        return tombstone.locator_digest
    if field_name in {"tombstone", "tombstone_id"}:
        return tombstone.pk
    if field_name.endswith("_uuid"):
        source_name = field_name[: -len("_uuid")]
        try:
            source_field = _model_field(instance.__class__, source_name)
        except GovernedWorkflowError:
            return None
        return getattr(instance, source_field.attname, None)
    if isinstance(field, models.DateTimeField) and field_name.endswith("scrubbed_at"):
        return now
    return None


def _detach_retained_rows(*, entry, queryset, space, tombstone, now) -> tuple[int, set]:
    model = queryset.model
    resource_ids: set = set()
    count = 0
    for instance in queryset.select_for_update(of=("self",)).order_by("pk"):
        resource_ids.add(instance.pk)
        changes = {}
        for field_name in entry.snapshot_fields or ():
            value = _snapshot_change(
                instance=instance,
                field_name=field_name,
                space=space,
                tombstone=tombstone,
                now=now,
            )
            if value is not None:
                field = _model_field(instance.__class__, field_name)
                changes[field.attname] = value
        for field_name in entry.scrub_fields or ():
            field = _model_field(instance.__class__, field_name)
            changes[field.attname] = _field_default(field, now=now)

        # Detach the exact registered direct nullable workspace FK. This also
        # covers nonstandard names such as User.default_space without ever
        # deleting the retained row. UUID snapshots and nested lookup paths are
        # deliberately not treated as live FKs.
        if "__" not in entry.space_field:
            try:
                registered_field = _model_field(model, entry.space_field)
            except GovernedWorkflowError:
                registered_field = None
            remote = getattr(
                getattr(registered_field, "remote_field", None), "model", None
            )
            if (
                registered_field is not None
                and remote is not None
                and remote._meta.label_lower == "spaces.knowledgespace"
                and registered_field.null
            ):
                changes[registered_field.attname] = None
        if changes:
            model._default_manager.filter(pk=instance.pk).update(**changes)
        count += 1
    return count, resource_ids


def _terminalize_notifications(*, resource_ids: set, space_id, now) -> int:
    Notification = apps.get_model("notifications", "Notification")
    normalized_ids = set()
    for value in resource_ids | {space_id}:
        try:
            normalized_ids.add(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            continue
    qs = Notification.objects.select_for_update(of=("self",)).filter(
        resource_uuid__in=normalized_ids
    )
    updates = {}
    field_names = {field.name for field in Notification._meta.concrete_fields}
    if "action_kind" in field_names:
        updates["action_kind"] = "resource_deleted"
    if "action_state" in field_names:
        updates["action_state"] = "stale"
    if "allowed_actions" in field_names:
        updates["allowed_actions"] = []
    if "deep_link" in field_names:
        updates["deep_link"] = ""
    if "link" in field_names:
        updates["link"] = ""
    return qs.update(**updates) if updates else 0


def _purge_registered_database_rows(*, space, tombstone, now) -> dict:
    deleted = 0
    detached = 0
    resource_ids: set = {space.pk}
    entries = WorkspacePurgeDependency.objects.filter(
        active=True,
        required=True,
        registration_state=WorkspacePurgeDependency.STATE_READY,
    ).order_by("purge_order", "model_label", "space_field")
    for entry in entries:
        label = entry.model_label.lower()
        if label in _PURGE_CORE_MODELS or label == "notifications.notification":
            continue
        queryset = registered_queryset(entry, space=space)
        resource_ids.update(queryset.values_list("pk", flat=True))
        if entry.disposition == WorkspacePurgeDependency.DISPOSITION_RETAINED:
            row_count, ids = _detach_retained_rows(
                entry=entry,
                queryset=queryset,
                space=space,
                tombstone=tombstone,
                now=now,
            )
            detached += row_count
            resource_ids.update(ids)
            continue
        row_count = queryset.count()
        if row_count:
            queryset.delete()
            deleted += row_count
    notifications = _terminalize_notifications(
        resource_ids=resource_ids,
        space_id=space.pk,
        now=now,
    )
    return {"deleted": deleted, "detached": detached, "notifications": notifications}


def _set_postgres_purge_fence(*, job: WorkspacePurgeJob) -> None:
    if connection.vendor != "postgresql":
        return
    fence = f"{job.session_fence_token}:{job.lease_generation}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('knowpilot.purge_fence', %s, true)", [fence])


def complete_database_purge(
    *,
    job_id,
    generation: int,
    fence_token,
    now=None,
) -> dict:
    """Delete the workspace last and complete one manifest lineage atomically."""

    now = now or timezone.now()
    with transaction.atomic():
        snapshot = WorkspacePurgeJob.objects.filter(pk=job_id).values(
            "request_id", "request__target_space_id"
        ).first()
        if not snapshot or snapshot["request__target_space_id"] is None:
            raise GovernedWorkflowError("purge_job_not_found", status_code=404)
        row, space = _lock_dispatch_graph(request_id=snapshot["request_id"])
        _, job = _lock_job_lineage(job_id=job_id)
        _verify_lease(
            job,
            generation=generation,
            fence_token=fence_token,
            now=now,
        )
        if row.status != GovernedActionRequest.STATUS_EXECUTING:
            raise GovernedWorkflowError("purge_request_not_claimable")
        if (
            job.request_version_snapshot != row.request_version
            or job.lifecycle_version_snapshot != space.lifecycle_version
            or job.ownership_version_snapshot != space.ownership_version
            or job.manifest_version != space.storage_manifest_version
            or job.manifest_digest != space.storage_manifest_digest
            or space.purge_fence_generation != generation
        ):
            raise GovernedWorkflowError("purge_fence_lost")

        current = build_deletion_manifest(space=space)
        if (
            not current.get("ready")
            or current.get("blockers")
            or current.get("version") != job.manifest_version
            or current.get("manifest_digest") != job.manifest_digest
        ):
            raise GovernedWorkflowError("manifest_mismatch")

        checkpoints = list(
            WorkspacePurgeCheckpoint.objects.select_for_update(of=("self",))
            .filter(job=job)
            .order_by("store_code", "batch_key")
        )
        by_store = {checkpoint.store_code: checkpoint for checkpoint in checkpoints}
        if set(by_store) != set(PURGE_STORE_CODES):
            raise GovernedWorkflowError("manifest_mismatch")
        for store in NON_DATABASE_STORES:
            checkpoint = by_store[store]
            if (
                checkpoint.status != WorkspacePurgeCheckpoint.STATUS_ACKED
                or checkpoint.expected_digest != job.manifest_digest
                or checkpoint.acknowledged_digest != job.manifest_digest
                or checkpoint.lease_generation != generation
            ):
                raise GovernedWorkflowError("store_checkpoint_incomplete")

        database_checkpoint = by_store["database"]
        if database_checkpoint.expected_digest != job.manifest_digest:
            raise GovernedWorkflowError("manifest_mismatch")
        database_checkpoint.status = WorkspacePurgeCheckpoint.STATUS_RUNNING
        database_checkpoint.lease_generation = generation
        database_checkpoint.attempts += 1
        database_checkpoint.save(
            update_fields=["status", "lease_generation", "attempts", "updated_at"]
        )
        _set_postgres_purge_fence(job=job)

        tombstone = (
            WorkspaceTombstone.objects.select_for_update(of=("self",))
            .filter(request=row, original_space_uuid=space.pk)
            .order_by("pk")
            .get()
        )
        result = _purge_registered_database_rows(
            space=space,
            tombstone=tombstone,
            now=now,
        )
        original_space_uuid = space.pk
        space.delete()

        database_checkpoint.status = WorkspacePurgeCheckpoint.STATUS_ACKED
        database_checkpoint.acknowledged_digest = job.manifest_digest
        database_checkpoint.item_count = result["deleted"] + result["detached"]
        database_checkpoint.acknowledged_at = now
        database_checkpoint.save(
            update_fields=[
                "status",
                "acknowledged_digest",
                "item_count",
                "acknowledged_at",
                "updated_at",
            ]
        )
        tombstone.purged_at = now
        tombstone.manifest_version = job.manifest_version
        tombstone.final_manifest_digest = job.manifest_digest
        tombstone.save(
            update_fields=["purged_at", "manifest_version", "final_manifest_digest"]
        )
        job.state = WorkspacePurgeJob.STATE_COMPLETED
        job.completed_at = now
        job.lease_expires_at = None
        job.failure_code = ""
        job.save(
            update_fields=["state", "completed_at", "lease_expires_at", "failure_code"]
        )

        old = row.status
        updated = GovernedActionRequest.objects.filter(
            pk=row.pk,
            status=GovernedActionRequest.STATUS_EXECUTING,
            request_version=row.request_version,
        ).update(
            status=GovernedActionRequest.STATUS_COMPLETED,
            result_uuid=tombstone.pk,
            completed_at=now,
            failure_code="",
            request_version=models.F("request_version") + 1,
            updated_at=now,
        )
        if updated != 1:
            raise GovernedWorkflowError("stale_request_version")
        row.refresh_from_db()
        record_transition_audit(
            actor=row.reviewer or row.requester,
            request=row,
            event="workspace_purge_completed",
            old_status=old,
            new_status=row.status,
            details={
                "space_uuid": str(original_space_uuid),
                "manifest_version": job.manifest_version,
                **result,
            },
        )
        enqueue_transition_outbox(
            request=row,
            event_type="workspace_purge_completed",
            transition_version=row.request_version,
            recipient=row.requester,
            payload={
                "request_id": str(row.pk),
                "status": row.status,
                "tombstone_id": str(tombstone.pk),
            },
        )
        return {
            "request_id": str(row.pk),
            "job_id": str(job.pk),
            "status": row.status,
            "tombstone_id": str(tombstone.pk),
            "manifest_digest": job.manifest_digest,
            **result,
        }


def _job_space_id(job_id):
    return WorkspacePurgeJob.objects.filter(pk=job_id).values_list(
        "request__target_space_id", flat=True
    ).first()


def execute_blob_store(*, lease: PurgeLease) -> dict:
    """Idempotently remove source blobs for the frozen workspace inventory."""

    space_id = _job_space_id(lease.job_id)
    if space_id is None:
        raise GovernedWorkflowError("purge_job_not_found", status_code=404)
    Document = apps.get_model("knowledge", "Document")
    rows = list(
        Document.objects.filter(space_id=space_id)
        .order_by("pk")
        .only("pk", "file", "file_size")
    )
    byte_count = 0
    try:
        for document in rows:
            byte_count += max(0, int(document.file_size or 0))
            name = getattr(document.file, "name", "")
            if name:
                document.file.storage.delete(name)
    except Exception as exc:
        raise GovernedWorkflowError("blob_store_failed") from exc
    return acknowledge_purge_store(
        job_id=lease.job_id,
        store_code="blob",
        generation=lease.generation,
        fence_token=lease.fence_token,
        acknowledged_digest=lease.manifest_digest,
        item_count=len(rows),
        byte_count=byte_count,
    )


def execute_search_store(*, lease: PurgeLease) -> dict:
    """Acknowledge lexical search isolation for the current DB-backed index."""

    space_id = _job_space_id(lease.job_id)
    if space_id is None:
        raise GovernedWorkflowError("purge_job_not_found", status_code=404)
    # SearchVector is stored on the registered PostgreSQL rows and archived
    # spaces are already authorization-excluded. Physical row removal remains
    # fenced by the database checkpoint; there is no second external index in
    # this deployment profile.
    Chunk = apps.get_model("knowledge", "DocumentChunk")
    count = Chunk.objects.filter(space_id=space_id).count()
    return acknowledge_purge_store(
        job_id=lease.job_id,
        store_code="search",
        generation=lease.generation,
        fence_token=lease.fence_token,
        acknowledged_digest=lease.manifest_digest,
        item_count=count,
    )


def execute_vector_store(*, lease: PurgeLease) -> dict:
    """Acknowledge pgvector isolation; physical rows delete in DB phase."""

    space_id = _job_space_id(lease.job_id)
    if space_id is None:
        raise GovernedWorkflowError("purge_job_not_found", status_code=404)
    Chunk = apps.get_model("knowledge", "DocumentChunk")
    count = Chunk.objects.filter(space_id=space_id).count()
    return acknowledge_purge_store(
        job_id=lease.job_id,
        store_code="vector",
        generation=lease.generation,
        fence_token=lease.fence_token,
        acknowledged_digest=lease.manifest_digest,
        item_count=count,
    )


def execute_replay_store(*, lease: PurgeLease) -> dict:
    """Delete every session lease and turn replay key for the workspace."""

    space_id = _job_space_id(lease.job_id)
    if space_id is None:
        raise GovernedWorkflowError("purge_job_not_found", status_code=404)
    Session = apps.get_model("chat", "ChatSession")
    Turn = apps.get_model("chat", "ChatTurn")
    session_ids = list(
        Session.objects.filter(space_id=space_id).order_by("pk").values_list("pk", flat=True)
    )
    turn_ids = list(
        Turn.objects.filter(space_id=space_id).order_by("pk").values_list("pk", flat=True)
    )
    from apps.chat.coordination import session_lease_key

    keys = [session_lease_key(value) for value in session_ids]
    for value in turn_ids:
        keys.extend(
            [f"chat:turn:{value}:events", f"chat:turn:{value}:seq"]
        )
    try:
        if keys:
            from apps.chat.coordination import create_redis_client

            client = create_redis_client()
            client.delete(*keys)
    except Exception as exc:
        raise GovernedWorkflowError("replay_store_failed") from exc
    return acknowledge_purge_store(
        job_id=lease.job_id,
        store_code="replay",
        generation=lease.generation,
        fence_token=lease.fence_token,
        acknowledged_digest=lease.manifest_digest,
        item_count=len(keys),
    )


def dispatch_purge_request(*, request_id) -> dict:
    """Run one complete purge attempt, persisting any store failure."""

    lease = claim_purge_request(request_id=request_id)
    active_store = None
    try:
        for active_store, handler in (
            ("blob", execute_blob_store),
            ("search", execute_search_store),
            ("vector", execute_vector_store),
            ("replay", execute_replay_store),
        ):
            handler(lease=lease)
        active_store = "database"
        return complete_database_purge(
            job_id=lease.job_id,
            generation=lease.generation,
            fence_token=lease.fence_token,
        )
    except GovernedWorkflowError as exc:
        if exc.code in {"purge_fence_lost", "purge_job_not_found"}:
            raise
        return fail_purge_job(
            job_id=lease.job_id,
            generation=lease.generation,
            fence_token=lease.fence_token,
            failure_code=(
                exc.code if len(exc.code) <= 80 else "workspace_purge_failed"
            ),
            store_code=active_store,
        )
    except Exception:
        return fail_purge_job(
            job_id=lease.job_id,
            generation=lease.generation,
            fence_token=lease.fence_token,
            failure_code="workspace_purge_failed",
            store_code=active_store,
        )


def dispatch_due_purges(*, limit: int = 50) -> list[dict]:
    results = []
    for request_id in due_purge_request_ids(limit=limit):
        try:
            results.append(dispatch_purge_request(request_id=request_id))
        except GovernedWorkflowError as exc:
            results.append(
                {
                    "request_id": str(request_id),
                    "status": "not_claimed",
                    "failure_code": exc.code,
                }
            )
    return results


__all__ = [
    "PurgeLease",
    "PURGE_STORE_CODES",
    "NON_DATABASE_STORES",
    "due_purge_request_ids",
    "claim_purge_request",
    "renew_purge_lease",
    "acknowledge_purge_store",
    "fail_purge_job",
    "complete_database_purge",
    "execute_blob_store",
    "execute_search_store",
    "execute_vector_store",
    "execute_replay_store",
    "dispatch_purge_request",
    "dispatch_due_purges",
]
