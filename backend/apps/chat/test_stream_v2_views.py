"""Database-free view contracts for SSE v2 negotiation and recovery."""

from __future__ import annotations

import sys
import uuid
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.chat.coordination import CoordinationUnavailableError
from apps.chat.models import ChatSession, ChatTurn
from apps.chat.services import (
    BeginTurnDisposition,
    BeginTurnResult,
    SessionResolutionDisposition,
    SessionResolutionResult,
)
from apps.chat.stream_events import RedisTurnEventStore
from apps.chat.test_stream_coordination import FakeRedis
from apps.spaces.models import KnowledgeSpace

try:
    from apps.chat.views import (
        _checkpoint_turn_sequence,
        _owned_recovery_turn,
        _stream_v2_enabled,
        chat_turn_events,
        send_message,
    )
except ImportError:
    _stream_v2_enabled = None
    _checkpoint_turn_sequence = None
    _owned_recovery_turn = None
    chat_turn_events = None
    from apps.chat.views import send_message


def scoped_session(user):
    return ChatSession(
        id=uuid.uuid4(),
        user=user,
        title="Existing",
        space=KnowledgeSpace(id=uuid.uuid4(), status="active"),
    )


def accepted_turn(session, request_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        client_request_id=request_id or uuid.uuid4(),
        session_id=session.id,
        session=session,
        space_id=session.space.id,
        space=session.space,
        user=session.user,
        status=ChatTurn.STATUS_ACCEPTED,
        answer_mode=ChatTurn.ANSWER_MODE_FAST,
        model_id="",
        error_code="",
        last_event_seq=0,
        completed_at=None,
        updated_at=None,
        assistant_message=None,
        question_message=SimpleNamespace(pk=uuid.uuid4()),
        save=Mock(),
    )


class StreamNegotiationTest(SimpleTestCase):
    def setUp(self):
        self.assertIsNotNone(_stream_v2_enabled, "v2 negotiation is missing")

    @override_settings(CHAT_STREAM_V2=False)
    def test_flag_off_preserves_v1_even_when_client_requests_v2(self):
        self.assertFalse(_stream_v2_enabled(2))

    @override_settings(CHAT_STREAM_V2=True)
    def test_v2_requires_both_flag_and_protocol_two(self):
        self.assertFalse(_stream_v2_enabled(1))
        self.assertTrue(_stream_v2_enabled(2))

    def test_sequence_checkpoint_never_regresses_a_newer_database_cursor(self):
        turn_id = uuid.uuid4()
        queryset = Mock()
        with patch(
            "apps.chat.views.ChatTurn.objects.filter",
            return_value=queryset,
        ) as filtered:
            _checkpoint_turn_sequence(turn_id, 25)

        filtered.assert_called_once_with(
            pk=turn_id,
            last_event_seq__lt=25,
        )
        queryset.update.assert_called_once_with(last_event_seq=25)


class SendMessageCoordinationTest(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model()(id=101, email="owner@example.com")
        self.session = scoped_session(self.user)
        self.turn = accepted_turn(self.session)
        self.factory = APIRequestFactory()
        policy_patcher = patch(
            "apps.chat.views._request_generation_policy",
            return_value=SimpleNamespace(
                answer_mode="fast",
                model_id="qwen-plus",
                thinking_enabled=False,
                thinking_budget=None,
                fallback_code="",
            ),
        )
        policy_patcher.start()
        self.addCleanup(policy_patcher.stop)

    def _request(self, protocol_version=2, answer_mode="fast"):
        request = self.factory.post(
            reverse("chat-send-message", kwargs={"session_id": self.session.id}),
            {
                "content": "safe question",
                "client_request_id": str(self.turn.client_request_id),
                "protocol_version": protocol_version,
                "answer_mode": answer_mode,
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        return request

    def _base_patches(self, disposition=BeginTurnDisposition.CREATED):
        return (
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
            patch(
                "apps.chat.views.begin_chat_turn",
                return_value=BeginTurnResult(self.turn, disposition),
            ),
        )

    @override_settings(CHAT_STREAM_V2=True)
    def test_meta_is_first_before_history_or_rag_construction(self):
        redis = FakeRedis()
        history = Mock(return_value=[])
        pipeline_class = Mock()
        rag_module = SimpleNamespace(RAGPipeline=pipeline_class)
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch("apps.chat.views._conversation_history", history),
            patch.dict(sys.modules, {"apps.rag.pipeline": rag_module}),
        ):
            response = send_message(self._request(), self.session.id)
            first = next(iter(response.streaming_content)).decode()
            response.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("id: 1\nevent: meta\n", first)
        self.assertIn('"protocol_version": 2', first)
        history.assert_not_called()
        pipeline_class.assert_not_called()
        self.assertEqual(response["X-Chat-Turn-Id"], str(self.turn.id))
        self.assertEqual(
            response["X-Chat-Client-Request-Id"],
            str(self.turn.client_request_id),
        )
        self.assertEqual(
            [event.name for event in RedisTurnEventStore(redis, self.turn.id).replay()],
            ["meta", "error"],
        )

    @override_settings(CHAT_STREAM_V2=True, DEEP_ANSWER_MODE=True)
    def test_direct_deep_request_without_server_capability_creates_no_turn(self):
        patches = self._base_patches()
        begin = Mock()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patch(
                "apps.chat.views.resolve_capabilities",
                return_value={"capabilities": ["chat.ask"]},
            ),
            patch("apps.chat.views.begin_chat_turn", begin),
        ):
            response = send_message(
                self._request(answer_mode="deep"),
                self.session.id,
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "deep_mode_unavailable")
        begin.assert_not_called()

    @override_settings(CHAT_STREAM_V2=True)
    def test_never_started_response_close_persists_error_and_releases_lease(self):
        redis = FakeRedis()
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
        ):
            response = send_message(self._request(), self.session.id)
            response.close()

        self.assertNotIn(f"chat:session:{self.session.id}:turn", redis.values)
        self.assertEqual(self.turn.status, ChatTurn.STATUS_FAILED)
        self.assertEqual(self.turn.error_code, "client_disconnected")
        self.assertEqual(self.turn.metrics["disconnect_count"], 1)
        replay = RedisTurnEventStore(redis, self.turn.id).replay()
        self.assertEqual([event.name for event in replay], ["meta", "error"])

    @override_settings(CHAT_STREAM_V2=True)
    def test_partial_stream_close_persists_terminal_error_for_replay(self):
        redis = FakeRedis()
        pipeline = SimpleNamespace(model_name="safe-model")
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch("apps.chat.views._conversation_history", return_value=[]),
            patch.dict(
                sys.modules,
                {"apps.rag.pipeline": SimpleNamespace(RAGPipeline=lambda: pipeline)},
            ),
        ):
            response = send_message(self._request(), self.session.id)
            chunks = iter(response.streaming_content)
            self.assertIn("event: meta", next(chunks).decode())
            self.assertIn("event: phase", next(chunks).decode())
            response.close()

        replay = RedisTurnEventStore(redis, self.turn.id).replay()
        self.assertEqual(
            [event.name for event in replay],
            ["meta", "phase", "error"],
        )
        self.assertNotIn(f"chat:session:{self.session.id}:turn", redis.values)

    @override_settings(CHAT_STREAM_V2=True)
    def test_protocol_one_preserves_exact_legacy_error_shape(self):
        redis = FakeRedis()
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch(
                "apps.chat.views._conversation_history",
                side_effect=RuntimeError("private failure"),
            ),
            patch("apps.chat.models.ModelInvocation.objects.create"),
        ):
            response = send_message(self._request(protocol_version=1), self.session.id)
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(
            body,
            'event: error\ndata: {"error": "stream_error"}\n\n',
        )
        self.assertNotIn("id:", body)
        self.assertNotIn("private failure", body)
        self.assertNotIn(f"chat:session:{self.session.id}:turn", redis.values)

    def test_protocol_one_success_records_all_safe_timings(self):
        redis = FakeRedis()
        pipeline = SimpleNamespace(
            model_name="safe-model",
            retrieve_and_generate=Mock(
                return_value=iter(
                    [
                        {
                            "event": "quality",
                            "data": {"score": 0.9, "retrieval_latency_ms": 9},
                        },
                        {"event": "metrics", "data": {"reasoning_ms": 11}},
                        {"event": "token", "data": {"token": "answer"}},
                        {"event": "done", "data": {}},
                    ]
                )
            ),
        )
        assistant = SimpleNamespace(id=uuid.uuid4())
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch("apps.chat.views._conversation_history", return_value=[]),
            patch("apps.chat.views.transaction.atomic", return_value=nullcontext()),
            patch("apps.chat.views.Message.objects.create", return_value=assistant),
            patch("apps.chat.views._save_citations"),
            patch("apps.chat.views._estimate_token_count", return_value=1),
            patch(
                "apps.chat.views.ChatSession.objects.filter",
                return_value=SimpleNamespace(update=Mock()),
            ),
            patch("apps.chat.models.ModelInvocation.objects.create"),
            patch.dict(
                sys.modules,
                {"apps.rag.pipeline": SimpleNamespace(RAGPipeline=lambda: pipeline)},
            ),
        ):
            response = send_message(
                self._request(protocol_version=1),
                self.session.id,
            )
            body = b"".join(response.streaming_content).decode()

        self.assertIn("event: done", body)
        self.assertIn("ttfe_ms", self.turn.metrics)
        self.assertEqual(self.turn.metrics["retrieval_ms"], 9)
        self.assertEqual(self.turn.metrics["reasoning_ms"], 11)
        self.assertIn("first_answer_token_ms", self.turn.metrics)
        self.assertIn("total_ms", self.turn.metrics)

    @override_settings(CHAT_STREAM_V2=True)
    def test_v2_maps_safe_events_persists_terminal_sequence_and_releases(self):
        redis = FakeRedis()
        pipeline = SimpleNamespace(
            model_name="safe-model",
            retrieve_and_generate=Mock(
                return_value=iter(
                    [
                        {"event": "quality", "data": {"score": 0.9}},
                        {
                            "event": "reasoning",
                            "data": {"reasoning": "private chain of thought"},
                        },
                        {"event": "token", "data": {"token": "answer"}},
                        {"event": "done", "data": {}},
                    ]
                )
            ),
        )
        assistant = SimpleNamespace(id=uuid.uuid4())
        checkpoints = Mock()
        session_update = Mock()
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch("apps.chat.views._conversation_history", return_value=[]),
            patch(
                "apps.chat.views._checkpoint_turn_sequence",
                checkpoints,
            ),
            patch("apps.chat.views.transaction.atomic", return_value=nullcontext()),
            patch("apps.chat.views.Message.objects.create", return_value=assistant),
            patch("apps.chat.views._save_citations"),
            patch("apps.chat.views._estimate_token_count", return_value=1),
            patch(
                "apps.chat.views.ChatSession.objects.filter",
                return_value=SimpleNamespace(update=session_update),
            ),
            patch("apps.chat.models.ModelInvocation.objects.create"),
            patch.dict(
                sys.modules,
                {"apps.rag.pipeline": SimpleNamespace(RAGPipeline=lambda: pipeline)},
            ),
        ):
            response = send_message(self._request(), self.session.id)
            self.assertEqual(
                response.status_code,
                200,
                getattr(response, "data", None),
            )
            body = b"".join(response.streaming_content).decode()

        names = [line.removeprefix("event: ") for line in body.splitlines() if line.startswith("event: ")]
        self.assertEqual(
            names,
            [
                "meta",
                "phase",
                "quality",
                "phase",
                "answer_delta",
                "phase",
                "usage",
                "done",
            ],
        )
        self.assertNotIn("reasoning", body)
        self.assertNotIn("private chain of thought", body)
        self.assertIn('"phase": "retrieving"', body)
        self.assertIn('"phase": "answering"', body)
        self.assertIn('"phase": "saving"', body)
        self.assertNotIn('"phase": "searching"', body)
        self.assertNotIn('"phase": "generating"', body)
        self.assertNotIn('"phase": "finalizing"', body)
        ids = [int(line.removeprefix("id: ")) for line in body.splitlines() if line.startswith("id: ")]
        self.assertEqual(ids, list(range(1, len(ids) + 1)))
        checkpoints.assert_called_once_with(self.turn.id, ids[-1])
        self.assertEqual(self.turn.status, ChatTurn.STATUS_COMPLETED)
        self.assertNotIn(f"chat:session:{self.session.id}:turn", redis.values)

    def test_busy_session_marks_turn_retryable_and_returns_stable_409(self):
        redis = FakeRedis()
        redis.values[f"chat:session:{self.session.id}:turn"] = "other-owner"
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
        ):
            response = send_message(self._request(protocol_version=1), self.session.id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "session_busy")
        self.assertEqual(response.data["turn_id"], str(self.turn.id))
        self.assertEqual(self.turn.status, ChatTurn.STATUS_FAILED)
        self.assertEqual(self.turn.error_code, "session_busy")

    def test_redis_unavailable_fails_closed_with_stable_503(self):
        redis = FakeRedis()
        redis.fail = True
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
        ):
            response = send_message(self._request(protocol_version=1), self.session.id)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "coordination_unavailable")
        self.assertEqual(self.turn.status, ChatTurn.STATUS_FAILED)

    def test_redis_client_configuration_failure_is_also_stable_503(self):
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch(
                "apps.chat.views.create_redis_client",
                side_effect=CoordinationUnavailableError(),
            ),
        ):
            response = send_message(self._request(protocol_version=1), self.session.id)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "coordination_unavailable")
        self.assertEqual(self.turn.status, ChatTurn.STATUS_FAILED)

    @override_settings(CHAT_STREAM_V2=True)
    def test_renewal_start_failure_marks_retryable_releases_and_returns_503(self):
        redis = FakeRedis()
        patches = self._base_patches()
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch(
                "apps.chat.views.RedisSessionLease.start_renewal",
                side_effect=CoordinationUnavailableError(),
            ),
        ):
            response = send_message(self._request(), self.session.id)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "coordination_unavailable")
        self.assertTrue(response.data["retryable"])
        self.assertEqual(self.turn.status, ChatTurn.STATUS_FAILED)
        self.assertEqual(self.turn.error_code, "coordination_unavailable")
        self.assertNotIn(f"chat:session:{self.session.id}:turn", redis.values)

    def test_completed_and_active_duplicates_do_not_acquire_a_lease(self):
        completed = accepted_turn(self.session)
        completed.assistant_message = SimpleNamespace(id=uuid.uuid4())
        create_client = Mock()
        request = self._request(protocol_version=1)
        patches = self._base_patches(BeginTurnDisposition.COMPLETED)
        patches = list(patches)
        patches[-1] = patch(
            "apps.chat.views.begin_chat_turn",
            return_value=BeginTurnResult(completed, BeginTurnDisposition.COMPLETED),
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", create_client),
            patch(
                "apps.chat.views._completed_turn_events",
                return_value=iter(["event: done\ndata: {}\n\n"]),
            ),
        ):
            response = send_message(request, self.session.id)
            response.close()
        create_client.assert_not_called()
        self.assertEqual(response["X-Chat-Turn-Id"], str(completed.id))

    @override_settings(CHAT_STREAM_V2=True)
    def test_completed_duplicate_uses_v2_without_acquiring_session_lease(self):
        citations = SimpleNamespace(
            select_related=lambda *_args: SimpleNamespace(all=lambda: [])
        )
        message = SimpleNamespace(
            id=uuid.uuid4(),
            content="saved answer",
            citations=citations,
            confidence_score=0.8,
            confidence_label="high",
            needs_human_review=False,
            retrieval_mode="hybrid",
            retrieval_latency_ms=12,
            token_count=2,
            response_time_ms=25,
            model_used="safe-model",
        )
        completed = accepted_turn(self.session)
        completed.status = ChatTurn.STATUS_COMPLETED
        completed.assistant_message = message
        completed.model_id = "safe-model"
        redis = FakeRedis()
        lease_class = Mock()
        patches = list(self._base_patches(BeginTurnDisposition.COMPLETED))
        patches[-1] = patch(
            "apps.chat.views.begin_chat_turn",
            return_value=BeginTurnResult(completed, BeginTurnDisposition.COMPLETED),
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch("apps.chat.views.RedisSessionLease", lease_class),
            patch("apps.chat.views._checkpoint_turn_sequence"),
        ):
            response = send_message(self._request(), self.session.id)
            body = b"".join(response.streaming_content).decode()

        lease_class.assert_not_called()
        self.assertIn("event: meta", body)
        self.assertIn("event: answer_delta", body)
        self.assertIn("event: done", body)
        self.assertNotIn("event: token", body)


class TurnEventsViewTest(SimpleTestCase):
    def setUp(self):
        self.assertIsNotNone(chat_turn_events, "Turn events recovery view is missing")
        self.user = get_user_model()(id=111, email="owner@example.com")
        self.session = scoped_session(self.user)
        self.turn = accepted_turn(self.session)

    def test_route_exists_and_after_query_replays_only_newer_events(self):
        try:
            url = reverse("chat-turn-events", kwargs={"turn_id": self.turn.id})
        except NoReverseMatch as exc:
            self.fail(f"recovery route missing: {exc}")
        redis = FakeRedis()
        store = RedisTurnEventStore(redis, self.turn.id)
        store.append("meta", {"protocol_version": 2})
        store.append("phase", {"phase": "retrieving"})
        store.append("done", {"message_id": "m"}, terminal=True)
        request = APIRequestFactory().get(f"{url}?after=1")
        force_authenticate(request, user=self.user)

        with (
            patch("apps.chat.views.get_object_or_404", return_value=self.turn),
            patch("apps.chat.views.effective_space_role", return_value="member"),
            patch(
                "apps.chat.views.has_space_permission",
                return_value=True,
            ),
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch("apps.chat.views.converge_stale_turn", return_value=False),
        ):
            response = chat_turn_events(request, self.turn.id)
            body = b"".join(response.streaming_content).decode()

        self.assertNotIn("event: meta", body)
        self.assertIn("id: 2\nevent: phase", body)
        self.assertIn("id: 3\nevent: done", body)

    def test_last_event_id_is_used_when_query_cursor_is_absent(self):
        redis = FakeRedis()
        store = RedisTurnEventStore(redis, self.turn.id)
        store.append("meta", {})
        store.append("done", {"message_id": "m"}, terminal=True)
        request = APIRequestFactory().get(
            "/events/", HTTP_LAST_EVENT_ID="1"
        )
        force_authenticate(request, user=self.user)
        with (
            patch("apps.chat.views.get_object_or_404", return_value=self.turn),
            patch("apps.chat.views.effective_space_role", return_value="member"),
            patch(
                "apps.chat.views.has_space_permission",
                return_value=True,
            ),
            patch("apps.chat.views.create_redis_client", return_value=redis),
            patch("apps.chat.views.converge_stale_turn", return_value=False),
        ):
            response = chat_turn_events(request, self.turn.id)
            body = b"".join(response.streaming_content).decode()
        self.assertNotIn("id: 1\n", body)
        self.assertIn("id: 2\n", body)

    def test_stale_convergence_runs_before_recovery_metrics_touch_updated_at(self):
        order = []
        request = SimpleNamespace(user=self.user)
        with (
            patch("apps.chat.views.get_object_or_404", return_value=self.turn),
            patch("apps.chat.views.has_space_permission", return_value=True),
            patch("apps.chat.views.create_redis_client", return_value=FakeRedis()),
            patch(
                "apps.chat.views.converge_stale_turn",
                side_effect=lambda *_args, **_kwargs: order.append("converge"),
            ),
            patch(
                "apps.chat.views._record_turn_metrics",
                side_effect=lambda *_args, **_kwargs: order.append("metrics"),
            ),
        ):
            _owned_recovery_turn(request, self.turn.id)

        self.assertEqual(order, ["converge", "metrics"])

    def test_membership_denial_is_non_disclosing_and_does_not_touch_redis(self):
        request = APIRequestFactory().get("/events/")
        force_authenticate(request, user=self.user)
        create_client = Mock()
        with (
            patch("apps.chat.views.get_object_or_404", return_value=self.turn),
            patch("apps.chat.views.effective_space_role", return_value="member"),
            patch(
                "apps.chat.views.has_space_permission",
                return_value=False,
            ),
            patch("apps.chat.views.create_redis_client", create_client),
        ):
            response = chat_turn_events(request, self.turn.id)
        self.assertEqual(response.status_code, 404)
        create_client.assert_not_called()

    def test_replay_returns_stable_503_when_client_configuration_is_unavailable(self):
        request = APIRequestFactory().get("/events/")
        force_authenticate(request, user=self.user)
        with (
            patch("apps.chat.views.get_object_or_404", return_value=self.turn),
            patch("apps.chat.views.effective_space_role", return_value="member"),
            patch(
                "apps.chat.views.has_space_permission",
                return_value=True,
            ),
            patch(
                "apps.chat.views.create_redis_client",
                side_effect=CoordinationUnavailableError(),
            ),
        ):
            response = chat_turn_events(request, self.turn.id)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "event_store_unavailable")
