"""Database-free behavioral tests for transport-neutral Turn generation."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.chat.coordination import LeaseLostError
from apps.chat.generation import (
    GenerationEvent,
    NeverCancelled,
    RedisCancellationProbe,
    iter_chat_turn,
)
from apps.chat.models import ChatTurn
from apps.rag.errors import ProviderGenerationError


class FakeLease:
    def __init__(self, *, acquired=True, fail_after=None):
        self.acquired = acquired
        self.fail_after = fail_after
        self.checks = 0
        self.started = False
        self.released = False

    def acquire(self):
        return self.acquired

    def start_renewal(self):
        self.started = True

    def ensure_owned(self):
        self.checks += 1
        if self.fail_after is not None and self.checks >= self.fail_after:
            raise LeaseLostError()

    def release(self):
        self.released = True
        return True


class CancelAfterChecks:
    def __init__(self, allowed_checks):
        self.allowed_checks = allowed_checks
        self.checks = 0
        self.cleared = False

    def raise_if_requested(self):
        self.checks += 1
        if self.checks > self.allowed_checks:
            from apps.chat.generation import GenerationCancelled

            raise GenerationCancelled()

    def clear(self):
        self.cleared = True


class FakeCancelRedis:
    def __init__(self):
        self.values = {}
        self.expiries = {}
        self.fail = False

    def set(self, key, value, *, ex=None):
        if self.fail:
            raise ConnectionError("redis://user:secret@example.invalid/0")
        self.values[key] = value
        self.expiries[key] = ex
        return True

    def get(self, key):
        if self.fail:
            raise ConnectionError("redis unavailable")
        return self.values.get(key)

    def delete(self, key):
        if self.fail:
            raise ConnectionError("redis unavailable")
        return int(self.values.pop(key, None) is not None)


class RedisCancellationProbeTest(SimpleTestCase):
    def test_request_requested_and_clear_are_idempotent(self):
        redis = FakeCancelRedis()
        probe = RedisCancellationProbe(redis, "turn-a", ttl_seconds=900)

        self.assertFalse(probe.requested())
        self.assertTrue(probe.request())
        self.assertTrue(probe.requested())
        self.assertEqual(redis.expiries[probe.key], 900)
        self.assertTrue(probe.clear())
        self.assertFalse(probe.clear())

    def test_redis_failure_fails_closed_with_safe_error(self):
        redis = FakeCancelRedis()
        redis.fail = True
        probe = RedisCancellationProbe(redis, "turn-a", ttl_seconds=900)

        for operation in (probe.request, probe.requested, probe.clear):
            with self.subTest(operation=operation), self.assertRaises(
                RuntimeError
            ) as captured:
                operation()
            self.assertNotIn("secret", str(captured.exception))


class GenerationServiceTest(SimpleTestCase):
    def setUp(self):
        self.turn = SimpleNamespace(
            id=uuid.uuid4(),
            pk=None,
            client_request_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            session=SimpleNamespace(id=None),
            space_id=uuid.uuid4(),
            space=SimpleNamespace(id=None),
            user=SimpleNamespace(pk=7),
            question_message=SimpleNamespace(pk=uuid.uuid4(), content="question"),
            assistant_message=None,
            status=ChatTurn.STATUS_ACCEPTED,
            model_id="safe-model",
            answer_mode="fast",
            thinking_enabled=False,
            thinking_budget=None,
            metrics={},
        )
        self.turn.pk = self.turn.id
        self.turn.session.id = self.turn.session_id
        self.turn.space.id = self.turn.space_id
        self.lease = FakeLease()
        self.persist = Mock(
            return_value=SimpleNamespace(
                message=SimpleNamespace(id=uuid.uuid4()),
                token_count=1,
                timings={"total_ms": 10},
            )
        )

    def _transition(self, turn, target, **kwargs):
        turn.status = target
        if "assistant_message" in kwargs:
            turn.assistant_message = kwargs["assistant_message"]
        turn.error_code = kwargs.get("error_code", "")
        return turn

    def _run(self, pipeline_events, *, probe=None, lease=None, persist=None):
        pipeline = SimpleNamespace(
            model_name="safe-model",
            retrieve_and_generate=Mock(return_value=iter(pipeline_events)),
        )
        with (
            patch("apps.chat.generation._load_turn", return_value=self.turn),
            patch("apps.chat.generation._make_lease", return_value=lease or self.lease),
            patch("apps.chat.generation._build_pipeline", return_value=pipeline),
            patch("apps.chat.generation._conversation_history", return_value=[]),
            patch(
                "apps.chat.generation._persist_completed_turn",
                persist or self.persist,
            ),
            patch("apps.chat.generation.transition_chat_turn", self._transition),
            patch("apps.chat.generation._record_invocation"),
            patch("apps.chat.generation._record_metrics"),
        ):
            return list(iter_chat_turn(self.turn.id, cancellation_probe=probe))

    def test_success_preserves_domain_order_and_completes_once(self):
        events = self._run(
            [
                {"event": "citations", "data": [{"document_id": "safe"}]},
                {"event": "quality", "data": {"score": 0.9}},
                {"event": "token", "data": {"token": "answer"}},
                {"event": "done", "data": {}},
            ],
            probe=NeverCancelled(),
        )

        self.assertEqual(
            [event.name for event in events],
            ["phase", "citations", "quality", "answer_delta", "done"],
        )
        self.assertTrue(events[-1].terminal)
        self.assertEqual(self.turn.status, ChatTurn.STATUS_COMPLETED)
        self.assertIsNotNone(self.turn.assistant_message)
        self.persist.assert_called_once()
        self.assertTrue(self.lease.released)

    def test_cancellation_before_retrieval_writes_no_answer(self):
        events = self._run([], probe=CancelAfterChecks(allowed_checks=0))

        self.assertEqual(events, [GenerationEvent(
            "error", {"code": "cancelled", "retryable": False}, terminal=True
        )])
        self.assertEqual(self.turn.status, ChatTurn.STATUS_CANCELLED)
        self.assertIsNone(self.turn.assistant_message)
        self.persist.assert_not_called()

    def test_cancellation_after_partial_answer_does_not_persist(self):
        events = self._run(
            [
                {"event": "token", "data": {"token": "partial"}},
                {"event": "token", "data": {"token": "ignored"}},
            ],
            probe=CancelAfterChecks(allowed_checks=2),
        )

        self.assertEqual(
            [event.name for event in events],
            ["phase", "answer_delta", "error"],
        )
        self.assertEqual(events[-1].data["code"], "cancelled")
        self.assertEqual(self.turn.status, ChatTurn.STATUS_CANCELLED)
        self.persist.assert_not_called()

    def test_lease_loss_fails_turn_safely(self):
        events = self._run(
            [{"event": "token", "data": {"token": "ignored"}}],
            lease=FakeLease(fail_after=2),
        )

        self.assertEqual(events[-1].data["code"], "lease_lost")
        self.assertEqual(self.turn.status, ChatTurn.STATUS_FAILED)
        self.persist.assert_not_called()

    def test_provider_failure_is_stable_and_retryable(self):
        def failed_events():
            raise ProviderGenerationError("private upstream detail")
            yield

        events = self._run(failed_events())

        self.assertEqual(
            events[-1],
            GenerationEvent(
                "error",
                {"code": "provider_unavailable", "retryable": True},
                terminal=True,
            ),
        )
        self.assertEqual(self.turn.error_code, "provider_unavailable")

    def test_persistence_failure_creates_no_success_event(self):
        events = self._run(
            [{"event": "token", "data": {"token": "answer"}}],
            persist=Mock(side_effect=RuntimeError("database details")),
        )

        self.assertEqual(events[-1].data["code"], "answer_save_error")
        self.assertNotIn("database", str(events[-1].data))
        self.assertEqual(self.turn.status, ChatTurn.STATUS_FAILED)

    def test_duplicate_completed_reentry_does_not_acquire_or_persist(self):
        self.turn.status = ChatTurn.STATUS_COMPLETED
        self.turn.assistant_message = SimpleNamespace(id=uuid.uuid4())

        events = self._run([])

        self.assertEqual(events, [])
        self.assertFalse(self.lease.started)
        self.persist.assert_not_called()
