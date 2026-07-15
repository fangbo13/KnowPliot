"""Database-free contract tests for durable chat turns."""

import uuid
from contextlib import contextmanager
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.chat.models import ChatTurn
from apps.chat.serializers import ChatMessageRequestSerializer
from apps.chat.services import (
    BeginTurnDisposition,
    InvalidTurnTransitionError,
    begin_chat_turn,
    transition_chat_turn,
)


class ChatTurnModelContractTest(SimpleTestCase):
    def test_model_has_durable_identity_and_safe_operational_fields(self):
        fields = {field.name: field for field in ChatTurn._meta.get_fields()}

        self.assertTrue(fields["id"].primary_key)
        self.assertEqual(fields["id"].get_internal_type(), "UUIDField")
        self.assertEqual(fields["client_request_id"].get_internal_type(), "UUIDField")
        self.assertEqual(fields["question_message"].one_to_one, True)
        self.assertEqual(fields["assistant_message"].one_to_one, True)
        self.assertTrue(fields["assistant_message"].null)
        self.assertEqual(
            {value for value, _label in fields["status"].choices},
            {
                "accepted",
                "retrieving",
                "reasoning",
                "answering",
                "saving",
                "completed",
                "failed",
                "cancelled",
            },
        )
        self.assertEqual(
            {value for value, _label in fields["answer_mode"].choices},
            {"fast", "deep"},
        )

        constraints = ChatTurn._meta.constraints
        self.assertTrue(
            any(
                tuple(constraint.fields) == ("user", "client_request_id")
                for constraint in constraints
            )
        )
        index_fields = {tuple(index.fields) for index in ChatTurn._meta.indexes}
        self.assertIn(("session", "status"), index_fields)
        self.assertIn(("user", "-started_at"), index_fields)


class ChatMessageRequestSerializerTest(SimpleTestCase):
    def test_defaults_old_callers_to_server_request_id_fast_and_protocol_one(self):
        serializer = ChatMessageRequestSerializer(data={"content": "  hello  "})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsInstance(serializer.validated_data["client_request_id"], uuid.UUID)
        self.assertEqual(serializer.validated_data["answer_mode"], "fast")
        self.assertEqual(serializer.validated_data["protocol_version"], 1)
        self.assertEqual(serializer.validated_data["content"], "hello")

    def test_accepts_v2_identity_and_rejects_unknown_contract_values(self):
        request_id = uuid.uuid4()
        serializer = ChatMessageRequestSerializer(
            data={
                "content": "hello",
                "client_request_id": str(request_id),
                "answer_mode": "deep",
                "protocol_version": 2,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["client_request_id"], request_id)

        invalid = ChatMessageRequestSerializer(
            data={"content": "hello", "answer_mode": "slow", "protocol_version": 3}
        )
        self.assertFalse(invalid.is_valid())
        self.assertEqual(set(invalid.errors), {"answer_mode", "protocol_version"})


class FakeTurnRepository:
    def __init__(self, existing=None):
        self.existing = existing
        self.questions = []
        self.created_turns = []
        self.touched_sessions = []
        self.locked_users = []
        self.saved_turns = []

    def lock_user(self, user_id):
        self.locked_users.append(user_id)

    def find_turn(self, user, client_request_id):
        return self.existing

    def create_question(self, *, session, space, content):
        question = SimpleNamespace(
            id=uuid.uuid4(), session_id=session.id, content=content, role="user"
        )
        self.questions.append(question)
        return question

    def create_turn(self, **values):
        turn_values = {
            **values,
            "id": uuid.uuid4(),
            "status": "accepted",
            "attempt_count": 1,
            "last_event_seq": 0,
            "error_code": "",
            "model_id": "",
            "assistant_message": None,
            "completed_at": None,
            "session_id": values["session"].id,
        }
        turn = SimpleNamespace(**turn_values)
        self.created_turns.append(turn)
        return turn

    def save_retry(self, turn):
        self.saved_turns.append(turn)

    def touch_session(self, session):
        self.touched_sessions.append(session.id)


class ChatTurnBeginServiceTest(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk=7)
        self.session = SimpleNamespace(id=uuid.uuid4(), space="space")
        self.request_id = uuid.uuid4()
        self.atomic_entries = 0

    @contextmanager
    def atomic(self):
        self.atomic_entries += 1
        yield

    def begin(self, repository):
        return begin_chat_turn(
            user=self.user,
            session=self.session,
            space=self.session.space,
            client_request_id=self.request_id,
            content="same question",
            answer_mode="fast",
            repository=repository,
            atomic_factory=self.atomic,
        )

    def existing(self, **overrides):
        values = {
            "id": uuid.uuid4(),
            "status": "accepted",
            "attempt_count": 1,
            "last_event_seq": 5,
            "error_code": "",
            "model_id": "model-old",
            "assistant_message": None,
            "completed_at": None,
            "session_id": self.session.id,
            "question_message": SimpleNamespace(content="same question"),
            "answer_mode": "fast",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_new_request_atomically_creates_exactly_one_question_and_turn(self):
        repository = FakeTurnRepository()

        result = self.begin(repository)

        self.assertEqual(result.disposition, BeginTurnDisposition.CREATED)
        self.assertEqual(len(repository.questions), 1)
        self.assertEqual(len(repository.created_turns), 1)
        self.assertIs(result.turn.question_message, repository.questions[0])
        self.assertEqual(repository.locked_users, [self.user.pk])
        self.assertEqual(repository.touched_sessions, [self.session.id])
        self.assertEqual(self.atomic_entries, 1)

    def test_completed_and_active_duplicates_create_no_question(self):
        completed = self.existing(
            status="completed", assistant_message=SimpleNamespace(id=uuid.uuid4())
        )
        completed_repository = FakeTurnRepository(completed)
        completed_result = self.begin(completed_repository)
        self.assertEqual(completed_result.disposition, BeginTurnDisposition.COMPLETED)
        self.assertEqual(completed_repository.questions, [])

        active_repository = FakeTurnRepository(self.existing(status="answering"))
        active_result = self.begin(active_repository)
        self.assertEqual(active_result.disposition, BeginTurnDisposition.IN_PROGRESS)
        self.assertEqual(active_repository.questions, [])

    def test_retryable_failure_reuses_question_and_resets_only_safe_fields(self):
        question = SimpleNamespace(content="same question")
        failed = self.existing(
            status="failed",
            attempt_count=2,
            error_code="stream_timeout",
            last_event_seq=9,
            assistant_message=SimpleNamespace(id=uuid.uuid4()),
            question_message=question,
        )
        repository = FakeTurnRepository(failed)

        result = self.begin(repository)

        self.assertEqual(result.disposition, BeginTurnDisposition.RETRY)
        self.assertIs(result.turn.question_message, question)
        self.assertEqual(result.turn.attempt_count, 3)
        self.assertEqual(result.turn.status, "accepted")
        self.assertEqual(result.turn.error_code, "")
        self.assertEqual(result.turn.last_event_seq, 0)
        self.assertIsNone(result.turn.assistant_message)
        self.assertEqual(repository.questions, [])
        self.assertEqual(repository.saved_turns, [failed])

    def test_same_request_id_with_different_identity_is_a_conflict(self):
        repository = FakeTurnRepository(
            self.existing(question_message=SimpleNamespace(content="different"))
        )

        result = self.begin(repository)

        self.assertEqual(result.disposition, BeginTurnDisposition.CONFLICT)
        self.assertEqual(repository.questions, [])


class ChatTurnTransitionTest(SimpleTestCase):
    def test_allows_normal_lifecycle_and_stores_only_safe_error_codes(self):
        turn = SimpleNamespace(
            status="accepted",
            error_code="",
            completed_at=None,
            assistant_message=None,
            model_id="",
        )

        transition_chat_turn(turn, "retrieving", save=False)
        transition_chat_turn(turn, "answering", model_id="model-safe", save=False)
        transition_chat_turn(turn, "failed", error_code="provider_timeout", save=False)

        self.assertEqual(turn.status, "failed")
        self.assertEqual(turn.error_code, "provider_timeout")
        self.assertEqual(turn.model_id, "model-safe")

        retry = SimpleNamespace(
            status="accepted",
            error_code="",
            completed_at=None,
            assistant_message=None,
            model_id="",
        )
        transition_chat_turn(retry, "failed", error_code="raw exception: secret", save=False)
        self.assertEqual(retry.error_code, "internal_error")

    def test_rejects_illegal_terminal_transition(self):
        turn = SimpleNamespace(
            status="completed",
            error_code="",
            completed_at=None,
            assistant_message=SimpleNamespace(),
            model_id="model",
        )

        with self.assertRaises(InvalidTurnTransitionError):
            transition_chat_turn(turn, "answering", save=False)
