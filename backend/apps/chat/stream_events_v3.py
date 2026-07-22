"""Replayable v3 chat events backed by Redis Streams."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .stream_events import (
    EVENT_CHECKPOINT_INTERVAL,
    EVENT_NAMES,
    EventStoreUnavailableError,
    SSEEvent,
    _validate_safe_payload,
)


_APPEND_V3_SCRIPT = """
-- CHAT_EVENT_APPEND_V3
local sequence_type = redis.call('TYPE', KEYS[1])['ok']
local stream_type = redis.call('TYPE', KEYS[2])['ok']
if sequence_type ~= 'none' and sequence_type ~= 'string' then
  return redis.error_reply('invalid v3 sequence key type')
end
if stream_type ~= 'none' and stream_type ~= 'stream' then
  return redis.error_reply('invalid v3 event key type')
end

local sequence = tonumber(redis.call('GET', KEYS[1]) or '0')
local ttl = tonumber(ARGV[3])
local max_length = tonumber(ARGV[4])
if sequence == nil or ttl == nil or max_length == nil then
  return redis.error_reply('invalid v3 event append arguments')
end

sequence = sequence + 1
local stream_id = tostring(sequence) .. '-0'
redis.call('SET', KEYS[1], sequence, 'EX', ttl)
redis.call('XADD', KEYS[2], stream_id, 'event', ARGV[1], 'data', ARGV[2])
redis.call('XTRIM', KEYS[2], 'MAXLEN', max_length)
redis.call('EXPIRE', KEYS[2], ttl)
return sequence
"""


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    raise ValueError("invalid Redis Stream text value")


def _decode_stream_rows(rows: Sequence[Any]) -> list[SSEEvent]:
    events: list[SSEEvent] = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise ValueError("invalid Redis Stream row")
        stream_id, fields = row
        if not isinstance(fields, Mapping):
            raise ValueError("invalid Redis Stream fields")
        stream_id = _text(stream_id)
        sequence_text, separator, sub_sequence = stream_id.partition("-")
        if (
            separator != "-"
            or not sequence_text.isdigit()
            or int(sequence_text) <= 0
            or sub_sequence != "0"
        ):
            raise ValueError("invalid Redis Stream event ID")

        normalized = {_text(key): value for key, value in fields.items()}
        if "event" not in normalized or "data" not in normalized:
            raise ValueError("incomplete Redis Stream event")
        name = _text(normalized["event"])
        data = json.loads(_text(normalized["data"]))
        sequence = int(sequence_text)
        record = json.dumps(
            {"id": sequence, "event": name, "data": data},
            ensure_ascii=False,
        )
        events.append(SSEEvent.from_record(record))
    return events


def _cursor(after: int) -> str:
    if isinstance(after, bool) or not isinstance(after, int) or after < 0:
        raise ValueError("event cursor must be a non-negative integer")
    return f"{after}-0"


class RedisTurnStreamV3:
    """Redis Stream event log for a single protocol-v3 Turn."""

    def __init__(
        self,
        client: Any,
        turn_id: object,
        *,
        ttl_seconds: int,
        max_length: int,
        checkpoint: Callable[[int], None] | None = None,
    ):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_length <= 0:
            raise ValueError("max_length must be positive")
        self.client = client
        self.turn_id = str(turn_id)
        self.sequence_key = f"chat:v3:turn:{self.turn_id}:seq"
        self.events_key = f"chat:v3:turn:{self.turn_id}:events"
        self.ttl_seconds = int(ttl_seconds)
        self.max_length = int(max_length)
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
        if not isinstance(data, (dict, list)):
            raise ValueError("invalid SSE event payload")
        _validate_safe_payload(data)
        try:
            sequence = int(
                self.client.eval(
                    _APPEND_V3_SCRIPT,
                    2,
                    self.sequence_key,
                    self.events_key,
                    name,
                    json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    self.ttl_seconds,
                    self.max_length,
                )
            )
        except Exception as exc:
            raise EventStoreUnavailableError() from exc

        if self.checkpoint and (
            terminal or sequence % EVENT_CHECKPOINT_INTERVAL == 0
        ):
            try:
                self.checkpoint(sequence)
            except Exception as exc:
                raise EventStoreUnavailableError() from exc
        return SSEEvent(sequence=sequence, name=name, data=data)

    def replay(self, *, after: int = 0) -> list[SSEEvent]:
        cursor = _cursor(after)
        try:
            rows = self.client.xrange(
                self.events_key,
                min=f"({cursor}",
                max="+",
            )
            return _decode_stream_rows(rows)
        except Exception as exc:
            raise EventStoreUnavailableError() from exc

    def read(self, *, after: int = 0, block_ms: int = 15_000) -> list[SSEEvent]:
        cursor = _cursor(after)
        if block_ms < 0:
            raise ValueError("block_ms must be non-negative")
        try:
            result = self.client.xread(
                {self.events_key: cursor},
                block=block_ms,
                count=256,
            )
            if not result:
                return []
            rows: list[Any] = []
            for stream in result:
                if not isinstance(stream, (tuple, list)) or len(stream) != 2:
                    raise ValueError("invalid XREAD response")
                rows.extend(stream[1])
            return _decode_stream_rows(rows)
        except Exception as exc:
            raise EventStoreUnavailableError() from exc


class AnswerDeltaBatcher:
    """Coalesce small model deltas to reduce Redis and SSE write amplification."""

    def __init__(
        self,
        *,
        max_delay_seconds: float = 0.05,
        max_chars: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ):
        if max_delay_seconds <= 0:
            raise ValueError("max_delay_seconds must be positive")
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        self.max_delay_seconds = float(max_delay_seconds)
        self.max_chars = int(max_chars)
        self.clock = clock
        self._parts: list[str] = []
        self._char_count = 0
        self._started_at: float | None = None

    def push(self, text: str) -> str | None:
        if not isinstance(text, str):
            raise TypeError("answer delta must be text")
        if not text:
            return None
        now = self.clock()
        if not self._parts:
            self._started_at = now
        self._parts.append(text)
        self._char_count += len(text)
        elapsed = now - self._started_at if self._started_at is not None else 0
        if self._char_count >= self.max_chars or elapsed >= self.max_delay_seconds:
            return self.flush()
        return None

    def flush(self) -> str | None:
        if not self._parts:
            return None
        text = "".join(self._parts)
        self._parts.clear()
        self._char_count = 0
        self._started_at = None
        return text
