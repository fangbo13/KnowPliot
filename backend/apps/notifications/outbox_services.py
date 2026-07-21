"""Durable, retryable external delivery for notification side effects."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ActionOutboxEvent

logger = logging.getLogger(__name__)


def _payload_digest(payload) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def enqueue_action_outbox(
    *,
    aggregate_type,
    aggregate_uuid,
    transition,
    transition_version,
    recipient_key,
    payload,
):
    """Insert one delivery intent per aggregate transition and recipient.

    Callers invoke this inside the same business transaction as the aggregate,
    audit, and in-app notification writes. A conflicting replay with a changed
    payload fails closed instead of silently changing already-queued delivery.
    """

    if not recipient_key or not (
        recipient_key.startswith("user:")
        or recipient_key.startswith("email_hmac:")
    ):
        raise ValueError("recipient_key must be a safe user or email-HMAC key")
    safe_payload = dict(payload or {})
    digest = _payload_digest(safe_payload)
    event, created = ActionOutboxEvent.objects.get_or_create(
        aggregate_type=aggregate_type,
        aggregate_uuid=aggregate_uuid,
        transition=transition,
        transition_version=transition_version,
        recipient_key=recipient_key,
        defaults={"payload": safe_payload, "payload_digest": digest},
    )
    if not created and event.payload_digest != digest:
        raise ValueError("outbox transition payload mismatch")
    return event


def wake_action_outbox(event_id):
    """Wake the dispatcher after commit without making broker health atomic state."""

    def wake():
        try:
            from .tasks import deliver_action_outbox_event

            deliver_action_outbox_event.delay(str(event_id))
        except Exception:
            # The periodic sweep remains the durable recovery path. Never log
            # payload or recipient data from this best-effort wakeup.
            logger.warning("Action outbox wakeup failed for event_id=%s", event_id)

    transaction.on_commit(wake, robust=True)


def _claim_event(event_id, *, lease_seconds=60):
    now = timezone.now()
    with transaction.atomic():
        event = ActionOutboxEvent.objects.select_for_update().get(pk=event_id)
        if event.state == ActionOutboxEvent.STATE_DELIVERED:
            return None
        if (
            event.state == ActionOutboxEvent.STATE_DELIVERING
            and event.lease_expires_at
            and event.lease_expires_at > now
        ):
            return None
        if event.next_attempt_at and event.next_attempt_at > now:
            return None
        event.state = ActionOutboxEvent.STATE_DELIVERING
        event.attempt_count += 1
        event.lease_expires_at = now + timedelta(seconds=lease_seconds)
        event.last_error_code = ""
        event.save(
            update_fields=[
                "state",
                "attempt_count",
                "lease_expires_at",
                "last_error_code",
                "updated_at",
            ]
        )
        return event.attempt_count


def dispatch_action_outbox_event(event_id, deliver):
    """Claim, deliver, and durably finish one event.

    ``deliver`` is an adapter callable that receives the persisted event. The
    provider call runs outside a database transaction; only the claim and final
    state updates are transactional. Exceptions are reduced to a constant safe
    code so provider messages and addresses cannot leak into durable storage.
    """

    attempt = _claim_event(event_id)
    if attempt is None:
        return False
    event = ActionOutboxEvent.objects.get(pk=event_id)
    try:
        deliver(event)
    except Exception:
        retry_at = timezone.now() + timedelta(
            seconds=min(3600, 2 ** min(attempt, 10))
        )
        with transaction.atomic():
            event = ActionOutboxEvent.objects.select_for_update().get(pk=event_id)
            if (
                event.state == ActionOutboxEvent.STATE_DELIVERING
                and event.attempt_count == attempt
            ):
                event.state = ActionOutboxEvent.STATE_FAILED
                event.next_attempt_at = retry_at
                event.lease_expires_at = None
                event.last_error_code = "external_delivery_failed"
                event.save(
                    update_fields=[
                        "state",
                        "next_attempt_at",
                        "lease_expires_at",
                        "last_error_code",
                        "updated_at",
                    ]
                )
        return False

    with transaction.atomic():
        event = ActionOutboxEvent.objects.select_for_update().get(pk=event_id)
        if (
            event.state == ActionOutboxEvent.STATE_DELIVERING
            and event.attempt_count == attempt
        ):
            event.state = ActionOutboxEvent.STATE_DELIVERED
            event.delivered_at = timezone.now()
            event.next_attempt_at = None
            event.lease_expires_at = None
            event.last_error_code = ""
            event.save(
                update_fields=[
                    "state",
                    "delivered_at",
                    "next_attempt_at",
                    "lease_expires_at",
                    "last_error_code",
                    "updated_at",
                ]
            )
            return True
    return False
