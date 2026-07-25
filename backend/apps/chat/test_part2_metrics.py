# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Post-V3 Part 2 measure-first gate: RAG efficiency metrics.

These tests verify the four new ChatTurn metric keys are accepted by the
sanitizer and merge helpers, so a week of production data can quantify ROI
before any routing/cache optimisation code is built.

New keys:
- retrieval_result_count (numeric): chunks returned by retriever.
- query_near_dup (boolean): near-duplicate query detected.
- cache_hit (boolean): semantic cache hit (reserved; no cache built yet).
- routing_decision (enum): retrieve / skip_retrieval / cache_hit / degraded / none.
"""

from django.test import SimpleTestCase

from .metrics import (
    ChatStreamMetrics,
    merge_turn_metrics,
    sanitize_turn_metrics,
)


class SanitizePart2MetricsTest(SimpleTestCase):
    """sanitize_turn_metrics accepts the four Part 2 keys."""

    def test_retrieval_result_count_numeric(self):
        sanitized = sanitize_turn_metrics({"retrieval_result_count": 5})
        self.assertEqual(sanitized["retrieval_result_count"], 5)

    def test_retrieval_result_count_clamped_to_zero(self):
        sanitized = sanitize_turn_metrics({"retrieval_result_count": -3})
        self.assertEqual(sanitized["retrieval_result_count"], 0)

    def test_retrieval_result_count_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"retrieval_result_count": "five"})

    def test_retrieval_result_count_rejects_bool(self):
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"retrieval_result_count": True})

    def test_query_near_dup_boolean(self):
        sanitized = sanitize_turn_metrics({"query_near_dup": True})
        self.assertIs(sanitized["query_near_dup"], True)

    def test_query_near_dup_rejects_non_bool(self):
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"query_near_dup": "yes"})

    def test_cache_hit_boolean(self):
        sanitized = sanitize_turn_metrics({"cache_hit": False})
        self.assertIs(sanitized["cache_hit"], False)

    def test_cache_hit_rejects_non_bool(self):
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"cache_hit": 1})

    def test_routing_decision_valid(self):
        for decision in ("retrieve", "skip_retrieval", "cache_hit", "degraded", "none"):
            sanitized = sanitize_turn_metrics({"routing_decision": decision})
            self.assertEqual(sanitized["routing_decision"], decision)

    def test_routing_decision_rejects_unknown(self):
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"routing_decision": "custom_route"})

    def test_existing_keys_still_accepted(self):
        """Part 2 keys are additive — existing keys must still work."""
        sanitized = sanitize_turn_metrics(
            {"ttfe_ms": 100, "thinking_enabled": True, "effective_answer_mode": "fast"}
        )
        self.assertEqual(sanitized["ttfe_ms"], 100)
        self.assertIs(sanitized["thinking_enabled"], True)
        self.assertEqual(sanitized["effective_answer_mode"], "fast")


class ChatStreamMetricsPart2Test(SimpleTestCase):
    """ChatStreamMetrics records and snapshots Part 2 fields."""

    def test_mark_retrieval_result(self):
        metrics = ChatStreamMetrics(started_at=0.0)
        metrics.mark_retrieval_result(7)
        self.assertEqual(metrics.retrieval_result_count, 7)

    def test_mark_retrieval_result_clamped(self):
        metrics = ChatStreamMetrics(started_at=0.0)
        metrics.mark_retrieval_result(-1)
        self.assertEqual(metrics.retrieval_result_count, 0)

    def test_snapshot_includes_retrieval_result_count(self):
        metrics = ChatStreamMetrics(started_at=0.0)
        metrics.mark_retrieval_result(3)
        snapshot = metrics.snapshot(now=1.0)
        self.assertEqual(snapshot["retrieval_result_count"], 3)

    def test_snapshot_omits_none_retrieval_count(self):
        metrics = ChatStreamMetrics(started_at=0.0)
        snapshot = metrics.snapshot(now=1.0)
        self.assertNotIn("retrieval_result_count", snapshot)


class _StubTurn:
    """Minimal stand-in for ChatTurn to test merge_turn_metrics."""

    def __init__(self, metrics=None):
        self.metrics = metrics or {}

    def save(self, update_fields=None):
        pass


class MergeTurnMetricsPart2Test(SimpleTestCase):
    """merge_turn_metrics persists Part 2 keys onto a Turn."""

    def test_merge_retrieval_result_count(self):
        turn = _StubTurn()
        merge_turn_metrics(turn, retrieval_result_count=4)
        self.assertEqual(turn.metrics["retrieval_result_count"], 4)

    def test_merge_routing_decision(self):
        turn = _StubTurn()
        merge_turn_metrics(turn, routing_decision="retrieve")
        self.assertEqual(turn.metrics["routing_decision"], "retrieve")

    def test_merge_query_near_dup(self):
        turn = _StubTurn()
        merge_turn_metrics(turn, query_near_dup=True)
        self.assertIs(turn.metrics["query_near_dup"], True)

    def test_merge_cache_hit(self):
        turn = _StubTurn()
        merge_turn_metrics(turn, cache_hit=False)
        self.assertIs(turn.metrics["cache_hit"], False)

    def test_merge_preserves_existing_part2_keys(self):
        turn = _StubTurn({"retrieval_result_count": 2, "routing_decision": "retrieve"})
        merge_turn_metrics(turn, cache_hit=False)
        self.assertEqual(turn.metrics["retrieval_result_count"], 2)
        self.assertEqual(turn.metrics["routing_decision"], "retrieve")
        self.assertIs(turn.metrics["cache_hit"], False)


class GenerationWorkerMetricsTest(SimpleTestCase):
    def test_accepts_bounded_worker_metrics(self):
        sanitized = sanitize_turn_metrics(
            {
                "queue_wait_ms": 125,
                "task_attempt": 2,
                "worker_recovered": True,
                "delta_batch_count": 17,
            }
        )

        self.assertEqual(
            sanitized,
            {
                "queue_wait_ms": 125,
                "task_attempt": 2,
                "worker_recovered": True,
                "delta_batch_count": 17,
            },
        )

    def test_numeric_worker_metrics_reject_booleans(self):
        for key in ("queue_wait_ms", "task_attempt", "delta_batch_count"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                sanitize_turn_metrics({key: True})

    def test_worker_recovered_rejects_arbitrary_labels(self):
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"worker_recovered": "yes"})
