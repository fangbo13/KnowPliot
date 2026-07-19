"""Real Redis coordination/replay/rate-limit profile.

Run only against an explicitly configured shared Redis service::

    KNOWPILOT_REDIS_INTEGRATION=1 python manage.py test \
        apps.chat.test_redis_integration --settings=config.settings.docker

The default unit profile skips this module; FakeRedis or LocMemCache cannot
provide the multi-client evidence asserted here.
"""

from __future__ import annotations

import os
import queue
import threading
import time
import unittest
import uuid
from types import SimpleNamespace

from django.core.cache import caches
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.chat.coordination import RedisSessionLease, create_redis_client
from apps.chat.stream_events import EVENT_TTL_SECONDS, RedisTurnEventStore
from apps.core.throttling import AuthenticatedReadBurstThrottle


@unittest.skipUnless(
    os.environ.get("KNOWPILOT_REDIS_INTEGRATION") == "1",
    "requires explicit real Redis integration profile",
)
class RedisMultiWorkerIntegrationTests(SimpleTestCase):
    def setUp(self):
        self.clients = [create_redis_client() for _ in range(6)]
        for client in self.clients:
            self.assertTrue(client.ping())
        self.session_id = uuid.uuid4()
        self.turn_id = uuid.uuid4()
        self.throttle_user_id = f"redis-integration-{uuid.uuid4()}"

    def tearDown(self):
        keys = [
            f"chat:session:{self.session_id}:turn",
            f"chat:turn:{self.turn_id}:events",
            f"chat:turn:{self.turn_id}:seq",
        ]
        for client in self.clients:
            client.delete(*keys)
            close = getattr(client, "close", None)
            if close:
                close()
        throttle = AuthenticatedReadBurstThrottle()
        request = self._request()
        throttle.cache = caches["default"]
        throttle.cache.delete(throttle.get_cache_key(request, None))

    def _request(self):
        request = APIRequestFactory().get("/api/v1/admin/example/")
        request.user = SimpleNamespace(
            is_authenticated=True,
            pk=self.throttle_user_id,
        )
        return request

    def test_independent_clients_contend_for_one_renewable_session_lease(self):
        barrier = threading.Barrier(2)
        outcomes: queue.Queue[tuple[int, bool]] = queue.Queue()
        leases = [
            RedisSessionLease(
                self.clients[index],
                self.session_id,
                ttl_seconds=3,
                token_factory=lambda index=index: f"worker-{index}",
            )
            for index in range(2)
        ]

        def acquire(index):
            barrier.wait(timeout=5)
            outcomes.put((index, leases[index].acquire()))

        threads = [threading.Thread(target=acquire, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "Redis lease contention did not finish")

        results = [outcomes.get_nowait(), outcomes.get_nowait()]
        self.assertEqual(sum(acquired for _, acquired in results), 1)
        winner = next(index for index, acquired in results if acquired)
        loser = 1 - winner
        self.assertFalse(leases[loser].release())

        time.sleep(1.1)
        self.assertTrue(leases[winner].renew())
        self.assertGreater(self.clients[winner].pttl(leases[winner].key), 1_500)
        leases[winner].ensure_owned()
        self.assertTrue(leases[winner].release())

        replacement = RedisSessionLease(
            self.clients[2],
            self.session_id,
            ttl_seconds=3,
            token_factory=lambda: "replacement-worker",
        )
        self.assertTrue(replacement.acquire())
        self.assertTrue(replacement.release())

    def test_atomic_replay_sequence_and_ttl_hold_across_clients(self):
        barrier = threading.Barrier(4)
        sequences: queue.Queue[int] = queue.Queue()

        def append_from_worker(worker):
            store = RedisTurnEventStore(self.clients[worker], self.turn_id)
            barrier.wait(timeout=5)
            for item in range(5):
                event = store.append(
                    "phase",
                    {"phase": "retrieving", "worker": worker, "item": item},
                )
                sequences.put(event.sequence)

        threads = [threading.Thread(target=append_from_worker, args=(worker,)) for worker in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), "Redis event append did not finish")

        observed = sorted(sequences.get_nowait() for _ in range(20))
        self.assertEqual(observed, list(range(1, 21)))
        reader = RedisTurnEventStore(self.clients[4], self.turn_id)
        self.assertEqual(
            [event.sequence for event in reader.replay(after=10)],
            list(range(11, 21)),
        )
        ttl = self.clients[4].ttl(reader.events_key)
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, EVENT_TTL_SECONDS)
        self.assertEqual(self.clients[4].ttl(reader.sequence_key), -1)

        reader.clear_events()
        after_clear = RedisTurnEventStore(self.clients[5], self.turn_id).append(
            "done",
            {"message_id": "safe"},
            terminal=True,
        )
        self.assertEqual(after_clear.sequence, 21)

    def test_read_burst_quota_is_shared_by_independent_throttle_instances(self):
        request = self._request()
        throttles = [AuthenticatedReadBurstThrottle(), AuthenticatedReadBurstThrottle()]
        for throttle in throttles:
            throttle.cache = caches["default"]
            throttle.timer = lambda: 1_000.0
        key = throttles[0].get_cache_key(request, None)
        throttles[0].cache.delete(key)

        accepted = [
            throttles[index % 2].allow_request(request, None)
            for index in range(60)
        ]
        self.assertTrue(all(accepted))

        fresh_worker = AuthenticatedReadBurstThrottle()
        fresh_worker.cache = caches["default"]
        fresh_worker.timer = lambda: 1_000.0
        self.assertFalse(fresh_worker.allow_request(request, None))

