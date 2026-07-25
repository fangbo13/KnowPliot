"""Contracts for the dedicated protocol-v3 Celery generation task."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import SimpleTestCase

from apps.chat.generation import GenerationEvent
from apps.chat.stream_events import EventStoreUnavailableError, SSEEvent
from apps.chat.tasks import (
    GenerationReservationLost,
    enqueue_chat_turn_v3,
    generate_chat_turn_v3,
)


DONE = {
    "message_id": "message-a",
    "session_id": "session-a",
    "model": "safe-model",
    "turn_id": "turn-a",
    "client_request_id": "request-a",
}


class FakeCapacity:
    def __init__(self, *, renewed=True):
        self.renewed = renewed
        self.renewed_ids = []
        self.released_ids = []

    def renew(self, turn_id):
        self.renewed_ids.append(str(turn_id))
        return self.renewed

    def release(self, turn_id):
        self.released_ids.append(str(turn_id))
        return True


class FakeProbe:
    def __init__(self):
        self.cleared = False

    def clear(self):
        self.cleared = True
        return True


class FakeStream:
    def __init__(self, *, fail_on=None):
        self.events = []
        self.fail_on = fail_on

    def replay(self):
        return list(self.events)

    def append(self, name, data, terminal=False):
        if name == self.fail_on:
            raise EventStoreUnavailableError()
        event = SSEEvent(len(self.events) + 1, name, data)
        self.events.append(event)
        return event


class GenerationTaskTest(SimpleTestCase):
    def _run(self, generated, *, capacity=None, stream=None, probe=None):
        capacity = capacity or FakeCapacity()
        stream = stream or FakeStream()
        probe = probe or FakeProbe()
        metrics = Mock()
        with (
            patch(
                "apps.chat.tasks.generation_capacity_controller",
                return_value=capacity,
            ),
            patch("apps.chat.tasks.v3_event_store", return_value=stream),
            patch("apps.chat.tasks.cancel_probe", return_value=probe),
            patch("apps.chat.tasks.iter_chat_turn", return_value=iter(generated)),
            patch("apps.chat.tasks._record_task_metrics", metrics),
        ):
            result = generate_chat_turn_v3.run("turn-a")
        return result, capacity, stream, probe, metrics

    def test_task_batches_deltas_and_releases_capacity_and_cancellation(self):
        result, capacity, stream, probe, metrics = self._run(
            [
                GenerationEvent("answer_delta", {"text": "a"}),
                GenerationEvent("answer_delta", {"text": "b"}),
                GenerationEvent("done", DONE, terminal=True),
            ]
        )

        self.assertEqual(result, {"status": "completed", "turn_id": "turn-a"})
        self.assertEqual(
            [event.name for event in stream.events],
            ["phase", "answer_delta", "done"],
        )
        self.assertEqual(stream.events[1].data, {"text": "ab"})
        self.assertEqual(capacity.renewed_ids, ["turn-a"])
        self.assertEqual(capacity.released_ids, ["turn-a"])
        self.assertTrue(probe.cleared)
        self.assertEqual(metrics.call_args.kwargs["delta_batch_count"], 1)

    def test_existing_queued_event_is_not_duplicated_on_redelivery(self):
        stream = FakeStream()
        stream.append("phase", {"phase": "queued"})

        self._run(
            [GenerationEvent("done", DONE, terminal=True)],
            stream=stream,
        )
        self._run([], stream=stream)

        queued = [
            event
            for event in stream.events
            if event.name == "phase" and event.data == {"phase": "queued"}
        ]
        self.assertEqual(len(queued), 1)
        self.assertEqual(sum(event.name == "done" for event in stream.events), 1)

    def test_lost_reservation_fails_before_generation_and_still_releases(self):
        capacity = FakeCapacity(renewed=False)
        probe = FakeProbe()
        with (
            patch(
                "apps.chat.tasks.generation_capacity_controller",
                return_value=capacity,
            ),
            patch("apps.chat.tasks.v3_event_store", return_value=FakeStream()),
            patch("apps.chat.tasks.cancel_probe", return_value=probe),
            patch("apps.chat.tasks.iter_chat_turn") as generate,
            patch("apps.chat.tasks._record_task_metrics"),
            patch("apps.chat.tasks._mark_task_failed"),
            self.assertRaises(GenerationReservationLost),
        ):
            generate_chat_turn_v3.run("turn-a")

        generate.assert_not_called()
        self.assertEqual(capacity.released_ids, ["turn-a"])
        self.assertTrue(probe.cleared)

    def test_event_store_failure_marks_active_turn_failed_and_releases(self):
        stream = FakeStream(fail_on="answer_delta")
        failed = Mock()
        with patch("apps.chat.tasks._mark_task_failed", failed):
            with self.assertRaises(EventStoreUnavailableError):
                self._run(
                    [
                        GenerationEvent("answer_delta", {"text": "answer"}),
                        GenerationEvent("done", DONE, terminal=True),
                    ],
                    stream=stream,
                )

        failed.assert_called_once_with("turn-a", "coordination_unavailable")

    def test_task_declaration_uses_dedicated_reliable_delivery_contract(self):
        self.assertEqual(generate_chat_turn_v3.name, "apps.chat.tasks.generate_chat_turn_v3")
        self.assertTrue(generate_chat_turn_v3.acks_late)
        self.assertTrue(generate_chat_turn_v3.reject_on_worker_lost)
        self.assertEqual(generate_chat_turn_v3.max_retries, 3)
        self.assertEqual(generate_chat_turn_v3.soft_time_limit, 90)
        self.assertEqual(generate_chat_turn_v3.time_limit, 100)
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["apps.chat.tasks.generate_chat_turn_v3"],
            {"queue": "chat_generation"},
        )
        self.assertEqual(
            settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"],
            180,
        )
        self.assertEqual(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 1)

    def test_eager_celery_execution_runs_the_full_task_wrapper(self):
        capacity = FakeCapacity()
        stream = FakeStream()
        probe = FakeProbe()
        with (
            patch(
                "apps.chat.tasks.generation_capacity_controller",
                return_value=capacity,
            ),
            patch("apps.chat.tasks.v3_event_store", return_value=stream),
            patch("apps.chat.tasks.cancel_probe", return_value=probe),
            patch(
                "apps.chat.tasks.iter_chat_turn",
                return_value=iter([GenerationEvent("done", DONE, terminal=True)]),
            ),
            patch("apps.chat.tasks._record_task_metrics"),
        ):
            result = generate_chat_turn_v3.apply(args=["turn-a"], throw=True)

        self.assertTrue(result.successful())
        self.assertEqual(result.result["status"], "completed")
        self.assertEqual([event.name for event in stream.events], ["phase", "done"])

    def test_enqueue_routes_only_to_chat_generation_queue(self):
        with patch.object(generate_chat_turn_v3, "apply_async") as apply_async:
            expected = SimpleNamespace(id="task-a")
            apply_async.return_value = expected

            result = enqueue_chat_turn_v3("turn-a")

        self.assertIs(result, expected)
        apply_async.assert_called_once_with(args=["turn-a"], queue="chat_generation")
