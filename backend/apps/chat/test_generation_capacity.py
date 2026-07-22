"""Unit contracts for the Redis-backed generation admission gate."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.chat.capacity import (
    GenerationCapacityController,
    GenerationCapacityUnavailable,
)


class FakeCapacityRedis:
    """Deterministic subset of Redis used by the capacity controller."""

    def __init__(self):
        self.members: dict[str, dict[str, float]] = {}
        self.fail = False

    def eval(self, script, numkeys, *args):
        if self.fail:
            raise ConnectionError("redis://user:secret@example.invalid/0")
        if numkeys != 1:
            raise AssertionError("capacity scripts must use exactly one key")

        key, *argv = args
        members = self.members.setdefault(str(key), {})
        if "capacity:reserve" in script:
            now, expires, limit, member = argv
            now = float(now)
            for existing, expiry in list(members.items()):
                if expiry <= now:
                    del members[existing]
            member = str(member)
            if member in members:
                members[member] = float(expires)
                return [1, len(members)]
            if len(members) >= int(limit):
                return [0, len(members)]
            members[member] = float(expires)
            return [1, len(members)]
        if "capacity:renew" in script:
            now, expires, member = argv
            now = float(now)
            for existing, expiry in list(members.items()):
                if expiry <= now:
                    del members[existing]
            member = str(member)
            if member not in members:
                return 0
            members[member] = float(expires)
            return 1
        if "capacity:release" in script:
            return int(members.pop(str(argv[0]), None) is not None)
        if "capacity:outstanding" in script:
            now = float(argv[0])
            for existing, expiry in list(members.items()):
                if expiry <= now:
                    del members[existing]
            return len(members)
        raise AssertionError("unexpected capacity script")


class GenerationCapacityControllerTest(SimpleTestCase):
    def setUp(self):
        self.now = [1_000.0]
        self.redis = FakeCapacityRedis()
        self.gate = GenerationCapacityController(
            self.redis,
            max_outstanding=2,
            ttl_seconds=180,
            clock=lambda: self.now[0],
        )

    def test_reserve_rejects_at_limit_and_prunes_expired(self):
        self.assertTrue(self.gate.reserve("turn-a").accepted)
        self.assertTrue(self.gate.reserve("turn-b").accepted)

        rejected = self.gate.reserve("turn-c")

        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.outstanding, 2)
        self.assertEqual(rejected.retry_after_seconds, 5)

        self.now[0] += 181
        accepted = self.gate.reserve("turn-c")
        self.assertTrue(accepted.accepted)
        self.assertEqual(accepted.outstanding, 1)
        self.assertEqual(self.gate.outstanding(), 1)

    def test_duplicate_reservation_is_idempotent_and_renews_expiry(self):
        first = self.gate.reserve("turn-a")
        self.now[0] += 60
        duplicate = self.gate.reserve("turn-a")

        self.assertTrue(first.accepted)
        self.assertTrue(duplicate.accepted)
        self.assertEqual(duplicate.outstanding, 1)
        self.assertEqual(self.gate.outstanding(), 1)

        self.now[0] += 121
        self.assertEqual(self.gate.outstanding(), 1)

    def test_renew_only_succeeds_for_a_live_reservation(self):
        self.assertFalse(self.gate.renew("missing"))
        self.gate.reserve("turn-a")
        self.now[0] += 179
        self.assertTrue(self.gate.renew("turn-a"))
        self.now[0] += 2
        self.assertEqual(self.gate.outstanding(), 1)

    def test_release_is_idempotent(self):
        self.gate.reserve("turn-a")

        self.assertTrue(self.gate.release("turn-a"))
        self.assertFalse(self.gate.release("turn-a"))
        self.assertEqual(self.gate.outstanding(), 0)

    def test_invalid_limits_are_rejected_before_redis_is_used(self):
        for kwargs in (
            {"max_outstanding": 0, "ttl_seconds": 180},
            {"max_outstanding": 2, "ttl_seconds": 0},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                GenerationCapacityController(self.redis, **kwargs)

    def test_redis_errors_fail_closed_without_exposing_connection_details(self):
        self.redis.fail = True

        operations = (
            lambda: self.gate.reserve("turn-a"),
            lambda: self.gate.renew("turn-a"),
            lambda: self.gate.release("turn-a"),
            self.gate.outstanding,
        )
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(
                GenerationCapacityUnavailable
            ) as captured:
                operation()
            self.assertNotIn("secret", str(captured.exception))
            self.assertNotIn("redis://", str(captured.exception))
