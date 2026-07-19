# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Shared primitives for v3 governed workspace workflows.

This module intentionally contains no HTTP code.  The creation, join, and
deletion views use these helpers so idempotency, impact digests, audit, and
durable outbox rows cannot drift into separate state machines.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Iterator

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import (
    GovernedActionOutbox,
    GovernedActionRequest,
    WriteIdempotencyRecord,
)


class GovernedWorkflowError(APIException):
    """Stable, safe domain error mapped by the API exception handler."""

    status_code = 409
    default_code = "governed_conflict"
    default_detail = "The governed operation could not be applied."

    def __init__(self, code: str, detail: str | None = None, *, status_code: int | None = None, details=None):
        self.default_code = code
        self.code = code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail or code)

    def safe_response_body(self) -> dict[str, Any]:
        """Return the canonical body persisted and emitted for this failure.

        The same primitive-only payload is used by the live DRF exception
        handler and by idempotency replay.  Keeping its construction on the
        domain exception prevents the first response from drifting from the
        durable replay representation.
        """

        return canonical_payload(
            {
                "code": self.code,
                "detail": str(self.detail),
                "details": self.details,
            }
        )


class IdempotencyReplay(GovernedWorkflowError):
    status_code = 200


_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")


def normalize_text(value: Any, *, max_length: int, field: str, required: bool = True) -> str:
    if value is None:
        if required:
            raise ValidationError({field: "This field is required."})
        return ""
    if not isinstance(value, str):
        raise ValidationError({field: "Must be a string."})
    normalized = unicodedata.normalize("NFC", value).strip()
    if required and not normalized:
        raise ValidationError({field: "This field may not be blank."})
    if len(normalized) > max_length:
        raise ValidationError({field: f"Must be at most {max_length} characters."})
    return normalized


def normalize_code(value: Any) -> str:
    raw = normalize_text(value, max_length=120, field="code")
    code = unicodedata.normalize("NFKC", raw).lower()
    code = re.sub(r"[\s_]+", "-", code)
    code = re.sub(r"[^a-z0-9-]", "-", code)
    code = re.sub(r"-+", "-", code).strip("-")
    if not _CODE_RE.fullmatch(code):
        raise ValidationError({"code": "Use lower-case letters, numbers, and hyphens."})
    return code


def normalize_locator(organization_slug: str, code: str) -> str:
    return f"{normalize_code(organization_slug)}/{normalize_code(code)}"


def canonical_payload(value: Any) -> Any:
    """Convert UUID/datetime/container values to stable JSON primitives."""

    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes, dict, list, tuple)):
        try:
            return value.isoformat()
        except (AttributeError, TypeError, ValueError):
            pass
    if isinstance(value, dict):
        return {str(k): canonical_payload(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple, set)):
        return [canonical_payload(item) for item in value]
    return value


def digest_payload(value: Any) -> str:
    encoded = json.dumps(canonical_payload(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_idempotency_key(value: Any) -> uuid.UUID:
    if value in (None, ""):
        raise ValidationError({"Idempotency-Key": "A UUID Idempotency-Key header is required."})
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"Idempotency-Key": "Must be a UUID."}) from exc


def require_idempotency_key(request) -> uuid.UUID:
    return parse_idempotency_key(request.headers.get("Idempotency-Key"))


def _lock_idempotency(*, actor_uuid, operation_code: str, key: uuid.UUID):
    return (
        WriteIdempotencyRecord.objects.select_for_update(of=("self",))
        .filter(actor_uuid=actor_uuid, operation_code=operation_code, key=key)
        .order_by("pk")
        .first()
    )


@contextmanager
def durable_governed_transaction():
    """Commit a safely classified operation failure before re-raising it.

    ``operation_record`` rolls domain work back to its savepoint and persists
    the original safe response on the idempotency row. The outer transaction
    must therefore see a normal exit; otherwise Django rolls that evidence back
    too. This wrapper delays only ``GovernedWorkflowError`` until after commit.
    Database/connection failures still escape the atomic block and roll back
    every claim, which is the required safe-to-retry behavior.
    """

    delayed_error = None
    with transaction.atomic():
        try:
            yield
        except GovernedWorkflowError as exc:
            delayed_error = exc
    if delayed_error is not None:
        raise delayed_error


@contextmanager
def operation_record(
    *,
    actor,
    operation_code: str,
    key: uuid.UUID,
    request_digest: str,
    target_uuid=None,
    request_uuid=None,
    ttl_days: int = 90,
) -> Iterator[tuple[WriteIdempotencyRecord, bool]]:
    """Create/lock an operation row inside the caller's outer transaction.

    Yields ``(record, replay)``.  A replay record is never mutated by the
    caller.  The caller should return its stored safe response directly.
    """

    record = _lock_idempotency(
        actor_uuid=actor.pk, operation_code=operation_code, key=key
    )
    if record is not None:
        if record.request_digest != request_digest:
            raise GovernedWorkflowError(
                "idempotency_key_reused",
                "This Idempotency-Key was already used for another operation.",
                details={"current_version": record.response_schema_version},
            )
        if record.disposition == WriteIdempotencyRecord.DISPOSITION_IN_PROGRESS:
            raise GovernedWorkflowError("operation_in_progress", "The operation is still running.")
        yield record, True
        return

    try:
        record = WriteIdempotencyRecord.objects.create(
            actor_uuid=actor.pk,
            operation_code=operation_code,
            key=key,
            request_digest=request_digest,
            target_uuid=target_uuid,
            request_uuid=request_uuid,
            disposition=WriteIdempotencyRecord.DISPOSITION_IN_PROGRESS,
            expires_at=timezone.now() + timedelta(days=ttl_days),
        )
    except IntegrityError as exc:
        # A concurrent insert can win between the probe and create.  Re-read
        # under the same transaction and apply the exact replay/conflict rule.
        record = _lock_idempotency(
            actor_uuid=actor.pk, operation_code=operation_code, key=key
        )
        if record is None:
            raise
        if record.request_digest != request_digest:
            raise GovernedWorkflowError("idempotency_key_reused") from exc
        if record.disposition == WriteIdempotencyRecord.DISPOSITION_IN_PROGRESS:
            raise GovernedWorkflowError("operation_in_progress") from exc
        yield record, True
        return

    try:
        # The caller owns the outer business transaction. This nested atomic
        # block is the domain savepoint: safely classified command failures
        # roll back domain writes while leaving the idempotency row writable.
        with transaction.atomic():
            yield record, False
    except GovernedWorkflowError as exc:
        # Safe domain failures are durable and replayable.  A database error
        # that aborts the outer transaction never reaches this block safely.
        record.disposition = WriteIdempotencyRecord.DISPOSITION_FAILED
        record.failure_code = exc.code
        record.http_status = int(getattr(exc, "status_code", 409))
        record.response_body = exc.safe_response_body()
        record.save(update_fields=["disposition", "failure_code", "http_status", "response_body", "updated_at"])
        raise


def complete_operation_record(record: WriteIdempotencyRecord, *, status_code: int, body: dict, result_reference=None):
    record.disposition = WriteIdempotencyRecord.DISPOSITION_COMPLETED
    record.http_status = status_code
    record.result_reference = result_reference
    record.response_body = canonical_payload(body)
    record.save(update_fields=["disposition", "http_status", "result_reference", "response_body", "updated_at"])


def replay_response(record: WriteIdempotencyRecord):
    """Return a DRF response for a completed/failed operation record."""

    from rest_framework.response import Response

    response = Response(record.response_body, status=record.http_status or 200)
    response["Idempotency-Replayed"] = "true"
    return response


def safe_impact(*, action_type: str, resources: list[dict], policy_version=None, dependency_version=None) -> tuple[str, dict]:
    snapshot = {
        "action_type": action_type,
        "resources": sorted((canonical_payload(item) for item in resources), key=lambda item: json.dumps(item, sort_keys=True)),
        "policy_version": canonical_payload(policy_version),
        "dependency_version": canonical_payload(dependency_version),
    }
    return digest_payload(snapshot), snapshot


def record_transition_audit(*, actor, request: GovernedActionRequest, event: str, old_status: str | None, new_status: str, details: dict | None = None):
    """Persist a secret-free audit row in the same transaction."""

    from apps.audit.views import create_audit_log

    payload = {
        "governed_event": event,
        "request_id": str(request.id),
        "action_type": request.action_type,
        "old_status": old_status,
        "new_status": new_status,
        "request_version": request.request_version,
        "idempotency_outcome": "committed",
    }
    if details:
        payload.update(details)
    return create_audit_log(
        user=actor,
        action="space_update",
        target_type="GovernedActionRequest",
        target_id=request.id,
        details=payload,
        organization_id=request.organization_id,
        business_line_id=request.business_line_id,
        space_id=request.target_space_id,
    )


def enqueue_transition_outbox(*, request: GovernedActionRequest, event_type: str, transition_version: int, recipient=None, payload=None):
    return GovernedActionOutbox.objects.get_or_create(
        request=request,
        event_type=event_type,
        recipient=recipient,
        transition_version=transition_version,
        defaults={"payload": canonical_payload(payload or {}), "state": GovernedActionOutbox.STATE_PENDING},
    )[0]


def eligible_platform_reviewers(*, exclude_user_id=None):
    """Return active, eligible reviewer IDs without exposing identities."""

    User = get_user_model()
    qs = User.objects.filter(is_active=True, is_staff=True)
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)
    # Superusers/staff are the internal-beta platform reviewer baseline.  A
    # deployed RBAC role named ``admin`` is included without requiring a
    # synthetic workspace membership.
    try:
        from apps.rbac.models import UserRole

        role_ids = UserRole.objects.filter(
            is_active=True, role__name="admin", role__is_active=True
        ).values_list("user_id", flat=True)
        from django.db.models import Q

        qs = User.objects.filter(Q(pk__in=qs.values("pk")) | Q(pk__in=role_ids), is_active=True)
        if exclude_user_id:
            qs = qs.exclude(pk=exclude_user_id)
    except Exception:
        pass
    return qs.order_by("pk")


def ensure_two_reviewer_gate(*, requester_id):
    if eligible_platform_reviewers(exclude_user_id=requester_id).count() < 1:
        raise GovernedWorkflowError(
            "reviewer_separation_unavailable",
            "A second eligible reviewer is required.",
        )


__all__ = [
    "GovernedWorkflowError",
    "IdempotencyReplay",
    "normalize_text",
    "normalize_code",
    "normalize_locator",
    "canonical_payload",
    "digest_payload",
    "parse_idempotency_key",
    "require_idempotency_key",
    "durable_governed_transaction",
    "operation_record",
    "complete_operation_record",
    "replay_response",
    "safe_impact",
    "record_transition_audit",
    "enqueue_transition_outbox",
    "eligible_platform_reviewers",
    "ensure_two_reviewer_gate",
]
