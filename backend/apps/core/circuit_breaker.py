"""DashScope circuit breaker — V4.2 SYS-V4.2-014.

Prevents DashScope API failures from blocking the server.
When consecutive failures reach the threshold, the circuit opens
and returns a degraded response until the recovery timeout passes.

Design:
- Failure threshold: 3 consecutive failures → open circuit
- Recovery timeout: 30 seconds (half-open state)
- Half-open: allows 1 test request; if it succeeds → close circuit
- Open: all requests get degraded response immediately (no DashScope call)

This protects the runserver from being blocked by DashScope timeouts
or authentication failures. In open state, users see a graceful
degradation message instead of waiting 30 seconds for a timeout.

Note: This is a process-level circuit breaker (in-memory singleton).
For multi-worker deployments (gunicorn), use Redis-backed state.
"""

import os
import time
import logging
import threading

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Thread-safe circuit breaker for external API calls.

    States:
    - CLOSED: Normal operation. Failures are counted.
    - OPEN: All requests fail fast with degraded response.
    - HALF_OPEN: One test request allowed to probe recovery.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str = "dashscope",
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """Current circuit state (for logging/monitoring)."""
        with self._lock:
            # Auto-transition from OPEN → HALF_OPEN after recovery timeout
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through.

        Returns:
            True if the circuit is CLOSED or HALF_OPEN (test request).
            False if the circuit is OPEN (fail fast).
        """
        current_state = self.state  # Uses property (auto-transition)
        with self._lock:
            if current_state == self.CLOSED:
                return True
            elif current_state == self.HALF_OPEN:
                return True  # Allow one test request
            else:  # OPEN
                logger.warning(
                    "Circuit breaker [%s] is OPEN — request blocked (fail fast)",
                    self.name,
                )
                return False

    def record_success(self):
        """Record a successful response — close the circuit."""
        with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED
            logger.info(
                "Circuit breaker [%s] CLOSED — DashScope API recovered",
                self.name,
            )

    def record_failure(self):
        """Record a failed response — count toward opening the circuit."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = self.OPEN
                logger.warning(
                    "Circuit breaker [%s] OPENED — %d consecutive failures, "
                    "fail-fast for %ds",
                    self.name,
                    self._failure_count,
                    int(self.recovery_timeout),
                )
            else:
                logger.warning(
                    "Circuit breaker [%s] failure count: %d/%d",
                    self.name,
                    self._failure_count,
                    self.failure_threshold,
                )

    def record_timeout(self):
        """Record a timeout — same as failure but with specific logging."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = self.OPEN
                logger.error(
                    "Circuit breaker [%s] OPENED — %d consecutive timeouts",
                    self.name,
                    self._failure_count,
                )


# V4.2 SYS-V4.2-014: Module-level singleton for DashScope circuit breaker.
# V4.6: Relaxed defaults + env overrides. The previous 3-failures / 30s-global-block
# was too aggressive for multi-conversation use — a couple of transient DashScope
# timeouts (common when several SSE replies stream at once) tripped the breaker and
# made EVERY conversation fail-fast for 30s. Defaults are now 6 failures / 15s recovery;
# tighten for prod via env (e.g. DASHSCOPE_BREAKER_THRESHOLD=3, DASHSCOPE_BREAKER_RECOVERY=30).
dashscope_breaker = CircuitBreaker(
    name="dashscope",
    failure_threshold=int(os.environ.get("DASHSCOPE_BREAKER_THRESHOLD", "6")),
    recovery_timeout=float(os.environ.get("DASHSCOPE_BREAKER_RECOVERY", "15")),
)
