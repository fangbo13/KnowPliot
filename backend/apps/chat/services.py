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


class InvalidTurnTransitionError(ValueError):
    """Raised when code attempts an invalid Turn lifecycle transition."""


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


def _same_request_identity(turn, *, session, content, answer_mode) -> bool:
    return (
        turn.session_id == session.id
        and turn.question_message.content == content
        and turn.answer_mode == answer_mode
    )


def begin_chat_turn(
    *,
    user,
    session,
    space,
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
        # Locking the user closes the absent-row race for the per-user unique key.
        repository.lock_user(user.pk)
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
