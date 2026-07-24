"""Owner-only archive and permanent workspace deletion services."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .deletion_registry import build_deletion_manifest
from .governed import (
    GovernedWorkflowError,
    complete_operation_record,
    digest_payload,
    durable_governed_transaction,
    enqueue_transition_outbox,
    operation_record,
    record_transition_audit,
    replay_response,
    safe_impact,
)
from .models import (
    GovernedActionRequest,
    KnowledgeSpace,
    Organization,
    SpaceMembership,
    WorkspaceDeletionRequestDetail,
    WorkspaceLocatorReservation,
)


DELETE_SUBMIT_FIELDS = frozenset(
    {"impact_version", "expected_lifecycle_version", "expected_ownership_version"}
)
DELETE_CONFIRM_FIELDS = frozenset(
    {
        "expected_request_version",
        "impact_version",
        "expected_lifecycle_version",
        "expected_ownership_version",
        "confirmation_phrase",
        "acknowledge_permanent",
    }
)
DELETE_CANCEL_FIELDS = frozenset({"expected_request_version"})
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_IMPACT_TTL_SECONDS = 5 * 60
_ARCHIVE_RETENTION = timedelta(days=30)
_CONFIRM_RETENTION = timedelta(days=7)


def _feature_enabled() -> bool:
    return bool(getattr(settings, "WORKSPACE_PERMANENT_DELETE", False))


def _require_feature() -> None:
    if not _feature_enabled():
        raise GovernedWorkflowError(
            "workspace_permanent_delete_disabled",
            "Permanent workspace deletion is disabled.",
            status_code=503,
        )


def reject_unknown_fields(payload: Any, allowed: frozenset[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError("Expected a JSON object.")
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValidationError({"unknown_fields": unknown})
    return payload


def _positive_version(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError({field: "Must be a positive integer."})
    return value


def _impact_digest(payload: dict[str, Any]) -> str:
    value = payload.get("impact_version")
    if not isinstance(value, str) or not _HEX_64.fullmatch(value):
        raise ValidationError({"impact_version": "Must be 64 lower-case hex characters."})
    return value


def _impact_cache_key(*, actor_id, space_id, impact_version: str) -> str:
    return f"workspace-delete-impact:{actor_id}:{space_id}:{impact_version}"


def _preflight_space(*, actor, space_id) -> KnowledgeSpace:
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise NotFound("Space not found.")
    try:
        space = KnowledgeSpace.objects.select_related("organization", "business_line").get(
            pk=space_id
        )
    except KnowledgeSpace.DoesNotExist as exc:
        raise NotFound("Space not found.") from exc
    # Platform admins (superusers / RBAC 'admin' role) may manage any workspace.
    from .permissions import is_platform_admin
    if is_platform_admin(actor):
        return space
    if space.owner_id != actor.pk:
        raise NotFound("Space not found.")
    membership = SpaceMembership.objects.filter(
        space_id=space.pk,
        user_id=actor.pk,
        role=SpaceMembership.ROLE_OWNER,
        status="active",
        expires_at__isnull=True,
    ).exists()
    if not membership:
        raise NotFound("Space not found.")
    return space


def _lock_user(actor):
    User = get_user_model()
    try:
        user = (
            User.objects.select_for_update(of=("self",))
            .filter(pk=actor.pk)
            .order_by("pk")
            .get()
        )
    except User.DoesNotExist as exc:
        raise NotFound("Space not found.") from exc
    if not user.is_active:
        raise NotFound("Space not found.")
    return user


def _lock_space_graph(*, actor, preflight: KnowledgeSpace) -> tuple[KnowledgeSpace, WorkspaceLocatorReservation]:
    # User and operation-idempotency rows are locked by callers before this
    # helper.  The remaining prefix follows §20.3: organization, locator,
    # space, then membership.
    (
        Organization.objects.select_for_update(of=("self",))
        .filter(pk=preflight.organization_id)
        .order_by("pk")
        .get()
    )
    try:
        locator = (
            WorkspaceLocatorReservation.objects.select_for_update(of=("self",))
            .filter(live_space_id=preflight.pk)
            .order_by("pk")
            .get()
        )
    except WorkspaceLocatorReservation.DoesNotExist as exc:
        raise GovernedWorkflowError("storage_manifest_unavailable") from exc
    space = (
        KnowledgeSpace.objects.select_for_update(of=("self",))
        .select_related("organization", "business_line")
        .filter(pk=preflight.pk)
        .order_by("pk")
        .get()
    )
    from .permissions import is_platform_admin
    is_admin = is_platform_admin(actor)
    if not is_admin:
        membership = (
            SpaceMembership.objects.select_for_update(of=("self",))
            .filter(
                space_id=space.pk,
                user_id=actor.pk,
                role=SpaceMembership.ROLE_OWNER,
                status="active",
                expires_at__isnull=True,
            )
            .order_by("pk")
            .first()
        )
        if space.owner_id != actor.pk or membership is None:
            raise NotFound("Space not found.")
    return space, locator


def _parse_retention_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _impact_for_space(*, space: KnowledgeSpace, actor, issued_at=None) -> dict[str, Any]:
    issued_at = issued_at or timezone.now()
    manifest = build_deletion_manifest(space=space)
    resources = [
        {
            "kind": "workspace_versions",
            "id": str(space.pk),
            "status": space.status,
            "lifecycle_version": space.lifecycle_version,
            "ownership_version": space.ownership_version,
            "dependency_version": space.dependency_version,
            "archived_at": space.archived_at,
        },
        {
            "kind": "storage_manifest",
            "id": manifest.get("manifest_digest", ""),
            "status": "ready" if manifest.get("ready") else "not_ready",
            "version": manifest.get("version", 0),
            "resources": manifest.get("resources", []),
        },
    ]
    for blocker in manifest.get("blockers", []):
        resources.append(
            {
                "kind": blocker.get("kind", "storage_manifest_unavailable"),
                "id": blocker.get("id", ""),
                "status": blocker.get("status", "active"),
            }
        )
    impact_version, snapshot = safe_impact(
        action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
        resources=resources,
        policy_version={
            "archive_days": _ARCHIVE_RETENTION.days,
            "confirmation_days": _CONFIRM_RETENTION.days,
            "retention_policy_version": space.retention_policy_version,
            "manifest_version": manifest.get("version", 0),
            "registry_digest": manifest.get("registry_digest", ""),
        },
        dependency_version=space.dependency_version,
    )
    expires_at = issued_at + timedelta(seconds=_IMPACT_TTL_SECONDS)
    earliest = None
    if space.archived_at:
        earliest = space.archived_at + _ARCHIVE_RETENTION
    active_request = (
        GovernedActionRequest.objects.filter(
            target_space=space,
            action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
            status__in=GovernedActionRequest.DELETE_LIVE_STATUSES,
        )
        .order_by("created_at", "pk")
        .first()
    )
    return {
        "space_id": str(space.pk),
        "lifecycle_status": space.status,
        "expected_lifecycle_version": space.lifecycle_version,
        "expected_ownership_version": space.ownership_version,
        "confirmation_phrase": (
            space.locator_reservation.normalized_locator
            if hasattr(space, "locator_reservation")
            else f"{space.organization.slug}/{space.code}"
        ),
        "impact_version": impact_version,
        "impact_expires_at": expires_at.isoformat(),
        "impact": snapshot,
        "counts": manifest.get("counts", {}),
        "blockers": manifest.get("blockers", []),
        "earliest_purge_at": earliest.isoformat() if earliest else None,
        "manifest_digest": manifest.get("manifest_digest", ""),
        "manifest_version": manifest.get("version", 0),
        "retention_dates": manifest.get("retention_dates", []),
        "active_request": _request_body(active_request) if active_request else None,
    }


def get_deletion_impact(*, actor, space_id) -> dict[str, Any]:
    _require_feature()
    space = _preflight_space(actor=actor, space_id=space_id)
    body = _impact_for_space(space=space, actor=actor)
    cache.set(
        _impact_cache_key(
            actor_id=actor.pk,
            space_id=space.pk,
            impact_version=body["impact_version"],
        ),
        {
            "impact_expires_at": body["impact_expires_at"],
            "lifecycle_version": body["expected_lifecycle_version"],
            "ownership_version": body["expected_ownership_version"],
        },
        timeout=_IMPACT_TTL_SECONDS,
    )
    return body


def _raise_first_blocker(impact: dict[str, Any]) -> None:
    blockers = sorted(
        impact.get("blockers", []), key=lambda item: (str(item.get("kind")), str(item.get("id")))
    )
    if blockers:
        blocker = blockers[0]
        raise GovernedWorkflowError(
            str(blocker.get("kind") or "storage_manifest_unavailable"),
            details={"blockers": blockers},
        )


def _request_body(row: GovernedActionRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "request_id": str(row.pk),
        "status": row.status,
        "request_version": row.request_version,
        "status_url": f"/spaces/deletion-requests/{row.pk}/",
    }
    if row.expires_at:
        body["expires_at"] = row.expires_at.isoformat()
    if row.scheduled_for:
        body["purge_not_before"] = row.scheduled_for.isoformat()
    if row.failure_code:
        body["failure_code"] = row.failure_code
    return body


def submit_deletion_request(*, actor, space_id, payload: dict[str, Any], idempotency_key: uuid.UUID):
    _require_feature()
    payload = reject_unknown_fields(payload, DELETE_SUBMIT_FIELDS)
    supplied_impact = _impact_digest(payload)
    expected_lifecycle = _positive_version(payload, "expected_lifecycle_version")
    expected_ownership = _positive_version(payload, "expected_ownership_version")
    preflight = _preflight_space(actor=actor, space_id=space_id)
    request_digest = digest_payload(
        {
            "action": "workspace_permanent_delete.submit",
            "actor_uuid": actor.pk,
            "space_uuid": preflight.pk,
            "impact_version": supplied_impact,
            "expected_lifecycle_version": expected_lifecycle,
            "expected_ownership_version": expected_ownership,
        }
    )
    with durable_governed_transaction():
        actor = _lock_user(actor)
        with operation_record(
            actor=actor,
            operation_code="workspace_permanent_delete.submit",
            key=idempotency_key,
            request_digest=request_digest,
            target_uuid=preflight.pk,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            space, locator = _lock_space_graph(actor=actor, preflight=preflight)
            if space.status != "archived" or not space.archived_at:
                raise GovernedWorkflowError("workspace_not_archived")
            if space.lifecycle_version != expected_lifecycle:
                raise GovernedWorkflowError(
                    "impact_changed", details={"current_version": space.lifecycle_version}
                )
            if space.ownership_version != expected_ownership:
                raise GovernedWorkflowError("ownership_changed")
            current = _impact_for_space(space=space, actor=actor)
            cached = cache.get(
                _impact_cache_key(
                    actor_id=actor.pk,
                    space_id=space.pk,
                    impact_version=supplied_impact,
                )
            )
            if (
                cached is None
                or supplied_impact != current["impact_version"]
                or cached.get("lifecycle_version") != space.lifecycle_version
                or cached.get("ownership_version") != space.ownership_version
            ):
                raise GovernedWorkflowError(
                    "impact_changed",
                    details={
                        "current_version": space.lifecycle_version,
                        "impact_version": current["impact_version"],
                        "impact_expires_at": current["impact_expires_at"],
                        "impact": current["impact"],
                    },
                )
            _raise_first_blocker(current)
            if GovernedActionRequest.objects.filter(
                target_space=space,
                action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
                status__in=GovernedActionRequest.DELETE_LIVE_STATUSES,
            ).exists():
                raise GovernedWorkflowError("deletion_already_pending")
            try:
                row = GovernedActionRequest.objects.create(
                    action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
                    requester=actor,
                    requester_uuid=actor.pk,
                    scope_type="workspace",
                    scope_uuid=space.pk,
                    organization=space.organization,
                    business_line=space.business_line,
                    target_space=space,
                    target_space_uuid=space.pk,
                    locator_reservation=locator,
                    status=GovernedActionRequest.STATUS_PENDING,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                    request_version=1,
                    impact_revision=1,
                    impact_version=current["impact_version"],
                    impact_expires_at=timezone.now() + timedelta(seconds=_IMPACT_TTL_SECONDS),
                    impact_snapshot=current["impact"],
                    expires_at=timezone.now() + timedelta(days=30),
                )
            except IntegrityError as exc:
                raise GovernedWorkflowError("deletion_already_pending") from exc
            WorkspaceDeletionRequestDetail.objects.create(
                request=row,
                locator=current["confirmation_phrase"],
                expected_lifecycle_version=space.lifecycle_version,
                expected_ownership_version=space.ownership_version,
                expected_dependency_version=space.dependency_version,
                archived_at=space.archived_at,
                retention_policy_version=space.retention_policy_version,
                storage_manifest_version=current["manifest_version"],
                storage_manifest_digest=current["manifest_digest"],
            )
            record_transition_audit(
                actor=actor,
                request=row,
                event="workspace_delete_submitted",
                old_status=None,
                new_status=row.status,
                details={"space_id": str(space.pk)},
            )
            enqueue_transition_outbox(
                request=row,
                event_type="workspace_delete_submitted",
                transition_version=row.request_version,
                recipient=actor,
                payload={"request_id": str(row.pk), "status": row.status},
            )
            body = _request_body(row)
            complete_operation_record(operation, status_code=202, body=body, result_reference=row.pk)
            return body


def _preflight_request(*, actor, space_id, request_id) -> tuple[KnowledgeSpace, GovernedActionRequest]:
    space = _preflight_space(actor=actor, space_id=space_id)
    try:
        row = GovernedActionRequest.objects.select_related("delete_detail").get(
            pk=request_id,
            action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
            target_space_uuid=space.pk,
        )
    except GovernedActionRequest.DoesNotExist as exc:
        raise NotFound("Request not found.") from exc
    return space, row


def confirm_deletion_request(*, actor, space_id, request_id, payload: dict[str, Any], idempotency_key: uuid.UUID):
    _require_feature()
    payload = reject_unknown_fields(payload, DELETE_CONFIRM_FIELDS)
    expected_request = _positive_version(payload, "expected_request_version")
    supplied_impact = _impact_digest(payload)
    expected_lifecycle = _positive_version(payload, "expected_lifecycle_version")
    expected_ownership = _positive_version(payload, "expected_ownership_version")
    phrase = payload.get("confirmation_phrase")
    if not isinstance(phrase, str) or len(phrase) > 180:
        raise ValidationError({"confirmation_phrase": "Must be a string of at most 180 characters."})
    phrase = unicodedata.normalize("NFC", phrase)
    if payload.get("acknowledge_permanent") is not True:
        raise ValidationError({"acknowledge_permanent": "Must be true."})
    preflight, request_row = _preflight_request(
        actor=actor, space_id=space_id, request_id=request_id
    )
    request_digest = digest_payload(
        {
            "action": "workspace_permanent_delete.confirm",
            "actor_uuid": actor.pk,
            "request_uuid": request_row.pk,
            "expected_request_version": expected_request,
            "impact_version": supplied_impact,
            "expected_lifecycle_version": expected_lifecycle,
            "expected_ownership_version": expected_ownership,
            "confirmation_phrase": phrase,
            "acknowledge_permanent": True,
        }
    )
    with durable_governed_transaction():
        actor = _lock_user(actor)
        with operation_record(
            actor=actor,
            operation_code="workspace_permanent_delete.confirm",
            key=idempotency_key,
            request_digest=request_digest,
            target_uuid=preflight.pk,
            request_uuid=request_row.pk,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            space, _ = _lock_space_graph(actor=actor, preflight=preflight)
            row = (
                GovernedActionRequest.objects.select_for_update(of=("self",))
                .select_related("delete_detail")
                .filter(pk=request_row.pk)
                .order_by("pk")
                .get()
            )
            if row.status != GovernedActionRequest.STATUS_PENDING:
                raise GovernedWorkflowError("request_already_resolved")
            if row.request_version != expected_request:
                raise GovernedWorkflowError(
                    "stale_request_version", details={"current_version": row.request_version}
                )
            detail = row.delete_detail
            if (
                row.requester_uuid != actor.pk
                or space.ownership_version != expected_ownership
                or detail.expected_ownership_version != expected_ownership
            ):
                raise GovernedWorkflowError("ownership_changed")
            if (
                space.lifecycle_version != expected_lifecycle
                or detail.expected_lifecycle_version != expected_lifecycle
                or detail.expected_dependency_version != space.dependency_version
            ):
                raise GovernedWorkflowError("impact_changed")
            current = _impact_for_space(space=space, actor=actor)
            if (
                supplied_impact != row.impact_version
                or supplied_impact != current["impact_version"]
                or row.impact_expires_at is None
                or row.impact_expires_at <= timezone.now()
            ):
                raise GovernedWorkflowError(
                    "impact_changed",
                    details={
                        "current_version": row.request_version,
                        "impact_revision": row.impact_revision,
                        "impact_version": current["impact_version"],
                        "impact_expires_at": current["impact_expires_at"],
                        "impact": current["impact"],
                    },
                )
            _raise_first_blocker(current)
            if phrase != detail.locator:
                raise GovernedWorkflowError("confirmation_mismatch")
            now = timezone.now()
            retention_dates = [detail.archived_at + _ARCHIVE_RETENTION, now + _CONFIRM_RETENTION]
            retention_dates.extend(
                date
                for date in (_parse_retention_date(value) for value in current.get("retention_dates", []))
                if date is not None
            )
            purge_not_before = max(retention_dates)
            old = row.status
            row.status = GovernedActionRequest.STATUS_SCHEDULED
            row.reviewer = actor
            row.reviewer_uuid = actor.pk
            row.reviewed_at = now
            row.scheduled_for = purge_not_before
            row.request_version += 1
            row.save(
                update_fields=[
                    "status",
                    "reviewer",
                    "reviewer_uuid",
                    "reviewed_at",
                    "scheduled_for",
                    "request_version",
                    "updated_at",
                ]
            )
            detail.purge_not_before = purge_not_before
            detail.confirmed_at = now
            detail.confirmation_digest = hashlib.sha256(phrase.encode("utf-8")).hexdigest()
            detail.save(
                update_fields=[
                    "purge_not_before",
                    "confirmed_at",
                    "confirmation_digest",
                ]
            )
            record_transition_audit(
                actor=actor,
                request=row,
                event="workspace_delete_scheduled",
                old_status=old,
                new_status=row.status,
                details={"purge_not_before": purge_not_before.isoformat()},
            )
            enqueue_transition_outbox(
                request=row,
                event_type="workspace_delete_scheduled",
                transition_version=row.request_version,
                recipient=actor,
                payload={
                    "request_id": str(row.pk),
                    "status": row.status,
                    "purge_not_before": purge_not_before.isoformat(),
                },
            )
            body = _request_body(row)
            complete_operation_record(operation, status_code=202, body=body, result_reference=row.pk)
            return body


def cancel_deletion_request(*, actor, space_id, request_id, payload: dict[str, Any], idempotency_key: uuid.UUID):
    payload = reject_unknown_fields(payload, DELETE_CANCEL_FIELDS)
    expected_request = _positive_version(payload, "expected_request_version")
    preflight, request_row = _preflight_request(
        actor=actor, space_id=space_id, request_id=request_id
    )
    request_digest = digest_payload(
        {
            "action": "workspace_permanent_delete.cancel",
            "actor_uuid": actor.pk,
            "request_uuid": request_row.pk,
            "expected_request_version": expected_request,
        }
    )
    with durable_governed_transaction():
        actor = _lock_user(actor)
        with operation_record(
            actor=actor,
            operation_code="workspace_permanent_delete.cancel",
            key=idempotency_key,
            request_digest=request_digest,
            target_uuid=preflight.pk,
            request_uuid=request_row.pk,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            _lock_space_graph(actor=actor, preflight=preflight)
            row = (
                GovernedActionRequest.objects.select_for_update(of=("self",))
                .filter(pk=request_row.pk)
                .order_by("pk")
                .get()
            )
            if row.status in (
                GovernedActionRequest.STATUS_EXECUTING,
                GovernedActionRequest.STATUS_FAILED,
                GovernedActionRequest.STATUS_COMPLETED,
            ):
                raise GovernedWorkflowError("purge_already_started")
            if row.status not in (
                GovernedActionRequest.STATUS_PENDING,
                GovernedActionRequest.STATUS_SCHEDULED,
            ):
                raise GovernedWorkflowError("request_already_resolved")
            if row.request_version != expected_request:
                raise GovernedWorkflowError(
                    "stale_request_version", details={"current_version": row.request_version}
                )
            old = row.status
            row.status = GovernedActionRequest.STATUS_CANCELLED
            row.completed_at = timezone.now()
            row.request_version += 1
            row.save(
                update_fields=["status", "completed_at", "request_version", "updated_at"]
            )
            record_transition_audit(
                actor=actor,
                request=row,
                event="workspace_delete_cancelled",
                old_status=old,
                new_status=row.status,
            )
            enqueue_transition_outbox(
                request=row,
                event_type="workspace_delete_cancelled",
                transition_version=row.request_version,
                recipient=actor,
                payload={"request_id": str(row.pk), "status": row.status},
            )
            body = _request_body(row)
            complete_operation_record(operation, status_code=200, body=body, result_reference=row.pk)
            return body


def get_deletion_request_status(*, actor, request_id) -> dict[str, Any]:
    try:
        row = (
            GovernedActionRequest.objects.select_related(
                "target_space", "delete_detail", "purge_job"
            )
            .prefetch_related("purge_job__checkpoints")
            .get(
                pk=request_id,
                action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
            )
        )
    except GovernedActionRequest.DoesNotExist as exc:
        raise NotFound("Request not found.") from exc
    if row.target_space_id:
        if row.target_space.owner_id != actor.pk:
            raise NotFound("Request not found.")
    elif actor.pk not in {row.requester_uuid, row.reviewer_uuid}:
        raise NotFound("Request not found.")
    body = _request_body(row)
    try:
        job = row.purge_job
    except (AttributeError, ObjectDoesNotExist):
        job = None
    if job is not None:
        body["purge"] = {
            "state": job.state,
            "attempt": job.attempt,
            "failure_code": job.failure_code or None,
            "stores": [
                {
                    "store": checkpoint.store_code,
                    "status": checkpoint.status,
                    "item_count": checkpoint.item_count,
                    "byte_count": checkpoint.byte_count,
                }
                for checkpoint in job.checkpoints.order_by("store_code", "batch_key")
            ],
        }
    return body


def archive_workspace(*, actor, space_id) -> KnowledgeSpace:
    preflight = _preflight_space(actor=actor, space_id=space_id)
    with transaction.atomic():
        actor = _lock_user(actor)
        space, _ = _lock_space_graph(actor=actor, preflight=preflight)
        if space.status == "archived":
            return space
        space.status = "archived"
        space.archived_at = timezone.now()
        space.lifecycle_version += 1
        space.save(
            update_fields=["status", "archived_at", "lifecycle_version", "updated_at"]
        )
        _record_lifecycle_audit(actor=actor, space=space, event="space_archived")
        return space


def restore_workspace(*, actor, space_id) -> KnowledgeSpace:
    preflight = _preflight_space(actor=actor, space_id=space_id)
    with transaction.atomic():
        actor = _lock_user(actor)
        space, _ = _lock_space_graph(actor=actor, preflight=preflight)
        if GovernedActionRequest.objects.filter(
            target_space=space,
            action_type=GovernedActionRequest.ACTION_WORKSPACE_DELETE,
            status__in=GovernedActionRequest.DELETE_LIVE_STATUSES,
        ).exists():
            raise GovernedWorkflowError("deletion_request_active")
        if space.status == "active":
            return space
        space.status = "active"
        space.archived_at = None
        space.lifecycle_version += 1
        space.save(
            update_fields=["status", "archived_at", "lifecycle_version", "updated_at"]
        )
        _record_lifecycle_audit(actor=actor, space=space, event="space_restored")
        return space


def _record_lifecycle_audit(*, actor, space: KnowledgeSpace, event: str):
    from apps.audit.views import create_audit_log

    return create_audit_log(
        user=actor,
        action="space_update",
        target_type="KnowledgeSpace",
        target_id=space.pk,
        details={
            "governed_event": event,
            "space_uuid": str(space.pk),
            "lifecycle_version": space.lifecycle_version,
        },
        organization_id=space.organization_id,
        business_line_id=space.business_line_id,
        space_id=space.pk,
    )


__all__ = [
    "DELETE_SUBMIT_FIELDS",
    "DELETE_CONFIRM_FIELDS",
    "DELETE_CANCEL_FIELDS",
    "reject_unknown_fields",
    "get_deletion_impact",
    "submit_deletion_request",
    "confirm_deletion_request",
    "cancel_deletion_request",
    "get_deletion_request_status",
    "archive_workspace",
    "restore_workspace",
]
