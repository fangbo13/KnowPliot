"""Database-free owner-scoping tests for the Turn recovery endpoint."""

import sys
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.chat.models import ChatSession, ChatTurn
from apps.chat.services import (
    BeginTurnDisposition,
    BeginTurnResult,
    SessionResolutionDisposition,
    SessionResolutionResult,
)
from apps.chat.test_stream_coordination import FakeRedis
from apps.chat.views import chat_turn_status, send_message
from apps.spaces.models import KnowledgeSpace


def scoped_session(user):
    return ChatSession(
        id=uuid.uuid4(),
        user=user,
        title="Existing",
        space=KnowledgeSpace(id=uuid.uuid4()),
    )


class ChatTurnStatusViewTest(SimpleTestCase):
    def setUp(self):
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

    def test_route_is_owner_scoped_and_returns_no_question_content(self):
        user = get_user_model()(id=7, email="owner@example.com")
        session = ChatSession(id=uuid.uuid4(), user=user)
        turn = ChatTurn(
            id=uuid.uuid4(),
            client_request_id=uuid.uuid4(),
            session=session,
            user=user,
            question_message_id=uuid.uuid4(),
            status=ChatTurn.STATUS_ACCEPTED,
            answer_mode=ChatTurn.ANSWER_MODE_FAST,
        )
        request = APIRequestFactory().get(
            reverse("chat-turn-status", kwargs={"turn_id": turn.id})
        )
        force_authenticate(request, user=user)

        with patch("apps.chat.views.get_object_or_404", return_value=turn) as lookup:
            response = chat_turn_status(request, turn.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(turn.id))
        self.assertIsNone(response.data["answer"])
        self.assertNotIn("question", response.data)
        self.assertIs(lookup.call_args.kwargs["user"], user)

    def test_completed_duplicate_replays_saved_result_without_constructing_rag(self):
        user = get_user_model()(id=8, email="owner@example.com")
        session = scoped_session(user)
        turn = SimpleNamespace(
            id=uuid.uuid4(),
            client_request_id=uuid.uuid4(),
            session_id=session.id,
            assistant_message=SimpleNamespace(id=uuid.uuid4()),
        )
        request = APIRequestFactory().post(
            reverse("chat-send-message", kwargs={"session_id": session.id}),
            {
                "content": "same question",
                "client_request_id": str(turn.client_request_id),
            },
            format="json",
        )
        force_authenticate(request, user=user)
        rag_pipeline = SimpleNamespace(RAGPipeline=Mock())

        with (
            patch("apps.chat.views.resolve_request_space", return_value=None),
            patch(
                "apps.chat.views.resolve_chat_session",
                return_value=SessionResolutionResult(
                    session,
                    SessionResolutionDisposition.EXISTING,
                ),
            ),
            patch("apps.chat.views.effective_space_role", return_value="member"),
            patch("apps.chat.views.has_space_permission", return_value=True),
            patch(
                "apps.chat.views.begin_chat_turn",
                return_value=BeginTurnResult(
                    turn=turn,
                    disposition=BeginTurnDisposition.COMPLETED,
                ),
            ),
            patch(
                "apps.chat.views._completed_turn_events",
                return_value=iter(["event: done\ndata: {}\n\n"]),
            ),
            patch.dict(sys.modules, {"apps.rag.pipeline": rag_pipeline}),
        ):
            response = send_message(request, session.id)
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: done", body)
        self.assertFalse(rag_pipeline.RAGPipeline.called)

    def test_active_duplicate_has_stable_conflict_code_and_turn_id(self):
        user = get_user_model()(id=9, email="owner@example.com")
        session = scoped_session(user)
        turn = SimpleNamespace(id=uuid.uuid4(), client_request_id=uuid.uuid4())
        request = APIRequestFactory().post(
            reverse("chat-send-message", kwargs={"session_id": session.id}),
            {"content": "same question", "client_request_id": str(uuid.uuid4())},
            format="json",
        )
        force_authenticate(request, user=user)

        with (
            patch("apps.chat.views.resolve_request_space", return_value=None),
            patch(
                "apps.chat.views.resolve_chat_session",
                return_value=SessionResolutionResult(
                    session,
                    SessionResolutionDisposition.EXISTING,
                ),
            ),
            patch("apps.chat.views.effective_space_role", return_value="member"),
            patch("apps.chat.views.has_space_permission", return_value=True),
            patch(
                "apps.chat.views.begin_chat_turn",
                return_value=BeginTurnResult(
                    turn=turn,
                    disposition=BeginTurnDisposition.IN_PROGRESS,
                ),
            ),
        ):
            response = send_message(request, session.id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "turn_in_progress")
        self.assertEqual(response.data["turn_id"], str(turn.id))

    def test_history_failure_marks_accepted_turn_failed_and_emits_safe_error(self):
        user = get_user_model()(id=10, email="owner@example.com")
        session = scoped_session(user)
        question = SimpleNamespace(pk=uuid.uuid4())
        turn = SimpleNamespace(
            id=uuid.uuid4(),
            client_request_id=uuid.uuid4(),
            session_id=session.id,
            status=ChatTurn.STATUS_ACCEPTED,
            model_id="",
            error_code="",
            completed_at=None,
            assistant_message=None,
            question_message=question,
            save=Mock(),
        )
        request = APIRequestFactory().post(
            reverse("chat-send-message", kwargs={"session_id": session.id}),
            {
                "content": "same question",
                "client_request_id": str(turn.client_request_id),
            },
            format="json",
        )
        force_authenticate(request, user=user)

        with (
            self.assertLogs("apps.chat.views", level="ERROR") as captured,
            patch("apps.chat.views.resolve_request_space", return_value=None),
            patch(
                "apps.chat.views.resolve_chat_session",
                return_value=SessionResolutionResult(
                    session,
                    SessionResolutionDisposition.EXISTING,
                ),
            ),
            patch("apps.chat.views.effective_space_role", return_value="member"),
            patch("apps.chat.views.has_space_permission", return_value=True),
            patch(
                "apps.chat.views.begin_chat_turn",
                return_value=BeginTurnResult(
                    turn=turn,
                    disposition=BeginTurnDisposition.CREATED,
                ),
            ),
            patch(
                "apps.chat.views._conversation_history",
                side_effect=RuntimeError(
                    "raw database secret password=secret"
                ),
            ),
            patch("apps.chat.views.create_redis_client", return_value=FakeRedis()),
            patch("apps.chat.models.ModelInvocation.objects.create"),
        ):
            response = send_message(request, session.id)
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(turn.status, ChatTurn.STATUS_FAILED)
        self.assertEqual(turn.error_code, "stream_error")
        self.assertIn('"error": "stream_error"', body)
        self.assertNotIn("raw database secret", body)
        self.assertNotIn("password=secret", "\n".join(captured.output))
