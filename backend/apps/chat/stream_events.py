"""Safe replayable chat events and streaming resource lifecycle helpers."""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from .coordination import LEASE_TTL_SECONDS, CoordinationUnavailableError

EVENT_TTL_SECONDS = 15 * 60
EVENT_CHECKPOINT_INTERVAL = 25
EVENT_NAMES = frozenset(
    {
        "meta",
        "phase",
        "answer_delta",
        "citations",
        "quality",
        "usage",
        "done",
        "error",
    }
)
_FORBIDDEN_KEYS = frozenset(
    {
        "chain_of_thought",
        "exception",
        "prompt",
        "raw_exception",
        "raw_reasoning",
        "reasoning",
        "system_prompt",
    }
)
_SAFE_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,64}$")
_ACTIVE_STATUSES = frozenset(
    {"accepted", "retrieving", "reasoning", "answering", "saving"}
)


class EventStoreUnavailableError(RuntimeError):
    def __init__(self):
        super().__init__("chat_event_store_unavailable")


def _validate_safe_payload(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                raise ValueError("unsafe event payload field")
            _validate_safe_payload(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _validate_safe_payload(nested)


@dataclass(frozen=True)
class SSEEvent:
    sequence: int
    name: str
    data: dict[str, Any] | list[Any]

    def to_sse(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"id: {self.sequence}\nevent: {self.name}\ndata: {payload}\n\n"

    def to_record(self) -> str:
        return json.dumps(
            {"id": self.sequence, "event": self.name, "data": self.data},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_record(cls, value: str | bytes) -> SSEEvent:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        record = json.loads(value)
        return cls(
            sequence=int(record["id"]),
            name=record["event"],
            data=record["data"],
        )


class RedisTurnEventStore:
    """Redis-authoritative 15-minute event buffer for one Turn."""

    def __init__(
        self,
        client: Any,
        turn_id: object,
        *,
        clock: Callable[[], float] | None = None,
        checkpoint: Callable[[int], None] | None = None,
    ):
        self.client = client
        self.turn_id = str(turn_id)
        self.events_key = f"chat:turn:{self.turn_id}:events"
        self.sequence_key = f"chat:turn:{self.turn_id}:seq"
        self.clock = clock or time.time
        self.checkpoint = checkpoint

    def append(
        self,
        name: str,
        data: dict[str, Any] | list[Any],
        *,
        terminal: bool = False,
    ) -> SSEEvent:
        if name not in EVENT_NAMES:
            raise ValueError("unsupported SSE event type")
        _validate_safe_payload(data)
        now = self.clock()
        try:
            sequence = int(self.client.incr(self.sequence_key))
            event = SSEEvent(sequence, name, data)
            member = f"{sequence:020d}:{event.to_record()}"
            self.client.zadd(self.events_key, {member: now})
            self.client.zremrangebyscore(
                self.events_key,
                float("-inf"),
                now - EVENT_TTL_SECONDS,
            )
            self.client.expire(self.events_key, EVENT_TTL_SECONDS)
            self.client.expire(self.sequence_key, EVENT_TTL_SECONDS)
        except Exception as exc:
            raise EventStoreUnavailableError() from exc
        if self.checkpoint and (
            terminal or sequence % EVENT_CHECKPOINT_INTERVAL == 0
        ):
            try:
                self.checkpoint(sequence)
            except Exception as exc:
                raise EventStoreUnavailableError() from exc
        return event

    def append_error(self, code: str, _exception: Exception | None = None) -> SSEEvent:
        normalized = code if _SAFE_ERROR_CODE.fullmatch(code or "") else "internal_error"
        return self.append(
            "error",
            {"code": normalized, "retryable": True},
            terminal=True,
        )

    def clear_events(self) -> None:
        """Drop a prior attempt's events without resetting the Turn sequence."""

        try:
            self.client.delete(self.events_key)
        except Exception as exc:
            raise EventStoreUnavailableError() from exc

    def replay(self, *, after: int = 0) -> list[SSEEvent]:
        try:
            members = self.client.zrange(self.events_key, 0, -1)
            events = []
            for member in members:
                if isinstance(member, bytes):
                    member = member.decode("utf-8")
                _, record = member.split(":", 1)
                event = SSEEvent.from_record(record)
                if event.sequence > after:
                    events.append(event)
        except Exception as exc:
            raise EventStoreUnavailableError() from exc
        return sorted(events, key=lambda event: event.sequence)


class ManagedStream(Iterator[Any]):
    """Iterator that closes its source and owned resources exactly once."""

    def __init__(self, source: Iterator[Any], on_close: Callable[[], Any]):
        self._source = iter(source)
        self._on_close = on_close
        self._closed = False
        self._lock = threading.Lock()

    def __iter__(self):
        return self

    def __next__(self):
        if self._closed:
            raise StopIteration
        try:
            return next(self._source)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            closer = getattr(self._source, "close", None)
            if closer:
                closer()
        finally:
            self._on_close()


def converge_stale_turn(
    turn: Any,
    *,
    lease_exists: Callable[[object], bool],
    now,
    lease_ttl_seconds: int = LEASE_TTL_SECONDS,
) -> bool:
    """Fail an old active Turn only when Redis proves its lease is absent."""

    if turn.status not in _ACTIVE_STATUSES:
        return False
    if turn.updated_at is None:
        return False
    if now - turn.updated_at <= timedelta(seconds=lease_ttl_seconds):
        return False
    try:
        present = lease_exists(turn.session_id)
    except CoordinationUnavailableError:
        return False
    if present:
        return False
    turn.status = "failed"
    turn.error_code = "worker_lost"
    turn.completed_at = now
    turn.save(
        update_fields=["status", "error_code", "completed_at", "updated_at"]
    )
    return True
