"""Protocol-v3 acceptance, async replay, and cancellation contracts."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.chat.capacity import CapacityReservation
from apps.chat.models import ChatTurn
from apps.chat.services import (
    BeginTurnDisposition,
    BeginTurnResult,
    SessionResolutionDisposition,
    SessionResolutionResult,
)
from apps.chat.test_stream_v2_views import accepted_turn, scoped_session
from apps.chat.v3_views import (
    accept_chat_turn_v3,
    cancel_chat_turn_v3,
    chat_turn_events_dispatch,
)
from apps.chat.views import send_message


class FakeCapacity:
    def __init__(self, *, accepted=True, outstanding=1):
        self.accepted = accepted
        self.outstanding = outstanding
        self.reserved = []
        self.released = []

    def reserve(self, turn_id):
        self.reserved.append(str(turn_id))
        return CapacityReservation(self.accepted, self.outstanding, 5)

    def release(self, turn_id):
        self.released.append(str(turn_id))
        return True


class FakeEventStore:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.events = []

    def append(self, name, data, terminal=False):
        if self.fail:
            from apps.chat.stream_events import EventStoreUnavailableError

            raise EventStoreUnavailableError()
        self.events.append((name, data, terminal))


def v3_turn(status_value=ChatTurn.STATUS_ACCEPTED):
    return SimpleNamespace(
        id=uuid.uuid4(),
        client_request_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        status=status_value,
        protocol_version=3,
        requested_answer_mode="fast",
        answer_mode="fast",
        requested_thinking_enabled=False,
        thinking_enabled=False,
        thinking_snapshot_known=True,
        thinking_budget=None,
        model_id="safe-model",
        policy_fallback_code="",
        error_code="",
        completed_at=None,
        assistant_message=(
            SimpleNamespace(id=uuid.uuid4())
            if status_value == ChatTurn.STATUS_COMPLETED
            else None
        ),
        save=Mock(),
    )


class V3AcceptanceTest(SimpleTestCase):
    def test_created_turn_reserves_writes_meta_and_queues_on_commit(self):
        turn = v3_turn()
        capacity = FakeCapacity()
        events = FakeEventStore()
        enqueue = Mock(return_value=SimpleNamespace(id="task-a"))

        with patch(
            "apps.chat.v3_views.transaction.on_commit",
            side_effect=lambda callback: callback(),
        ):
            response = accept_chat_turn_v3(
                turn,
                disposition=BeginTurnDisposition.CREATED,
                capacity=capacity,
                event_store=events,
                enqueue=enqueue,
            )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["status"], "accepted")
        self.assertEqual(response["Location"], response.data["status_url"])
        self.assertEqual(capacity.reserved, [str(turn.id)])
        self.assertEqual([name for name, _data, _terminal in events.events], ["meta", "phase"])
        self.assertEqual(events.events[1][1], {"phase": "queued"})
        enqueue.assert_called_once_with(turn.id)

    def test_capacity_rejection_returns_stable_429_and_retry_after(self):
        turn = v3_turn()
        response = accept_chat_turn_v3(
            turn,
            disposition=BeginTurnDisposition.CREATED,
            capacity=FakeCapacity(accepted=False, outstanding=625),
            event_store=FakeEventStore(),
            enqueue=Mock(),
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["code"], "generation_capacity_reached")
        self.assertEqual(response.data["retry_after_seconds"], 5)
        self.assertEqual(response["Retry-After"], "5")
        self.assertEqual(turn.status, ChatTurn.STATUS_FAILED)
        self.assertEqual(turn.error_code, "capacity_reached")

    def test_capacity_service_failure_returns_safe_503(self):
        from apps.chat.capacity import GenerationCapacityUnavailable

        capacity = Mock()
        capacity.reserve.side_effect = GenerationCapacityUnavailable()
        response = accept_chat_turn_v3(
            v3_turn(),
            disposition=BeginTurnDisposition.CREATED,
            capacity=capacity,
            event_store=FakeEventStore(),
            enqueue=Mock(),
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {"code": "coordination_unavailable", "retryable": True})

    def test_event_or_enqueue_failure_releases_capacity_and_fails_turn(self):
        for failure in ("events", "enqueue"):
            turn = v3_turn()
            capacity = FakeCapacity()
            event_store = FakeEventStore(fail=failure == "events")
            enqueue = Mock(
                side_effect=RuntimeError("broker details")
                if failure == "enqueue"
                else None
            )

            with self.subTest(failure=failure):
                with patch(
                    "apps.chat.v3_views.transaction.on_commit",
                    side_effect=lambda callback: callback(),
                ):
                    response = accept_chat_turn_v3(
                        turn,
                        disposition=BeginTurnDisposition.CREATED,
                        capacity=capacity,
                        event_store=event_store,
                        enqueue=enqueue,
                    )
                self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
                self.assertEqual(response.data["code"], "coordination_unavailable")
                self.assertEqual(capacity.released, [str(turn.id)])
                self.assertEqual(turn.status, ChatTurn.STATUS_FAILED)
                self.assertNotIn("broker", str(response.data))

    def test_duplicate_in_progress_and_completed_turns_reuse_identity(self):
        for turn_status in (ChatTurn.STATUS_RETRIEVING, ChatTurn.STATUS_COMPLETED):
            turn = v3_turn(turn_status)
            capacity = FakeCapacity()
            enqueue = Mock()
            disposition = (
                BeginTurnDisposition.IN_PROGRESS
                if turn_status == ChatTurn.STATUS_RETRIEVING
                else BeginTurnDisposition.COMPLETED
            )

            with self.subTest(turn_status=turn_status):
                response = accept_chat_turn_v3(
                    turn,
                    disposition=disposition,
                    capacity=capacity,
                    event_store=FakeEventStore(),
                    enqueue=enqueue,
                )
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
                self.assertEqual(response.data["turn_id"], str(turn.id))
                self.assertEqual(
                    response.data["status"],
                    "completed"
                    if turn_status == ChatTurn.STATUS_COMPLETED
                    else "accepted",
                )
                self.assertEqual(capacity.reserved, [])
                enqueue.assert_not_called()


class V3SendRoutingTest(SimpleTestCase):
    def setUp(self):
        self.user = get_user_model()(id=501, email="v3-owner@example.com")
        self.session = scoped_session(self.user)
        self.turn = accepted_turn(self.session)
        self.turn.protocol_version = 3
        self.factory = APIRequestFactory()

    def request(self):
        request = self.factory.post(
            reverse("chat-send-message", kwargs={"session_id": self.session.id}),
            {
                "content": "safe question",
                "client_request_id": str(self.turn.client_request_id),
                "protocol_version": 3,
                "answer_mode": "fast",
                "thinking_enabled": False,
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        return request

    @override_settings(CHAT_STREAM_V3=False)
    def test_disabled_v3_returns_409_before_session_or_turn_work(self):
        with patch("apps.chat.views.resolve_chat_session") as resolve:
            response = send_message(self.request(), self.session.id)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "stream_protocol_unavailable")
        resolve.assert_not_called()

    @override_settings(CHAT_STREAM_V3=True)
    def test_enabled_v3_dispatches_before_legacy_lease_acquisition(self):
        accepted = Response({"status": "accepted"}, status=202)
        policy = SimpleNamespace(
            answer_mode="fast",
            model_id="safe-model",
            thinking_enabled=False,
            thinking_budget=None,
            fallback_code="",
        )
        with (
            patch("apps.chat.views.resolve_request_space", return_value=None),
            patch(
                "apps.chat.views.resolve_chat_session",
                return_value=SessionResolutionResult(
                    self.session,
                    SessionResolutionDisposition.EXISTING,
                ),
            ),
            patch("apps.chat.views.effective_space_role", return_value="member"),
            patch("apps.chat.views.has_space_permission", return_value=True),
            patch("apps.chat.views._request_generation_policy", return_value=policy),
            patch(
                "apps.chat.views.begin_chat_turn",
                return_value=BeginTurnResult(self.turn, BeginTurnDisposition.CREATED),
            ) as begin,
            patch("apps.chat.views._record_turn_metrics"),
            patch("apps.chat.views.accept_chat_turn_v3", return_value=accepted) as accept,
            patch("apps.chat.views.create_redis_client") as legacy_redis,
        ):
            response = send_message(self.request(), self.session.id)

        self.assertIs(response, accepted)
        self.assertEqual(begin.call_args.kwargs["protocol_version"], 3)
        accept.assert_called_once_with(self.turn, disposition=BeginTurnDisposition.CREATED)
        legacy_redis.assert_not_called()


class FakeAsyncRedis:
    def __init__(self, rows):
        self.rows = rows
        self.xread_calls = []

    async def xrange(self, key, min, max):
        return list(self.rows)

    async def xread(self, streams, block, count):
        self.xread_calls.append((streams, block, count))
        return []


class V3AsyncEventsTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(id=7, pk=7, is_authenticated=True)
        self.turn = SimpleNamespace(
            id=uuid.uuid4(),
            protocol_version=3,
            client_request_id=uuid.uuid4(),
        )

    def test_async_endpoint_replays_integer_cursor_through_terminal_event(self):
        request = self.factory.get("/events/?after=0")
        request.user = self.user
        rows = [
            (b"1-0", {b"event": b"phase", b"data": b'{"phase":"queued"}'}),
            (b"2-0", {b"event": b"done", b"data": b'{"message_id":"safe"}'}),
        ]
        with (
            patch("apps.chat.v3_views._load_owned_turn", return_value=self.turn),
            patch("apps.chat.v3_views._async_events_client", return_value=FakeAsyncRedis(rows)),
        ):
            response = async_to_sync(chat_turn_events_dispatch)(request, self.turn.id)

        async def consume():
            return b"".join([chunk async for chunk in response.streaming_content])

        body = async_to_sync(consume)().decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Chat-Turn-Id"], str(self.turn.id))
        self.assertEqual(
            response["X-Chat-Client-Request-Id"],
            str(self.turn.client_request_id),
        )
        self.assertIn("id: 1\nevent: phase", body)
        self.assertIn("id: 2\nevent: done", body)

    def test_cross_user_or_revoked_scope_is_non_disclosing_404(self):
        request = self.factory.get("/events/")
        request.user = self.user
        with patch("apps.chat.v3_views._load_owned_turn", side_effect=Http404):
            response = async_to_sync(chat_turn_events_dispatch)(request, uuid.uuid4())

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("turn", response.content.decode().lower())

    def test_missing_authentication_is_rejected_before_turn_lookup(self):
        request = self.factory.get("/events/")
        with patch("apps.chat.v3_views._load_owned_turn") as load:
            response = async_to_sync(chat_turn_events_dispatch)(
                request,
                uuid.uuid4(),
            )

        self.assertEqual(response.status_code, 401)
        load.assert_not_called()

    def test_v2_turn_delegates_to_unchanged_finite_replay_view(self):
        request = self.factory.get("/events/")
        request.user = self.user
        legacy_turn = SimpleNamespace(id=uuid.uuid4(), protocol_version=2)
        legacy_response = HttpResponse("legacy", content_type="text/event-stream")
        with (
            patch("apps.chat.v3_views._load_owned_turn", return_value=legacy_turn),
            patch("apps.chat.views.chat_turn_events", return_value=legacy_response) as legacy,
        ):
            response = async_to_sync(chat_turn_events_dispatch)(
                request,
                legacy_turn.id,
            )

        self.assertIs(response, legacy_response)
        legacy.assert_called_once_with(request, legacy_turn.id)


class V3CancellationTest(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model()(id=601, email="cancel@example.com")

    def request(self):
        request = self.factory.post("/cancel/", {}, format="json")
        force_authenticate(request, user=self.user)
        return request

    def test_active_cancel_is_idempotent_and_completed_is_rejected(self):
        probe = SimpleNamespace(request=Mock(return_value=True))
        active = v3_turn(ChatTurn.STATUS_ANSWERING)
        with (
            patch("apps.chat.v3_views._owned_turn_for_control", return_value=active),
            patch("apps.chat.v3_views.cancel_probe", return_value=probe),
        ):
            response = cancel_chat_turn_v3(self.request(), active.id)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "cancelling")
        probe.request.assert_called_once()

        completed = v3_turn(ChatTurn.STATUS_COMPLETED)
        with patch(
            "apps.chat.v3_views._owned_turn_for_control",
            return_value=completed,
        ):
            response = cancel_chat_turn_v3(self.request(), completed.id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "turn_not_cancellable")
