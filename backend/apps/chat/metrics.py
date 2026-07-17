"""Safe, low-cardinality metrics for a single chat Turn."""

from __future__ import annotations

from dataclasses import dataclass

_NUMERIC_KEYS = frozenset(
    {
        "ttfe_ms",
        "retrieval_ms",
        "reasoning_ms",
        "first_answer_token_ms",
        "total_ms",
        "disconnect_count",
        "recovery_count",
    }
)
_IDEMPOTENCY_VALUES = frozenset(
    {"created", "retry", "completed", "in_progress", "terminal", "conflict"}
)
_BOOLEAN_KEYS = frozenset({"idempotency_rollout_enabled"})


def sanitize_turn_metrics(values: dict) -> dict:
    """Accept only numeric timings/counts and one bounded outcome code."""

    sanitized = {}
    for key, value in values.items():
        if key in _NUMERIC_KEYS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("chat metric must be numeric")
            sanitized[key] = max(0, int(value))
            continue
        if key == "idempotency_disposition" and value in _IDEMPOTENCY_VALUES:
            sanitized[key] = value
            continue
        if key in _BOOLEAN_KEYS and isinstance(value, bool):
            sanitized[key] = value
            continue
        raise ValueError("unsupported chat metric")
    return sanitized


def merge_turn_metrics(turn, *, increments=(), **values) -> dict:
    """Merge sanitized metrics onto a Turn without accepting arbitrary labels."""

    current = dict(getattr(turn, "metrics", {}) or {})
    sanitized = sanitize_turn_metrics(values)
    for key, value in sanitized.items():
        if key in increments:
            current[key] = int(current.get(key, 0)) + int(value)
        else:
            current[key] = value
    turn.metrics = sanitize_turn_metrics(current)
    # Metrics are observational and must not refresh the Turn liveness clock.
    # `updated_at` is used by stale-worker convergence, so touching it from a
    # recovery poll could indefinitely postpone `worker_lost` detection.
    turn.save(update_fields=["metrics"])
    return turn.metrics


@dataclass
class ChatStreamMetrics:
    started_at: float
    ttfe_ms: int | None = None
    retrieval_ms: int | None = None
    reasoning_ms: int | None = None
    first_answer_token_ms: int | None = None

    def mark_first_event(self, now: float) -> None:
        if self.ttfe_ms is None:
            self.ttfe_ms = max(0, int(round((now - self.started_at) * 1000)))

    def mark_retrieval(self, duration_ms: int | float) -> None:
        self.retrieval_ms = max(0, int(duration_ms))

    def mark_reasoning(self, duration_ms: int | float) -> None:
        self.reasoning_ms = (self.reasoning_ms or 0) + max(0, int(duration_ms))

    def mark_first_answer(self, now: float) -> None:
        if self.first_answer_token_ms is None:
            self.first_answer_token_ms = max(
                0, int(round((now - self.started_at) * 1000))
            )

    def snapshot(self, *, now: float) -> dict:
        values = {
            "ttfe_ms": self.ttfe_ms,
            "retrieval_ms": self.retrieval_ms,
            "reasoning_ms": self.reasoning_ms,
            "first_answer_token_ms": self.first_answer_token_ms,
            "total_ms": max(0, int(round((now - self.started_at) * 1000))),
        }
        return sanitize_turn_metrics(
            {key: value for key, value in values.items() if value is not None}
        )
