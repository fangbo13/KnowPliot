"""Database-free contract tests for durable chat turns."""

import uuid
from contextlib import contextmanager
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from apps.chat.metrics import sanitize_turn_metrics
from apps.chat.models import ChatTurn
from apps.chat.serializers import ChatMessageRequestSerializer
from apps.chat.services import (
    BeginTurnDisposition,
    ChatTurnScopeError,
    InvalidTurnTransitionError,
    SessionResolutionDisposition,
    begin_chat_turn,
    resolve_chat_session,
    transition_chat_turn,
)


class ChatTurnModelContractTest(SimpleTestCase):
    def test_model_has_durable_identity_and_safe_operational_fields(self):
        fields = {field.name: field for field in ChatTurn._meta.get_fields()}

        self.assertTrue(fields["id"].primary_key)
        self.assertEqual(fields["id"].get_internal_type(), "UUIDField")
        self.assertEqual(fields["client_request_id"].get_internal_type(), "UUIDField")
        self.assertEqual(fields["question_message"].many_to_one, True)
        self.assertEqual(fields["assistant_message"].one_to_one, True)
        self.assertTrue(fields["assistant_message"].null)
        self.assertFalse(fields["space"].null)
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

    def test_metrics_accept_the_boolean_idempotency_rollout_marker(self):
        metrics = sanitize_turn_metrics(
            {
                "idempotency_disposition": "created",
                "idempotency_rollout_enabled": True,
            }
        )

        self.assertEqual(metrics["idempotency_disposition"], "created")
        self.assertIs(metrics["idempotency_rollout_enabled"], True)

        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"idempotency_rollout_enabled": 1})


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
            data={"content": "hello", "answer_mode": "slow", "protocol_version": 4}
        )
        self.assertFalse(invalid.is_valid())
        self.assertEqual(set(invalid.errors), {"answer_mode", "protocol_version"})


class FakeTurnRepository:
    def __init__(self, existing=None, locked_session=None):
        self.existing = existing
        self.locked_session = locked_session
        self.questions = []
        self.created_turns = []
        self.touched_sessions = []
        self.locked_users = []
        self.locked_sessions = []
        self.saved_turns = []

    def lock_user(self, user_id):
        self.locked_users.append(user_id)

    def lock_session(self, session_id):
        self.locked_sessions.append(session_id)
        return self.locked_session

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
            "space_id": values["space"].id,
            "user_id": values["user"].pk,
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
        self.space = SimpleNamespace(
            id=uuid.uuid4(),
            status="active",
            organization=SimpleNamespace(status="active"),
            business_line_id=None,
        )
        self.session = SimpleNamespace(
            id=uuid.uuid4(),
            pk=None,
            user=self.user,
            user_id=self.user.pk,
            space=self.space,
            space_id=self.space.id,
        )
        self.session.pk = self.session.id
        self.request_id = uuid.uuid4()
        self.atomic_entries = 0

    @contextmanager
    def atomic(self):
        self.atomic_entries += 1
        yield

    def begin(self, repository):
        if repository.locked_session is None:
            repository.locked_session = self.session
        return begin_chat_turn(
            session=self.session,
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
            "space_id": self.space.id,
            "user_id": self.user.pk,
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
        self.assertEqual(repository.locked_sessions, [self.session.id])
        self.assertEqual(repository.touched_sessions, [self.session.id])
        self.assertIs(result.turn.user, self.user)
        self.assertIs(result.turn.space, self.space)
        self.assertEqual(self.atomic_entries, 1)

    def test_protocol_three_is_persisted_and_part_of_idempotent_identity(self):
        repository = FakeTurnRepository()
        repository.locked_session = self.session

        created = begin_chat_turn(
            session=self.session,
            client_request_id=self.request_id,
            content="same question",
            answer_mode="fast",
            protocol_version=3,
            repository=repository,
            atomic_factory=self.atomic,
        )

        self.assertEqual(created.turn.protocol_version, 3)

        duplicate_repository = FakeTurnRepository(created.turn, self.session)
        duplicate = self.begin(duplicate_repository)
        self.assertEqual(duplicate.disposition, BeginTurnDisposition.CONFLICT)

    def test_regeneration_reuses_the_original_question_without_creating_a_duplicate(self):
        repository = FakeTurnRepository()
        repository.locked_session = self.session
        original_question = SimpleNamespace(
            id=uuid.uuid4(),
            session_id=self.session.id,
            space_id=self.space.id,
            content="same question",
            role="user",
        )

        result = begin_chat_turn(
            session=self.session,
            client_request_id=self.request_id,
            content="same question",
            answer_mode="fast",
            question_message=original_question,
            repository=repository,
            atomic_factory=self.atomic,
        )

        self.assertEqual(result.disposition, BeginTurnDisposition.CREATED)
        self.assertEqual(repository.questions, [])
        self.assertIs(result.turn.question_message, original_question)

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
        self.assertEqual(result.turn.last_event_seq, 9)
        self.assertIsNone(result.turn.assistant_message)
        self.assertEqual(repository.questions, [])
        self.assertEqual(repository.saved_turns, [failed])

    def test_retryable_deep_failure_can_downgrade_to_fast_on_the_same_turn(self):
        failed = self.existing(
            status="failed",
            answer_mode="deep",
            model_id="deep-model",
            error_code="provider_unavailable",
        )
        repository = FakeTurnRepository(failed)
        repository.locked_session = self.session

        result = begin_chat_turn(
            session=self.session,
            client_request_id=self.request_id,
            content="same question",
            requested_answer_mode="deep",
            answer_mode="fast",
            model_id="fast-model",
            repository=repository,
            atomic_factory=self.atomic,
        )

        self.assertEqual(result.disposition, BeginTurnDisposition.RETRY)
        self.assertEqual(result.turn.answer_mode, "fast")
        self.assertEqual(result.turn.model_id, "fast-model")
        self.assertEqual(repository.questions, [])

    def test_same_request_id_with_different_identity_is_a_conflict(self):
        repository = FakeTurnRepository(
            self.existing(question_message=SimpleNamespace(content="different"))
        )

        result = self.begin(repository)

        self.assertEqual(result.disposition, BeginTurnDisposition.CONFLICT)
        self.assertEqual(repository.questions, [])

        wrong_scope_repository = FakeTurnRepository(
            self.existing(space_id=uuid.uuid4())
        )
        wrong_scope_result = self.begin(wrong_scope_repository)
        self.assertEqual(
            wrong_scope_result.disposition,
            BeginTurnDisposition.CONFLICT,
        )
        self.assertEqual(wrong_scope_repository.questions, [])

    def test_rejects_null_or_mismatched_locked_session_scope(self):
        missing_space = SimpleNamespace(
            **{**vars(self.session), "space": None, "space_id": None}
        )
        missing_repository = FakeTurnRepository(locked_session=missing_space)
        with self.assertRaises(ChatTurnScopeError):
            self.begin(missing_repository)
        self.assertEqual(missing_repository.questions, [])

        other_user = SimpleNamespace(pk=99)
        mismatched = SimpleNamespace(
            **{
                **vars(self.session),
                "user": other_user,
                "user_id": other_user.pk,
            }
        )
        mismatch_repository = FakeTurnRepository(locked_session=mismatched)
        with self.assertRaises(ChatTurnScopeError):
            self.begin(mismatch_repository)
        self.assertEqual(mismatch_repository.questions, [])


class FakeSessionRepository:
    def __init__(self, session=None):
        self.session = session
        self.locked_users = []
        self.lookups = []
        self.created = []
        self.saved_spaces = []

    def lock_user(self, user_id):
        self.locked_users.append(user_id)

    def find_session(self, session_id):
        self.lookups.append(session_id)
        return self.session

    def create_session(self, **values):
        session = SimpleNamespace(
            id=values["session_id"],
            pk=values["session_id"],
            user=values["user"],
            user_id=values["user"].pk,
            space=values["space"],
            space_id=values["space"].id,
            title=values["title"],
        )
        self.created.append(session)
        self.session = session
        return session

    def save_space(self, session, space):
        session.space = space
        session.space_id = space.id
        self.saved_spaces.append((session.id, space.id))


class ChatSessionResolutionServiceTest(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk=11)
        self.space = SimpleNamespace(id=uuid.uuid4())
        self.session_id = uuid.uuid4()
        self.atomic_entries = 0

    @contextmanager
    def atomic(self):
        self.atomic_entries += 1
        yield

    def resolve(self, repository, *, request_space=None, fallback=None):
        return resolve_chat_session(
            user=self.user,
            session_id=self.session_id,
            title="Question",
            request_space=request_space,
            fallback_space_factory=fallback or (lambda: self.space),
            repository=repository,
            atomic_factory=self.atomic,
        )

    def test_serializes_recheck_and_creates_one_session_for_repeated_resolution(self):
        repository = FakeSessionRepository()

        first = self.resolve(repository)
        second = self.resolve(repository)

        self.assertEqual(first.disposition, SessionResolutionDisposition.CREATED)
        self.assertEqual(second.disposition, SessionResolutionDisposition.EXISTING)
        self.assertIs(first.session, second.session)
        self.assertEqual(len(repository.created), 1)
        self.assertEqual(repository.locked_users, [self.user.pk, self.user.pk])
        self.assertEqual(repository.lookups, [self.session_id, self.session_id])
        self.assertEqual(self.atomic_entries, 2)

    def test_foreign_session_is_non_disclosing_and_never_recreated(self):
        other = SimpleNamespace(pk=44)
        foreign_session = SimpleNamespace(
            id=self.session_id,
            user=other,
            user_id=other.pk,
            space=self.space,
            space_id=self.space.id,
        )
        repository = FakeSessionRepository(foreign_session)

        result = self.resolve(repository)

        self.assertEqual(result.disposition, SessionResolutionDisposition.ACCESS_DENIED)
        self.assertIsNone(result.session)
        self.assertEqual(repository.created, [])

    def test_rejects_new_or_legacy_session_when_no_space_can_be_resolved(self):
        new_repository = FakeSessionRepository()
        new_result = self.resolve(
            new_repository,
            request_space=None,
            fallback=lambda: None,
        )
        self.assertEqual(
            new_result.disposition,
            SessionResolutionDisposition.SCOPE_UNAVAILABLE,
        )
        self.assertEqual(new_repository.created, [])

        legacy = SimpleNamespace(
            id=self.session_id,
            user=self.user,
            user_id=self.user.pk,
            space=None,
            space_id=None,
        )
        legacy_repository = FakeSessionRepository(legacy)
        legacy_result = self.resolve(
            legacy_repository,
            request_space=None,
            fallback=lambda: None,
        )
        self.assertEqual(
            legacy_result.disposition,
            SessionResolutionDisposition.SCOPE_UNAVAILABLE,
        )
        self.assertEqual(legacy_repository.saved_spaces, [])


class ChatTurnTransitionTest(SimpleTestCase):
    def test_model_snapshot_uses_the_full_database_field_width(self):
        turn = SimpleNamespace(
            status="accepted",
            error_code="",
            completed_at=None,
            assistant_message=None,
            model_id="",
        )
        model_id = "m" * 160

        transition_chat_turn(turn, "retrieving", model_id=model_id, save=False)

        self.assertEqual(turn.model_id, model_id)

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

    def test_failed_terminal_transition_records_a_terminal_timestamp(self):
        turn = SimpleNamespace(
            status="accepted",
            error_code="",
            completed_at=None,
            assistant_message=None,
            model_id="",
        )
        finished_at = timezone.now()

        transition_chat_turn(
            turn,
            "failed",
            error_code="stream_error",
            save=False,
            now=finished_at,
        )

        self.assertEqual(turn.completed_at, finished_at)
