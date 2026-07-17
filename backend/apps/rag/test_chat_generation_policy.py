"""Chat-only pipeline, provider separation, and safe timing contracts."""

import inspect
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

try:
    from apps.rag.guardrails import ProviderStreamPart, parse_provider_stream
except ImportError:  # RED: Task 5 introduces typed provider stream parsing.
    ProviderStreamPart = None
    parse_provider_stream = None

try:
    from apps.chat.metrics import (
        ChatStreamMetrics,
        merge_turn_metrics,
        sanitize_turn_metrics,
    )
except ImportError:  # RED: Task 5 introduces stable low-cardinality metrics.
    ChatStreamMetrics = None
    merge_turn_metrics = None
    sanitize_turn_metrics = None


class ProviderStreamParserTest(SimpleTestCase):
    def setUp(self):
        self.assertIsNotNone(parse_provider_stream)
        self.assertIsNotNone(ProviderStreamPart)

    def test_interleaved_reasoning_is_reduced_to_numeric_timing_and_never_text(self):
        clock = iter([1.000, 1.040]).__next__
        lines = [
            'data: {"choices":[{"delta":{"reasoning_content":"private alpha"}}]}',
            'data: {"choices":[{"delta":{"reasoning_content":"private beta"}}]}',
            'data: {"choices":[{"delta":{"content":"visible"}}]}',
            "data: [DONE]",
        ]

        parts = list(parse_provider_stream(lines, clock=clock))

        self.assertEqual(
            [part.kind for part in parts],
            ["reasoning_duration", "answer_delta"],
        )
        self.assertEqual(parts[0].duration_ms, 40)
        self.assertEqual(parts[1].text, "visible")
        serialized = repr(parts)
        self.assertNotIn("private alpha", serialized)
        self.assertNotIn("private beta", serialized)

    def test_malformed_chunks_and_reasoning_only_eof_escape_no_text(self):
        lines = [
            "data: not-json",
            'data: {"choices":[]}',
            'data: {"choices":[{"delta":{"reasoning_content":"never expose"}}]}',
            'data: {"choices":[{"delta":{"content":{"reasoning_content":"nested private"}}}]}',
        ]

        parts = list(parse_provider_stream(lines, clock=iter([2.0, 2.05]).__next__))

        self.assertEqual([part.kind for part in parts], ["reasoning_duration"])
        self.assertEqual(parts[0].duration_ms, 50)
        self.assertNotIn("never expose", repr(parts))
        self.assertNotIn("nested private", repr(parts))

    def test_deep_payload_uses_resolved_model_and_thinking_budget(self):
        from apps.rag.guardrails import LiteLLMChatService

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def raise_for_status(self):
                return None

            def iter_lines(self):
                return iter(['data: {"choices":[{"delta":{"content":"ok"}}]}'])

        client = Mock()
        client.stream.return_value = Response()
        service = object.__new__(LiteLLMChatService)
        service.base_url = "https://provider.invalid/v1"
        service.headers = {"Authorization": "safe-test-value"}
        service.model = "default-model"
        service._client = client

        parts = list(
            service.stream_chat_parts(
                "system",
                "question",
                model_id="governed-deep",
                thinking_enabled=True,
                thinking_budget=2048,
            )
        )

        self.assertEqual([part.text for part in parts], ["ok"])
        payload = client.stream.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "governed-deep")
        self.assertTrue(payload["enable_thinking"])
        self.assertEqual(payload["thinking_budget"], 2048)


class ChatPipelineConstructionTest(SimpleTestCase):
    def test_chat_default_does_not_import_or_construct_ingestion_dependencies(self):
        from apps.rag import pipeline as pipeline_module

        source = inspect.getsource(pipeline_module)
        self.assertNotIn("\nfrom .chunker import", source)
        with (
            patch.object(pipeline_module, "_shared_chat_services", None),
            patch("apps.rag.pipeline.EmbeddingService", return_value=Mock()),
            patch("apps.rag.pipeline.HybridRetriever", return_value=Mock()),
            patch("apps.rag.pipeline.PromptBuilder", return_value=Mock()),
            patch("apps.rag.pipeline.GuardrailsService", return_value=Mock()),
            patch("apps.rag.pipeline.get_llm_service", return_value=Mock()),
        ):
            chat_pipeline = pipeline_module.RAGPipeline()

        self.assertFalse(hasattr(chat_pipeline, "parser"))
        self.assertFalse(hasattr(chat_pipeline, "chunker"))

    def test_chat_pipelines_reuse_the_shared_llm_service(self):
        from apps.rag import pipeline as pipeline_module

        shared = Mock()
        with (
            patch.object(pipeline_module, "_shared_chat_services", None),
            patch("apps.rag.pipeline.EmbeddingService", return_value=Mock()) as embedder,
            patch("apps.rag.pipeline.HybridRetriever", return_value=Mock()) as retriever,
            patch("apps.rag.pipeline.PromptBuilder", return_value=Mock()),
            patch("apps.rag.pipeline.GuardrailsService", return_value=Mock()),
            patch("apps.rag.pipeline.get_llm_service", return_value=shared) as getter,
        ):
            first = pipeline_module.RAGPipeline()
            second = pipeline_module.RAGPipeline()

        self.assertIs(first.llm, shared)
        self.assertIs(second.llm, shared)
        self.assertIs(first.retriever, second.retriever)
        embedder.assert_called_once_with()
        retriever.assert_called_once()
        self.assertEqual(getter.call_count, 2)


class DeepProviderFailureTest(SimpleTestCase):
    def test_open_provider_circuit_keeps_deep_turn_retryable(self):
        from apps.rag.errors import ProviderGenerationError
        from apps.rag.pipeline import RAGPipeline

        pipeline = object.__new__(RAGPipeline)
        pipeline.guardrails = Mock(check_input=Mock(return_value=True))
        pipeline.retriever = Mock(
            search=Mock(
                return_value=[
                    {
                        "id": "chunk-a",
                        "content": "safe evidence a",
                        "document_id": "doc-a",
                        "document_title": "Document A",
                        "score": 0.9,
                    },
                    {
                        "id": "chunk-b",
                        "content": "safe evidence b",
                        "document_id": "doc-b",
                        "document_title": "Document B",
                        "score": 0.9,
                    },
                ]
            )
        )
        pipeline.answer_mode = "deep"

        with (
            patch("apps.rag.pipeline.dashscope_breaker.allow_request", return_value=False),
            self.assertRaisesRegex(ProviderGenerationError, "provider_unavailable"),
        ):
            list(
                pipeline.retrieve_and_generate(
                    "question",
                    user_profile=object(),
                    conversation_history=[],
                    space_id="00000000-0000-0000-0000-000000000001",
                )
            )

    def test_reasoning_only_eof_is_retryable_and_never_becomes_empty_answer(self):
        from apps.rag.errors import ProviderGenerationError
        from apps.rag.pipeline import RAGPipeline

        pipeline = object.__new__(RAGPipeline)
        pipeline.guardrails = Mock(check_input=Mock(return_value=True))
        pipeline.retriever = Mock(
            search=Mock(
                return_value=[
                    {
                        "id": "chunk-a",
                        "content": "safe evidence a",
                        "document_id": "doc-a",
                        "document_title": "Document A",
                        "score": 0.9,
                    },
                    {
                        "id": "chunk-b",
                        "content": "safe evidence b",
                        "document_id": "doc-b",
                        "document_title": "Document B",
                        "score": 0.9,
                    },
                ]
            )
        )
        pipeline.prompt_builder = Mock(build=Mock(return_value="safe prompt"))
        pipeline.llm = Mock(
            stream_chat_parts=Mock(
                return_value=iter(
                    [ProviderStreamPart(kind="reasoning_duration", duration_ms=12)]
                )
            )
        )
        pipeline.model_name = "governed-deep"
        pipeline.answer_mode = "deep"
        pipeline.thinking_enabled = True
        pipeline.thinking_budget = 1024

        with (
            patch("apps.rag.pipeline.dashscope_breaker.allow_request", return_value=True),
            patch("apps.rag.pipeline.dashscope_breaker.record_failure"),
            self.assertLogs("apps.rag.pipeline", level="ERROR") as logs,
            self.assertRaisesRegex(
                ProviderGenerationError,
                "provider_unavailable",
            ),
        ):
            list(
                pipeline.retrieve_and_generate(
                    "question",
                    user_profile=object(),
                    conversation_history=[],
                    space_id="00000000-0000-0000-0000-000000000001",
                )
            )

        self.assertNotIn("reasoning_content", "\n".join(logs.output))
        self.assertNotIn("safe evidence", "\n".join(logs.output))


class StableChatMetricsTest(SimpleTestCase):
    def setUp(self):
        self.assertIsNotNone(ChatStreamMetrics)
        self.assertIsNotNone(merge_turn_metrics)
        self.assertIsNotNone(sanitize_turn_metrics)

    def test_timings_are_numeric_and_have_only_stable_keys(self):
        metrics = ChatStreamMetrics(started_at=10.0)
        metrics.mark_first_event(10.010)
        metrics.mark_retrieval(21)
        metrics.mark_reasoning(14)
        metrics.mark_reasoning(20)
        metrics.mark_first_answer(10.060)

        result = metrics.snapshot(now=10.120)

        self.assertEqual(
            result,
            {
                "ttfe_ms": 10,
                "retrieval_ms": 21,
                "reasoning_ms": 34,
                "first_answer_token_ms": 60,
                "total_ms": 120,
            },
        )
        self.assertEqual(sanitize_turn_metrics(result), result)

    def test_raw_or_high_cardinality_metric_values_are_rejected(self):
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"raw_reasoning": "private"})
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"total_ms": "provider exception text"})
        with self.assertRaises(ValueError):
            sanitize_turn_metrics({"idempotency_disposition": "user supplied value"})

    def test_observational_metrics_do_not_refresh_the_turn_liveness_clock(self):
        turn = SimpleNamespace(metrics={}, save=Mock())

        merge_turn_metrics(turn, recovery_count=1, increments=("recovery_count",))

        turn.save.assert_called_once_with(update_fields=["metrics"])
