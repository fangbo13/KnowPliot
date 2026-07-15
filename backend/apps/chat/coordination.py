"""Redis-backed single-writer coordination for chat sessions.

The Redis client is deliberately created lazily. Importing this module, running
Django checks, and collecting tests never opens a network connection.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from typing import Any

LEASE_TTL_SECONDS = 180
LEASE_RENEW_SECONDS = 30

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class CoordinationUnavailableError(RuntimeError):
    """Coordination could not be proven safe; callers must fail closed."""

    def __init__(self):
        super().__init__("chat_coordination_unavailable")


class LeaseLostError(RuntimeError):
    """The worker no longer owns the session lease."""

    def __init__(self):
        super().__init__("session_lease_lost")


def session_lease_key(session_id: object) -> str:
    return f"chat:session:{session_id}:turn"


def create_redis_client():
    """Construct, but do not contact, the configured coordination client."""

    try:
        from django.conf import settings
        from redis import Redis

        url = getattr(
            settings,
            "CHAT_COORDINATION_REDIS_URL",
            settings.CELERY_BROKER_URL,
        )
        return Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
    except Exception as exc:
        raise CoordinationUnavailableError() from exc


class RedisSessionLease:
    """Renewable compare-token lease for one chat session."""

    def __init__(
        self,
        client: Any,
        session_id: object,
        *,
        ttl_seconds: int = LEASE_TTL_SECONDS,
        renew_interval: float = LEASE_RENEW_SECONDS,
        token_factory: Callable[[], str] | None = None,
    ):
        self.client = client
        self.key = session_lease_key(session_id)
        self.ttl_seconds = int(ttl_seconds)
        self.renew_interval = renew_interval
        self._token = (token_factory or (lambda: secrets.token_urlsafe(32)))()
        self._acquired = False
        self._lost = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def acquire(self) -> bool:
        try:
            acquired = bool(
                self.client.set(
                    self.key,
                    self._token,
                    nx=True,
                    ex=self.ttl_seconds,
                )
            )
        except Exception as exc:
            raise CoordinationUnavailableError() from exc
        self._acquired = acquired
        return acquired

    def renew(self) -> bool:
        if not self._acquired:
            return False
        try:
            renewed = bool(
                self.client.eval(
                    _RENEW_SCRIPT,
                    1,
                    self.key,
                    self._token,
                    self.ttl_seconds,
                )
            )
        except Exception as exc:
            self._lost.set()
            raise CoordinationUnavailableError() from exc
        if not renewed:
            self._lost.set()
        return renewed

    def _renew_loop(self) -> None:
        while not self._stop.wait(self.renew_interval):
            try:
                if not self.renew():
                    return
            except CoordinationUnavailableError:
                return

    def start_renewal(self) -> None:
        if not self._acquired or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._renew_loop,
            name="chat-session-lease-renewal",
            daemon=True,
        )
        self._thread.start()

    def ensure_owned(self) -> None:
        if not self._acquired or self._lost.is_set():
            raise LeaseLostError()

    def release(self) -> bool:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=min(max(self.renew_interval * 2, 0.1), 2))
        if not self._acquired:
            return False
        try:
            released = bool(
                self.client.eval(
                    _RELEASE_SCRIPT,
                    1,
                    self.key,
                    self._token,
                )
            )
        except Exception as exc:
            self._acquired = False
            raise CoordinationUnavailableError() from exc
        self._acquired = False
        return released

    close = release


def lease_exists(client: Any, session_id: object) -> bool:
    """Return lease presence, distinguishing Redis failure from absence."""

    try:
        return client.get(session_lease_key(session_id)) is not None
    except Exception as exc:
        raise CoordinationUnavailableError() from exc
