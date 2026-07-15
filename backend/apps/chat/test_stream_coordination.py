"""Database-free contracts for Redis coordination and replayable SSE."""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase
from django.utils import timezone

try:
    from apps.chat.coordination import (
        LEASE_RENEW_SECONDS,
        LEASE_TTL_SECONDS,
        CoordinationUnavailableError,
        LeaseLostError,
        RedisSessionLease,
    )
    from apps.chat.stream_events import (
        EVENT_TTL_SECONDS,
        EventStoreUnavailableError,
        ManagedStream,
        RedisTurnEventStore,
        SSEEvent,
        converge_stale_turn,
    )
except ModuleNotFoundError:
    CoordinationUnavailableError = None
    EventStoreUnavailableError = None
    LeaseLostError = None
    RedisSessionLease = None
    RedisTurnEventStore = None
    SSEEvent = None
    ManagedStream = None
    converge_stale_turn = None
    LEASE_TTL_SECONDS = None
    LEASE_RENEW_SECONDS = None
    EVENT_TTL_SECONDS = None


class FakeRedis:
    """Small deterministic Redis surface used by the coordination contracts."""

    def __init__(self):
        self.values = {}
        self.expiries = {}
        self.sorted_sets = {}
        self.eval_calls = []
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("redis://user:secret@example.invalid/0")

    def set(self, key, value, *, nx=False, ex=None):
        self._check()
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expiries[key] = ex
        return True

    def get(self, key):
        self._check()
        return self.values.get(key)

    def eval(self, script, number_of_keys, key, token, ttl=None):
        self._check()
        self.eval_calls.append((script, number_of_keys, key, token, ttl))
        if self.values.get(key) != token:
            return 0
        if ttl is None:
            del self.values[key]
            self.expiries.pop(key, None)
        else:
            self.expiries[key] = int(ttl)
        return 1

    def incr(self, key):
        self._check()
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    def zadd(self, key, mapping):
        self._check()
        self.sorted_sets.setdefault(key, {}).update(mapping)

    def zremrangebyscore(self, key, minimum, maximum):
        self._check()
        entries = self.sorted_sets.setdefault(key, {})
        for member, score in list(entries.items()):
            if float(minimum) <= score <= float(maximum):
                del entries[member]

    def zrange(self, key, start, end):
        self._check()
        entries = self.sorted_sets.get(key, {})
        ordered = sorted(entries, key=lambda member: (entries[member], member))
        return ordered[start:] if end == -1 else ordered[start : end + 1]

    def expire(self, key, seconds):
        self._check()
        self.expiries[key] = seconds

    def delete(self, key):
        self._check()
        self.values.pop(key, None)
        self.expiries.pop(key, None)
        self.sorted_sets.pop(key, None)
        return 1


class RedisSessionLeaseTest(SimpleTestCase):
    def setUp(self):
        self.assertIsNotNone(RedisSessionLease, "Redis lease feature is missing")

    def test_defaults_match_operational_contract(self):
        self.assertEqual(LEASE_TTL_SECONDS, 180)
        self.assertEqual(LEASE_RENEW_SECONDS, 30)

    def test_acquire_uses_nx_and_only_one_owner_wins(self):
        redis = FakeRedis()
        first = RedisSessionLease(redis, "session-1", token_factory=lambda: "owner-a")
        second = RedisSessionLease(redis, "session-1", token_factory=lambda: "owner-b")

        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        self.assertEqual(redis.expiries[first.key], 180)

    def test_renew_and_release_compare_the_owner_token(self):
        redis = FakeRedis()
        lease = RedisSessionLease(redis, "session-1", token_factory=lambda: "owner-a")
        self.assertTrue(lease.acquire())

        redis.values[lease.key] = "other-owner"
        self.assertFalse(lease.renew())
        self.assertFalse(lease.release())
        self.assertEqual(redis.values[lease.key], "other-owner")
        self.assertTrue(all(call[1] == 1 for call in redis.eval_calls))

    def test_renewal_runs_while_provider_iteration_is_blocked(self):
        redis = FakeRedis()
        lease = RedisSessionLease(
            redis,
            "session-1",
            renew_interval=0.01,
            token_factory=lambda: "owner-a",
        )
        self.assertTrue(lease.acquire())
        lease.start_renewal()

        time.sleep(0.035)  # Simulates a provider iterator that has not yielded.
        lease.release()

        renewals = [call for call in redis.eval_calls if call[4] is not None]
        self.assertGreaterEqual(len(renewals), 1)

    def test_renewal_loss_is_observable_after_control_returns(self):
        redis = FakeRedis()
        lease = RedisSessionLease(
            redis,
            "session-1",
            renew_interval=0.01,
            token_factory=lambda: "owner-a",
        )
        self.assertTrue(lease.acquire())
        lease.start_renewal()
        redis.values[lease.key] = "new-owner"
        time.sleep(0.025)

        with self.assertRaises(LeaseLostError):
            lease.ensure_owned()
        lease.release()

    def test_redis_error_fails_closed_without_exposing_connection_text(self):
        redis = FakeRedis()
        redis.fail = True
        lease = RedisSessionLease(redis, "session-1")

        with self.assertRaises(CoordinationUnavailableError) as error:
            lease.acquire()
        self.assertNotIn("secret", str(error.exception))


class ManagedStreamTest(SimpleTestCase):
    def setUp(self):
        self.assertIsNotNone(ManagedStream, "managed stream feature is missing")

    def test_close_releases_even_when_iterator_was_never_started(self):
        release = Mock()
        stream = ManagedStream(iter(["event"]), release)

        stream.close()

        release.assert_called_once_with()

    def test_exhaustion_and_iteration_exception_both_release(self):
        released = Mock()
        stream = ManagedStream(iter(["event"]), released)
        self.assertEqual(next(stream), "event")
        with self.assertRaises(StopIteration):
            next(stream)
        released.assert_called_once_with()

        def broken():
            yield "event"
            raise RuntimeError("provider detail")

        released_on_error = Mock()
        stream = ManagedStream(broken(), released_on_error)
        next(stream)
        with self.assertRaises(RuntimeError):
            next(stream)
        released_on_error.assert_called_once_with()


class RedisTurnEventStoreTest(SimpleTestCase):
    def setUp(self):
        self.assertIsNotNone(RedisTurnEventStore, "event store feature is missing")

    def test_monotonic_ids_sse_shape_and_fifteen_minute_expiry(self):
        redis = FakeRedis()
        now = [1_000.0]
        store = RedisTurnEventStore(redis, uuid.uuid4(), clock=lambda: now[0])

        first = store.append("meta", {"protocol_version": 2})
        now[0] += 1
        second = store.append("phase", {"phase": "retrieving"})

        self.assertEqual((first.sequence, second.sequence), (1, 2))
        self.assertEqual(EVENT_TTL_SECONDS, 900)
        self.assertEqual(redis.expiries[store.events_key], 900)
        self.assertEqual(
            second.to_sse(),
            'id: 2\nevent: phase\ndata: {"phase": "retrieving"}\n\n',
        )

    def test_replay_returns_only_events_after_cursor(self):
        redis = FakeRedis()
        store = RedisTurnEventStore(redis, uuid.uuid4(), clock=lambda: 1_000.0)
        store.append("meta", {"turn_id": "safe"})
        store.append("phase", {"phase": "retrieving"})
        store.append("done", {"message_id": "m"}, terminal=True)

        replay = store.replay(after=1)

        self.assertEqual([event.sequence for event in replay], [2, 3])
        self.assertEqual([event.name for event in replay], ["phase", "done"])

    def test_retry_clears_prior_attempt_events_but_keeps_monotonic_sequence(self):
        redis = FakeRedis()
        store = RedisTurnEventStore(redis, uuid.uuid4())
        store.append("meta", {"attempt": 1})
        store.append_error("stream_error")

        store.clear_events()
        current = store.append("meta", {"attempt": 2})

        self.assertEqual(current.sequence, 3)
        self.assertEqual(
            [(event.sequence, event.name) for event in store.replay()],
            [(3, "meta")],
        )

    def test_corrupt_replay_record_fails_with_safe_store_error(self):
        redis = FakeRedis()
        store = RedisTurnEventStore(redis, uuid.uuid4())
        redis.sorted_sets[store.events_key] = {"corrupt:password=secret": 1.0}

        with self.assertRaises(EventStoreUnavailableError) as error:
            store.replay()

        self.assertNotIn("secret", str(error.exception))

    def test_expired_members_are_removed_and_payload_rejects_reasoning(self):
        redis = FakeRedis()
        now = [1_000.0]
        store = RedisTurnEventStore(redis, uuid.uuid4(), clock=lambda: now[0])
        store.append("meta", {"turn_id": "safe"})
        now[0] += 901
        store.append("done", {"message_id": "m"}, terminal=True)

        self.assertEqual([event.name for event in store.replay(after=0)], ["done"])
        with self.assertRaises(ValueError):
            store.append("phase", {"reasoning": "private chain of thought"})
        with self.assertRaises(ValueError):
            store.append("unknown", {})

    def test_error_event_is_stable_and_does_not_forward_raw_exception(self):
        redis = FakeRedis()
        store = RedisTurnEventStore(redis, uuid.uuid4())
        event = store.append_error("stream_error", RuntimeError("password=secret"))

        self.assertEqual(event.data, {"code": "stream_error", "retryable": True})
        self.assertNotIn("secret", event.to_sse())

    def test_redis_failure_is_safe_and_fail_closed(self):
        redis = FakeRedis()
        redis.fail = True
        store = RedisTurnEventStore(redis, uuid.uuid4())
        with self.assertRaises(EventStoreUnavailableError) as error:
            store.append("meta", {})
        self.assertNotIn("secret", str(error.exception))

    def test_checkpoint_batches_tokens_and_flushes_terminal_sequence(self):
        redis = FakeRedis()
        checkpoints = []
        store = RedisTurnEventStore(
            redis,
            uuid.uuid4(),
            checkpoint=checkpoints.append,
        )
        for _ in range(24):
            store.append("answer_delta", {"text": "x"})
        self.assertEqual(checkpoints, [])
        store.append("answer_delta", {"text": "x"})
        self.assertEqual(checkpoints, [25])
        store.append("done", {"message_id": "m"}, terminal=True)
        self.assertEqual(checkpoints, [25, 26])

    def test_checkpoint_failure_is_safe_while_redis_event_remains_recoverable(self):
        redis = FakeRedis()
        store = RedisTurnEventStore(
            redis,
            uuid.uuid4(),
            checkpoint=Mock(side_effect=RuntimeError("database password=secret")),
        )

        with self.assertRaises(EventStoreUnavailableError) as error:
            store.append("done", {"message_id": "m"}, terminal=True)

        self.assertNotIn("secret", str(error.exception))
        self.assertEqual([event.name for event in store.replay()], ["done"])


class StaleTurnRecoveryTest(SimpleTestCase):
    def setUp(self):
        self.assertIsNotNone(converge_stale_turn, "stale recovery feature is missing")

    def _turn(self):
        now = timezone.now()
        return SimpleNamespace(
            status="answering",
            session_id=uuid.uuid4(),
            updated_at=now - timedelta(seconds=181),
            error_code="",
        )

    def test_definitely_absent_lease_marks_old_active_turn_worker_lost(self):
        turn = self._turn()
        save = Mock()
        turn.save = save

        changed = converge_stale_turn(
            turn,
            lease_exists=lambda _session_id: False,
            now=timezone.now(),
        )

        self.assertTrue(changed)
        self.assertEqual(turn.status, "failed")
        self.assertEqual(turn.error_code, "worker_lost")
        save.assert_called_once()

    def test_redis_error_is_not_mistaken_for_absent_lease(self):
        turn = self._turn()
        turn.save = Mock()

        changed = converge_stale_turn(
            turn,
            lease_exists=lambda _session_id: (_ for _ in ()).throw(
                CoordinationUnavailableError()
            ),
            now=timezone.now(),
        )

        self.assertFalse(changed)
        self.assertEqual(turn.status, "answering")
        turn.save.assert_not_called()
