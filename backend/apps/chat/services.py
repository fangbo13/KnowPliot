"""Transactional domain services for durable chat Turns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import ChatSession, ChatTurn, Message

ACTIVE_TURN_STATUSES = frozenset(
    {
        ChatTurn.STATUS_ACCEPTED,
        ChatTurn.STATUS_RETRIEVING,
        ChatTurn.STATUS_REASONING,
        ChatTurn.STATUS_ANSWERING,
        ChatTurn.STATUS_SAVING,
    }
)
RETRYABLE_ERROR_CODES = frozenset(
    {
        "answer_save_error",
        "client_disconnected",
        "connection_error",
        "provider_timeout",
        "provider_unavailable",
        "stream_error",
        "stream_timeout",
        "worker_lost",
    }
)
_SAFE_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,64}$")


class BeginTurnDisposition(StrEnum):
    CREATED = "created"
    RETRY = "retry"
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    TERMINAL = "terminal"
    CONFLICT = "conflict"


class SessionResolutionDisposition(StrEnum):
    CREATED = "created"
    EXISTING = "existing"
    ACCESS_DENIED = "access_denied"
    SCOPE_UNAVAILABLE = "scope_unavailable"


@dataclass(frozen=True)
class BeginTurnResult:
    turn: ChatTurn
    disposition: BeginTurnDisposition

    @property
    def should_generate(self) -> bool:
        return self.disposition in {
            BeginTurnDisposition.CREATED,
            BeginTurnDisposition.RETRY,
        }


@dataclass(frozen=True)
class SessionResolutionResult:
    session: ChatSession | None
    disposition: SessionResolutionDisposition


class InvalidTurnTransitionError(ValueError):
    """Raised when code attempts an invalid Turn lifecycle transition."""


class ChatTurnScopeError(ValueError):
    """Raised when a Turn cannot derive an owned, non-null session scope."""


_ALLOWED_TRANSITIONS = {
    ChatTurn.STATUS_ACCEPTED: {
        ChatTurn.STATUS_RETRIEVING,
        ChatTurn.STATUS_FAILED,
        ChatTurn.STATUS_CANCELLED,
    },
    ChatTurn.STATUS_RETRIEVING: {
        ChatTurn.STATUS_REASONING,
        ChatTurn.STATUS_ANSWERING,
        ChatTurn.STATUS_SAVING,
        ChatTurn.STATUS_FAILED,
        ChatTurn.STATUS_CANCELLED,
    },
    ChatTurn.STATUS_REASONING: {
        ChatTurn.STATUS_ANSWERING,
        ChatTurn.STATUS_SAVING,
        ChatTurn.STATUS_FAILED,
        ChatTurn.STATUS_CANCELLED,
    },
    ChatTurn.STATUS_ANSWERING: {
        ChatTurn.STATUS_SAVING,
        ChatTurn.STATUS_FAILED,
        ChatTurn.STATUS_CANCELLED,
    },
    ChatTurn.STATUS_SAVING: {
        ChatTurn.STATUS_COMPLETED,
        ChatTurn.STATUS_FAILED,
        ChatTurn.STATUS_CANCELLED,
    },
    ChatTurn.STATUS_FAILED: {ChatTurn.STATUS_ACCEPTED},
    ChatTurn.STATUS_CANCELLED: set(),
    ChatTurn.STATUS_COMPLETED: set(),
}


def normalize_error_code(error_code: str) -> str:
    """Keep only stable machine codes; never persist raw exception text."""

    value = (error_code or "").strip().lower()
    return value if _SAFE_ERROR_CODE.fullmatch(value) else "internal_error"


def transition_chat_turn(
    turn: ChatTurn,
    target_status: str,
    *,
    model_id: str | None = None,
    error_code: str = "",
    assistant_message: Message | None = None,
    save: bool = True,
    now=None,
) -> ChatTurn:
    """Apply one validated lifecycle transition to a Turn."""

    current_status = turn.status
    if target_status != current_status and target_status not in _ALLOWED_TRANSITIONS.get(
        current_status, set()
    ):
        raise InvalidTurnTransitionError(f"{current_status} -> {target_status}")

    turn.status = target_status
    if model_id is not None:
        turn.model_id = model_id[:100]
    if assistant_message is not None:
        turn.assistant_message = assistant_message
    if target_status == ChatTurn.STATUS_FAILED:
        turn.error_code = normalize_error_code(error_code)
    elif target_status != ChatTurn.STATUS_CANCELLED:
        turn.error_code = ""
    if target_status == ChatTurn.STATUS_COMPLETED:
        if turn.assistant_message is None:
            raise InvalidTurnTransitionError(
                "completed Turn requires an assistant message"
            )
        turn.completed_at = now or timezone.now()

    if save:
        turn.save(
            update_fields=[
                "status",
                "model_id",
                "assistant_message",
                "error_code",
                "completed_at",
                "updated_at",
            ]
        )
    return turn


class DjangoTurnRepository:
    """Small ORM adapter so decision behavior stays database-free testable."""

    def lock_user(self, user_id):
        get_user_model().objects.select_for_update().only("pk").get(pk=user_id)

    def lock_session(self, session_id):
        return (
            ChatSession.objects.select_for_update()
            .select_related("user", "space")
            .filter(pk=session_id)
            .first()
        )

    def find_turn(self, user, client_request_id):
        return (
            ChatTurn.objects.select_for_update()
            .select_related("session", "question_message", "assistant_message")
            .filter(user=user, client_request_id=client_request_id)
            .first()
        )

    def create_question(self, *, session, space, content):
        return Message.objects.create(
            session=session,
            role="user",
            content=content,
            space=space,
        )

    def create_turn(self, **values):
        return ChatTurn.objects.create(**values)

    def save_retry(self, turn):
        turn.save(
            update_fields=[
                "status",
                "answer_mode",
                "attempt_count",
                "last_event_seq",
                "error_code",
                "model_id",
                "assistant_message",
                "completed_at",
                "updated_at",
            ]
        )

    def touch_session(self, session):
        ChatSession.objects.filter(pk=session.pk).update(updated_at=timezone.now())


class DjangoSessionRepository:
    """Serialize legacy session lookup/backfill/create for one user."""

    def lock_user(self, user_id):
        get_user_model().objects.select_for_update().only("pk").get(pk=user_id)

    def find_session(self, session_id):
        return (
            ChatSession.objects.select_for_update()
            .select_related("user", "space")
            .filter(pk=session_id)
            .first()
        )

    def create_session(self, *, session_id, user, title, space):
        return ChatSession.objects.create(
            id=session_id,
            user=user,
            title=title,
            space=space,
        )

    def save_space(self, session, space):
        session.space = space
        session.save(update_fields=["space"])


def resolve_chat_session(
    *,
    user,
    session_id,
    title: str,
    request_space,
    fallback_space_factory,
    repository: Any | None = None,
    atomic_factory=None,
) -> SessionResolutionResult:
    """Resolve/create one session after serializing concurrent legacy requests."""

    repository = repository or DjangoSessionRepository()
    atomic_factory = atomic_factory or transaction.atomic

    with atomic_factory():
        repository.lock_user(user.pk)
        session = repository.find_session(session_id)
        if session is not None and session.user_id != user.pk:
            return SessionResolutionResult(
                None,
                SessionResolutionDisposition.ACCESS_DENIED,
            )

        if session is not None:
            if session.space_id is None:
                space = request_space or fallback_space_factory()
                if space is None:
                    return SessionResolutionResult(
                        None,
                        SessionResolutionDisposition.SCOPE_UNAVAILABLE,
                    )
                repository.save_space(session, space)
            return SessionResolutionResult(
                session,
                SessionResolutionDisposition.EXISTING,
            )

        space = request_space or fallback_space_factory()
        if space is None:
            return SessionResolutionResult(
                None,
                SessionResolutionDisposition.SCOPE_UNAVAILABLE,
            )
        session = repository.create_session(
            session_id=session_id,
            user=user,
            title=title,
            space=space,
        )
        return SessionResolutionResult(
            session,
            SessionResolutionDisposition.CREATED,
        )


def _same_request_identity(turn, *, session, user, space, content, answer_mode) -> bool:
    return (
        turn.session_id == session.id
        and turn.user_id == user.pk
        and turn.space_id == space.id
        and turn.question_message.content == content
        and turn.answer_mode == answer_mode
    )


def begin_chat_turn(
    *,
    session,
    client_request_id,
    content: str,
    answer_mode: str,
    repository: Any | None = None,
    atomic_factory=None,
) -> BeginTurnResult:
    """Atomically create or classify a Turn without duplicating its question."""

    repository = repository or DjangoTurnRepository()
    atomic_factory = atomic_factory or transaction.atomic

    with atomic_factory():
        expected_user_id = getattr(session, "user_id", None)
        if expected_user_id is None:
            raise ChatTurnScopeError("session_owner_unavailable")

        # User then session is the shared lock order for session resolution and
        # Turn creation. The locked session is the authority for user and space.
        repository.lock_user(expected_user_id)
        locked_session = repository.lock_session(session.pk)
        if (
            locked_session is None
            or locked_session.user_id != expected_user_id
            or locked_session.id != session.id
        ):
            raise ChatTurnScopeError("session_owner_mismatch")
        if locked_session.space_id is None or locked_session.space is None:
            raise ChatTurnScopeError("session_scope_unavailable")

        session = locked_session
        user = locked_session.user
        space = locked_session.space
        turn = repository.find_turn(user, client_request_id)
        if turn is None:
            question_message = repository.create_question(
                session=session,
                space=space,
                content=content,
            )
            turn = repository.create_turn(
                user=user,
                session=session,
                space=space,
                client_request_id=client_request_id,
                question_message=question_message,
                answer_mode=answer_mode,
            )
            repository.touch_session(session)
            return BeginTurnResult(turn, BeginTurnDisposition.CREATED)

        if not _same_request_identity(
            turn,
            session=session,
            user=user,
            space=space,
            content=content,
            answer_mode=answer_mode,
        ):
            return BeginTurnResult(turn, BeginTurnDisposition.CONFLICT)

        if turn.status == ChatTurn.STATUS_COMPLETED:
            return BeginTurnResult(turn, BeginTurnDisposition.COMPLETED)
        if turn.status in ACTIVE_TURN_STATUSES:
            return BeginTurnResult(turn, BeginTurnDisposition.IN_PROGRESS)
        if (
            turn.status == ChatTurn.STATUS_FAILED
            and turn.error_code in RETRYABLE_ERROR_CODES
        ):
            turn.status = ChatTurn.STATUS_ACCEPTED
            turn.answer_mode = answer_mode
            turn.attempt_count += 1
            turn.last_event_seq = 0
            turn.error_code = ""
            turn.model_id = ""
            turn.assistant_message = None
            turn.completed_at = None
            repository.save_retry(turn)
            repository.touch_session(session)
            return BeginTurnResult(turn, BeginTurnDisposition.RETRY)
        return BeginTurnResult(turn, BeginTurnDisposition.TERMINAL)
