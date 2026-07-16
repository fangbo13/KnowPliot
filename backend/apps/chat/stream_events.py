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
_APPEND_SCRIPT = """
-- CHAT_EVENT_APPEND_V2
local sequence_type = redis.call('TYPE', KEYS[1])['ok']
local events_type = redis.call('TYPE', KEYS[2])['ok']
if sequence_type ~= 'none' and sequence_type ~= 'string' then
  return redis.error_reply('invalid sequence key type')
end
if events_type ~= 'none' and events_type ~= 'zset' then
  return redis.error_reply('invalid events key type')
end

local durable_sequence = tonumber(ARGV[1])
local now = tonumber(ARGV[4])
local cutoff = tonumber(ARGV[5])
local ttl = tonumber(ARGV[6])
local data = cjson.decode(ARGV[3])
if durable_sequence == nil or now == nil or cutoff == nil or ttl == nil then
  return redis.error_reply('invalid event append arguments')
end

local redis_sequence = tonumber(redis.call('GET', KEYS[1]) or '0')
if redis_sequence == nil then
  return redis.error_reply('invalid sequence value')
end
local sequence = math.max(redis_sequence, durable_sequence) + 1
local record = cjson.encode({id=sequence, event=ARGV[2], data=data})
local member = string.format('%020d', sequence) .. ':' .. record

redis.call('SET', KEYS[1], sequence)
redis.call('ZADD', KEYS[2], now, member)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', cutoff)
redis.call('EXPIRE', KEYS[2], ttl)
return {sequence, record}
"""


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
        if not isinstance(record, dict):
            raise ValueError("invalid SSE record")
        sequence = record.get("id")
        name = record.get("event")
        data = record.get("data")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            raise ValueError("invalid SSE sequence")
        if name not in EVENT_NAMES:
            raise ValueError("invalid SSE event type")
        if not isinstance(data, (dict, list)):
            raise ValueError("invalid SSE event payload")
        _validate_safe_payload(data)
        return cls(
            sequence=sequence,
            name=name,
            data=data,
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
        initial_sequence: int = 0,
    ):
        self.client = client
        self.turn_id = str(turn_id)
        self.events_key = f"chat:turn:{self.turn_id}:events"
        self.sequence_key = f"chat:turn:{self.turn_id}:seq"
        self.clock = clock or time.time
        self.checkpoint = checkpoint
        self.initial_sequence = max(0, int(initial_sequence))

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
            result = self.client.eval(
                _APPEND_SCRIPT,
                2,
                self.sequence_key,
                self.events_key,
                self.initial_sequence,
                name,
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                now,
                now - EVENT_TTL_SECONDS,
                EVENT_TTL_SECONDS,
            )
            sequence = int(result[0])
            event = SSEEvent(sequence, name, data)
        except Exception as exc:
            raise EventStoreUnavailableError() from exc
        if self.checkpoint and (
            terminal or sequence % EVENT_CHECKPOINT_INTERVAL == 0
        ):
            try:
                self.checkpoint(sequence)
            except Exception as exc:
                raise EventStoreUnavailableError() from exc
            self.initial_sequence = max(self.initial_sequence, sequence)
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
                prefix, record = member.split(":", 1)
                if len(prefix) != 20 or not prefix.isdigit():
                    raise ValueError("invalid event member prefix")
                event = SSEEvent.from_record(record)
                if int(prefix) != event.sequence:
                    raise ValueError("event sequence mismatch")
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


class DjangoStaleTurnRepository:
    """Optimistically converge only the same still-stale database row."""

    def mark_failed_if_unchanged(self, turn, *, cutoff, now) -> int:
        from .models import ChatTurn

        return ChatTurn.objects.filter(
            pk=turn.pk,
            status=turn.status,
            updated_at=turn.updated_at,
            updated_at__lte=cutoff,
        ).update(
            status=ChatTurn.STATUS_FAILED,
            error_code="worker_lost",
            completed_at=now,
            updated_at=now,
        )

    def refresh(self, turn) -> None:
        turn.refresh_from_db()


def converge_stale_turn(
    turn: Any,
    *,
    lease_exists: Callable[[object], bool],
    now,
    lease_ttl_seconds: int = LEASE_TTL_SECONDS,
    repository: Any | None = None,
) -> bool:
    """Fail an old active Turn only when Redis proves its lease is absent."""

    repository = repository or DjangoStaleTurnRepository()
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
    cutoff = now - timedelta(seconds=lease_ttl_seconds)
    updated = repository.mark_failed_if_unchanged(
        turn,
        cutoff=cutoff,
        now=now,
    )
    if not updated:
        repository.refresh(turn)
        return False
    turn.status = "failed"
    turn.error_code = "worker_lost"
    turn.completed_at = now
    turn.updated_at = now
    return True
