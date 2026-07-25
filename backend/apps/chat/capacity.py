"""Redis-backed admission control for asynchronous chat generation.

The sorted set is both a bounded counter and a crash-safe reservation registry:
each member is a globally unique Turn ID and its score is the reservation expiry.
All read-modify-write operations are performed atomically in Redis.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from django.conf import settings


GENERATION_CAPACITY_KEY = "chat:v3:generation:outstanding"


_RESERVE_SCRIPT = """
-- capacity:reserve
local now = tonumber(ARGV[1])
local expires = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZSCORE', KEYS[1], ARGV[4]) then
  redis.call('ZADD', KEYS[1], expires, ARGV[4])
  return {1, redis.call('ZCARD', KEYS[1])}
end
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
  return {0, count}
end
redis.call('ZADD', KEYS[1], expires, ARGV[4])
return {1, count + 1}
"""


_RENEW_SCRIPT = """
-- capacity:renew
local now = tonumber(ARGV[1])
local expires = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if not redis.call('ZSCORE', KEYS[1], ARGV[3]) then
  return 0
end
redis.call('ZADD', KEYS[1], expires, ARGV[3])
return 1
"""


_RELEASE_SCRIPT = """
-- capacity:release
return redis.call('ZREM', KEYS[1], ARGV[1])
"""


_OUTSTANDING_SCRIPT = """
-- capacity:outstanding
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', tonumber(ARGV[1]))
return redis.call('ZCARD', KEYS[1])
"""


class GenerationCapacityUnavailable(RuntimeError):
    """Raised when Redis cannot prove that generation capacity is available."""


@dataclass(frozen=True)
class CapacityReservation:
    accepted: bool
    outstanding: int
    retry_after_seconds: int


class GenerationCapacityController:
    """Atomically reserve and account for outstanding generation Turns."""

    key = GENERATION_CAPACITY_KEY

    def __init__(
        self,
        client,
        *,
        max_outstanding: int,
        ttl_seconds: int,
        clock: Callable[[], float] = time.time,
        retry_after_seconds: int | None = None,
    ):
        if max_outstanding <= 0:
            raise ValueError("max_outstanding must be positive")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if retry_after_seconds is None:
            retry_after_seconds = settings.CHAT_GENERATION_RETRY_AFTER_SECONDS
        if retry_after_seconds <= 0:
            raise ValueError("retry_after_seconds must be positive")

        self.client = client
        self.max_outstanding = int(max_outstanding)
        self.ttl_seconds = int(ttl_seconds)
        self.clock = clock
        self.retry_after_seconds = int(retry_after_seconds)

    def reserve(self, turn_id) -> CapacityReservation:
        now = float(self.clock())
        try:
            accepted, outstanding = self.client.eval(
                _RESERVE_SCRIPT,
                1,
                self.key,
                now,
                now + self.ttl_seconds,
                self.max_outstanding,
                str(turn_id),
            )
        except Exception as exc:
            raise GenerationCapacityUnavailable(
                "generation capacity service is unavailable"
            ) from exc
        return CapacityReservation(
            accepted=bool(int(accepted)),
            outstanding=int(outstanding),
            retry_after_seconds=self.retry_after_seconds,
        )

    def renew(self, turn_id) -> bool:
        now = float(self.clock())
        try:
            result = self.client.eval(
                _RENEW_SCRIPT,
                1,
                self.key,
                now,
                now + self.ttl_seconds,
                str(turn_id),
            )
        except Exception as exc:
            raise GenerationCapacityUnavailable(
                "generation capacity service is unavailable"
            ) from exc
        return bool(int(result))

    def release(self, turn_id) -> bool:
        try:
            result = self.client.eval(
                _RELEASE_SCRIPT,
                1,
                self.key,
                str(turn_id),
            )
        except Exception as exc:
            raise GenerationCapacityUnavailable(
                "generation capacity service is unavailable"
            ) from exc
        return bool(int(result))

    def outstanding(self) -> int:
        try:
            result = self.client.eval(
                _OUTSTANDING_SCRIPT,
                1,
                self.key,
                float(self.clock()),
            )
        except Exception as exc:
            raise GenerationCapacityUnavailable(
                "generation capacity service is unavailable"
            ) from exc
        return int(result)
