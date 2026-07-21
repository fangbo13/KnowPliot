# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""V4 Part 3: Thinking inner monologue — progressive safe-label via SSE.

When thinking_enabled=True, the pipeline yields a
{"event": "phase", "data": {"phase": "thinking"}} event positioned between
citations and the first answer token.  No raw CoT or timing is exposed — only
the safe phase label and the reasoning_ms metric.

Constraints (from handoff doc):
- Reuse chatStore streamPhase/SafeProcessingPhase (frontend maps "thinking")
- No timing, no raw CoT
- SSE phase sends progressive safe-label
- Thinking switch on enables it
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class ThinkingPhaseEmissionTests(SimpleTestCase):
    """Verify the pipeline emits a thinking phase event when thinking is on."""

    def _collect_events(self, thinking_enabled: bool) -> list:
        """Create a RAGPipeline with fully mocked deps and collect all events."""
        with patch("apps.rag.pipeline.get_shared_chat_services") as mock_shared, \
             patch("apps.rag.pipeline.get_llm_service") as mock_llm, \
             patch("apps.rag.pipeline.dashscope_breaker") as mock_breaker, \
             patch("apps.rag.pipeline.classify_confidence") as mock_classify:

            # Mock retriever — return one valid chunk
            mock_retriever = MagicMock()
            mock_retriever.search.return_value = [
                {
                    "id": 1,
                    "document_id": 1,
                    "document_title": "Onboarding Guide",
                    "content": "Welcome to the team! Here is the process.",
                    "score": 0.95,
                    "page_number": 1,
                }
            ]

            # Mock guardrails — all input is safe
            mock_guardrails = MagicMock()
            mock_guardrails.check_input.return_value = True

            # Mock prompt builder
            mock_prompt_builder = MagicMock()
            mock_prompt_builder.build.return_value = "You are a helpful assistant."

            mock_shared.return_value = SimpleNamespace(
                embedder=MagicMock(),
                retriever=mock_retriever,
                prompt_builder=mock_prompt_builder,
                guardrails=mock_guardrails,
            )

            # Mock circuit breaker — allow requests
            mock_breaker.allow_request.return_value = True

            # Mock classify_confidence — high confidence
            mock_classify.return_value = SimpleNamespace(
                label="high",
                score=0.95,
                needs_human_review=False,
            )

            # Mock LLM — emit reasoning_duration + answer_delta parts
            mock_llm_instance = MagicMock()

            def fake_stream_parts(system_prompt, query, **kwargs):
                yield SimpleNamespace(kind="reasoning_duration", duration_ms=150)
                yield SimpleNamespace(kind="answer_delta", text="Hello world")

            mock_llm_instance.stream_chat_parts = fake_stream_parts
            mock_llm.return_value = mock_llm_instance

            from apps.rag.pipeline import RAGPipeline
            pipeline = RAGPipeline()
            pipeline.thinking_enabled = thinking_enabled
            pipeline.thinking_budget = 1024 if thinking_enabled else None

            events = list(pipeline.retrieve_and_generate(
                query="What is onboarding?",
                user_profile=SimpleNamespace(),
                conversation_history=[],
                space_id="1",
                language="en",
            ))
            return events

    # ------------------------------------------------------------------

    def test_thinking_enabled_emits_phase_event(self):
        """thinking_enabled=True must yield a thinking phase event."""
        events = self._collect_events(thinking_enabled=True)
        phase_events = [e for e in events if e["event"] == "phase"]
        self.assertTrue(
            any(e["data"]["phase"] == "thinking" for e in phase_events),
            "thinking_enabled=True must emit a thinking phase event",
        )

    def test_thinking_disabled_no_phase_event(self):
        """thinking_enabled=False must NOT yield a thinking phase event."""
        events = self._collect_events(thinking_enabled=False)
        phase_events = [e for e in events if e["event"] == "phase"]
        self.assertFalse(
            any(e["data"]["phase"] == "thinking" for e in phase_events),
            "thinking_enabled=False must not emit a thinking phase event",
        )

    def test_thinking_phase_after_citations_before_token(self):
        """The thinking phase must appear after citations and before the first token."""
        events = self._collect_events(thinking_enabled=True)

        citations_idx = None
        thinking_idx = None
        token_idx = None
        for i, e in enumerate(events):
            if e["event"] == "citations" and citations_idx is None:
                citations_idx = i
            if (e["event"] == "phase" and e["data"].get("phase") == "thinking"
                    and thinking_idx is None):
                thinking_idx = i
            if e["event"] == "token" and token_idx is None:
                token_idx = i

        self.assertIsNotNone(citations_idx, "citations event must be present")
        self.assertIsNotNone(thinking_idx, "thinking phase event must be present")
        self.assertIsNotNone(token_idx, "token event must be present")
        self.assertLess(
            citations_idx, thinking_idx,
            "thinking phase must come after citations",
        )
        self.assertLess(
            thinking_idx, token_idx,
            "thinking phase must come before first token",
        )

    def test_no_raw_cot_exposed(self):
        """Raw CoT (reasoning_content) must not appear in any event data."""
        events = self._collect_events(thinking_enabled=True)

        for event in events:
            self.assertNotIn(
                "reasoning_content", event.get("data", {}),
                "Raw CoT must not be exposed — only reasoning_ms metric",
            )

        # reasoning_duration is surfaced as a metrics event with reasoning_ms
        metrics_events = [e for e in events if e["event"] == "metrics"]
        self.assertTrue(
            any(e["data"].get("reasoning_ms") is not None for e in metrics_events),
            "reasoning_ms metric should be present when thinking is enabled",
        )

    def test_phase_event_format(self):
        """The phase event must use the exact wire format for SSE forwarding."""
        events = self._collect_events(thinking_enabled=True)
        phase_events = [
            e for e in events
            if e["event"] == "phase" and e["data"].get("phase") == "thinking"
        ]
        self.assertEqual(len(phase_events), 1, "exactly one thinking phase event")
        event = phase_events[0]
        self.assertIn("event", event)
        self.assertIn("data", event)
        self.assertEqual(event["event"], "phase")
        self.assertEqual(event["data"], {"phase": "thinking"})
