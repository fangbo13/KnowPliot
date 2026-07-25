"""Database-free contracts for replayable v3 Redis Streams."""

from __future__ import annotations

import json
import uuid

from django.test import SimpleTestCase

from apps.chat.stream_events import EventStoreUnavailableError
from apps.chat.stream_events_v3 import AnswerDeltaBatcher, RedisTurnStreamV3


class FakeStreamRedis:
    def __init__(self):
        self.sequences: dict[str, int] = {}
        self.streams: dict[str, list[tuple[bytes, dict[bytes, bytes]]]] = {}
        self.expiries: dict[str, int] = {}
        self.fail = False

    def eval(self, script, numkeys, *args):
        if self.fail:
            raise ConnectionError("redis://user:secret@example.invalid/0")
        if "CHAT_EVENT_APPEND_V3" not in script or numkeys != 2:
            raise AssertionError("unexpected stream script")
        sequence_key, events_key, name, encoded, ttl, max_length = args
        sequence_key = str(sequence_key)
        events_key = str(events_key)
        sequence = self.sequences.get(sequence_key, 0) + 1
        self.sequences[sequence_key] = sequence
        row = (
            f"{sequence}-0".encode(),
            {
                b"event": str(name).encode(),
                b"data": str(encoded).encode(),
            },
        )
        rows = self.streams.setdefault(events_key, [])
        rows.append(row)
        del rows[: max(0, len(rows) - int(max_length))]
        self.expiries[sequence_key] = int(ttl)
        self.expiries[events_key] = int(ttl)
        return sequence

    def xrange(self, key, min="-", max="+"):
        if self.fail:
            raise ConnectionError("redis unavailable")
        after = 0
        if isinstance(min, str) and min.startswith("("):
            after = int(min[1:].split("-", 1)[0])
        return [
            row
            for row in self.streams.get(str(key), [])
            if int(row[0].decode().split("-", 1)[0]) > after
        ]

    def xread(self, streams, block=None, count=None):
        if self.fail:
            raise ConnectionError("redis unavailable")
        key, cursor = next(iter(streams.items()))
        after = int(str(cursor).split("-", 1)[0])
        rows = [
            row
            for row in self.streams.get(str(key), [])
            if int(row[0].decode().split("-", 1)[0]) > after
        ][:count]
        return [(str(key).encode(), rows)] if rows else []


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class RedisTurnStreamV3Test(SimpleTestCase):
    def setUp(self):
        self.redis = FakeStreamRedis()
        self.turn_id = uuid.uuid4()
        self.store = RedisTurnStreamV3(
            self.redis,
            self.turn_id,
            ttl_seconds=900,
            max_length=4096,
        )

    def test_stream_replays_and_reads_from_integer_cursor(self):
        first = self.store.append("phase", {"phase": "queued"})
        second = self.store.append("answer_delta", {"text": "hello"})

        self.assertEqual([first.sequence, second.sequence], [1, 2])
        self.assertEqual(
            [event.sequence for event in self.store.replay(after=1)],
            [2],
        )
        self.assertEqual(
            [event.sequence for event in self.store.read(after=0, block_ms=25)],
            [1, 2],
        )
        self.assertEqual(self.store.read(after=2, block_ms=25), [])

    def test_forbidden_payload_and_unknown_event_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.append("answer_delta", {"reasoning": "private"})
        with self.assertRaises(ValueError):
            self.store.append("unknown", {"value": "no"})
        self.assertEqual(self.store.replay(), [])

    def test_terminal_and_interval_events_checkpoint_sequence(self):
        checkpoints = []
        store = RedisTurnStreamV3(
            self.redis,
            self.turn_id,
            ttl_seconds=900,
            max_length=4096,
            checkpoint=checkpoints.append,
        )
        for item in range(25):
            store.append("answer_delta", {"text": str(item)})
        store.append("done", {"message_id": "safe"}, terminal=True)

        self.assertEqual(checkpoints, [25, 26])

    def test_stream_honours_4096_entry_trim_and_15_minute_ttl(self):
        for item in range(4097):
            self.store.append("answer_delta", {"text": str(item)})

        replay = self.store.replay()
        self.assertEqual(len(replay), 4096)
        self.assertEqual(replay[0].sequence, 2)
        self.assertEqual(replay[-1].sequence, 4097)
        self.assertEqual(self.redis.expiries[self.store.sequence_key], 900)
        self.assertEqual(self.redis.expiries[self.store.events_key], 900)

    def test_malformed_stream_records_fail_closed(self):
        self.redis.streams[self.store.events_key] = [
            (b"1-0", {b"event": b"phase"}),
        ]

        with self.assertRaises(EventStoreUnavailableError):
            self.store.replay()

    def test_redis_and_checkpoint_failures_are_wrapped_safely(self):
        self.redis.fail = True
        operations = (
            lambda: self.store.append("phase", {"phase": "queued"}),
            self.store.replay,
            self.store.read,
        )
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(
                EventStoreUnavailableError
            ) as captured:
                operation()
            self.assertNotIn("secret", str(captured.exception))

        checkpoint_store = RedisTurnStreamV3(
            FakeStreamRedis(),
            self.turn_id,
            ttl_seconds=900,
            max_length=4096,
            checkpoint=lambda _sequence: (_ for _ in ()).throw(RuntimeError()),
        )
        with self.assertRaises(EventStoreUnavailableError):
            checkpoint_store.append("done", {"message_id": "safe"}, terminal=True)

    def test_nonzero_stream_sub_sequence_is_rejected(self):
        payload = json.dumps({"phase": "queued"}).encode()
        self.redis.streams[self.store.events_key] = [
            (b"2-1", {b"event": b"phase", b"data": payload}),
        ]

        with self.assertRaises(EventStoreUnavailableError):
            self.store.replay()


class AnswerDeltaBatcherTest(SimpleTestCase):
    def test_flushes_on_size_or_50_milliseconds(self):
        clock = FakeClock()
        batch = AnswerDeltaBatcher(
            max_delay_seconds=0.05,
            max_chars=5,
            clock=clock,
        )

        self.assertIsNone(batch.push("ab"))
        self.assertEqual(batch.push("cde"), "abcde")
        self.assertIsNone(batch.push("x"))
        clock.advance(0.05)
        self.assertEqual(batch.push("y"), "xy")

    def test_flush_and_empty_input_are_idempotent(self):
        batch = AnswerDeltaBatcher(max_delay_seconds=0.05, max_chars=5)

        self.assertIsNone(batch.push(""))
        self.assertIsNone(batch.flush())
        self.assertIsNone(batch.push("ab"))
        self.assertEqual(batch.flush(), "ab")
        self.assertIsNone(batch.flush())

    def test_invalid_batch_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            AnswerDeltaBatcher(max_delay_seconds=0, max_chars=5)
        with self.assertRaises(ValueError):
            AnswerDeltaBatcher(max_delay_seconds=0.05, max_chars=0)
