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
from apps.chat.services import BeginTurnDisposition, BeginTurnResult
from apps.chat.views import chat_turn_status, send_message


class ChatTurnStatusViewTest(SimpleTestCase):
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
        session = ChatSession(
            id=uuid.uuid4(), user=user, title="Existing", space=None
        )
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
            patch("apps.chat.views.ChatSession.objects.get", return_value=session),
            patch("apps.chat.views.resolve_request_space", return_value=None),
            patch("apps.chat.views._default_space_for", return_value=None),
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
        session = ChatSession(id=uuid.uuid4(), user=user, title="Existing")
        turn = SimpleNamespace(id=uuid.uuid4())
        request = APIRequestFactory().post(
            reverse("chat-send-message", kwargs={"session_id": session.id}),
            {"content": "same question", "client_request_id": str(uuid.uuid4())},
            format="json",
        )
        force_authenticate(request, user=user)

        with (
            patch("apps.chat.views.ChatSession.objects.get", return_value=session),
            patch("apps.chat.views.resolve_request_space", return_value=None),
            patch("apps.chat.views._default_space_for", return_value=None),
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
