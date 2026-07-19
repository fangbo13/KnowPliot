"""Durability, dedupe, and retry contracts for external action delivery."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import ActionOutboxEvent
from .outbox_services import (
    dispatch_action_outbox_event,
    enqueue_action_outbox,
    wake_action_outbox,
)


class ActionOutboxTests(TestCase):
    def enqueue(self, **overrides):
        values = {
            "aggregate_type": "space_invitation",
            "aggregate_uuid": uuid.uuid4(),
            "transition": "created",
            "transition_version": 1,
            "recipient_key": f"user:{uuid.uuid4()}",
            "payload": {"schema_version": 1, "resource_id": str(uuid.uuid4())},
        }
        values.update(overrides)
        return enqueue_action_outbox(**values)

    def test_transition_dedupes_and_changed_payload_fails_closed(self):
        aggregate_uuid = uuid.uuid4()
        recipient_key = f"user:{uuid.uuid4()}"
        payload = {"schema_version": 1, "resource_id": str(aggregate_uuid)}
        first = self.enqueue(
            aggregate_uuid=aggregate_uuid,
            recipient_key=recipient_key,
            payload=payload,
        )
        replay = self.enqueue(
            aggregate_uuid=aggregate_uuid,
            recipient_key=recipient_key,
            payload=payload,
        )
        self.assertEqual(first.id, replay.id)

        with self.assertRaises(ValueError):
            self.enqueue(
                aggregate_uuid=aggregate_uuid,
                recipient_key=recipient_key,
                payload={**payload, "unexpected": True},
            )
        self.assertEqual(ActionOutboxEvent.objects.count(), 1)

    def test_failed_delivery_is_retryable_then_delivered(self):
        event = self.enqueue()

        def fail_with_secret(_event):
            raise RuntimeError("provider-secret-and-address-must-not-persist")

        self.assertFalse(dispatch_action_outbox_event(event.id, fail_with_secret))
        event.refresh_from_db()
        self.assertEqual(event.state, ActionOutboxEvent.STATE_FAILED)
        self.assertEqual(event.attempt_count, 1)
        self.assertEqual(event.last_error_code, "external_delivery_failed")
        self.assertNotIn("provider-secret", event.last_error_code)

        event.next_attempt_at = timezone.now()
        event.save(update_fields=["next_attempt_at", "updated_at"])
        delivered = []
        self.assertTrue(
            dispatch_action_outbox_event(event.id, lambda row: delivered.append(row.id))
        )
        event.refresh_from_db()
        self.assertEqual(delivered, [event.id])
        self.assertEqual(event.state, ActionOutboxEvent.STATE_DELIVERED)
        self.assertEqual(event.attempt_count, 2)
        self.assertIsNotNone(event.delivered_at)
        self.assertIsNone(event.next_attempt_at)

    def test_active_lease_prevents_duplicate_delivery(self):
        event = self.enqueue()
        event.state = ActionOutboxEvent.STATE_DELIVERING
        event.lease_expires_at = timezone.now() + timedelta(seconds=30)
        event.save(update_fields=["state", "lease_expires_at", "updated_at"])
        calls = []
        self.assertFalse(
            dispatch_action_outbox_event(event.id, lambda row: calls.append(row.id))
        )
        self.assertEqual(calls, [])

    def test_dispatcher_is_woken_only_after_commit(self):
        event = self.enqueue()
        with patch(
            "apps.notifications.tasks.deliver_action_outbox_event.delay"
        ) as delay:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                wake_action_outbox(event.id)
                delay.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            delay.assert_called_once_with(str(event.id))
