"""Explicit live DashScope provider profile for the four v3 combinations."""

from __future__ import annotations

import os
import time
import unittest

from django.conf import settings
from django.test import SimpleTestCase

from apps.rag.guardrails import LiteLLMChatService
from apps.spaces.generation_policy import (
    CANONICAL_DEEP_MODEL,
    CANONICAL_FAST_MODEL,
)


@unittest.skipUnless(
    os.environ.get("KNOWPILOT_PROVIDER_INTEGRATION") == "1",
    "requires explicit live DashScope provider profile",
)
class DashScopeProviderIntegrationTests(SimpleTestCase):
    def test_canonical_fast_deep_and_independent_thinking_stream_safely(self):
        self.assertTrue(settings.DASHSCOPE_API_KEY)
        service = LiteLLMChatService()
        combinations = (
            ("fast_off", CANONICAL_FAST_MODEL, False),
            ("fast_on", CANONICAL_FAST_MODEL, True),
            ("deep_off", CANONICAL_DEEP_MODEL, False),
            ("deep_on", CANONICAL_DEEP_MODEL, True),
        )

        for label, model_id, thinking_enabled in combinations:
            with self.subTest(combination=label, model_id=model_id):
                started = time.monotonic()
                first_answer_at = None
                answer_parts = []
                observed_kinds = set()
                for part in service.stream_chat_parts(
                    "Reply with exactly the word OK. Do not add punctuation.",
                    "OK",
                    model_id=model_id,
                    thinking_enabled=thinking_enabled,
                    thinking_budget=64 if thinking_enabled else None,
                ):
                    observed_kinds.add(part.kind)
                    self.assertIn(part.kind, {"answer_delta", "reasoning_duration"})
                    if part.kind == "reasoning_duration":
                        self.assertEqual(part.text, "")
                        self.assertIsInstance(part.duration_ms, int)
                    elif part.text:
                        if first_answer_at is None:
                            first_answer_at = time.monotonic()
                        answer_parts.append(part.text)

                self.assertIsNotNone(first_answer_at)
                self.assertTrue("".join(answer_parts).strip())
                self.assertIn("answer_delta", observed_kinds)
                self.assertLess(first_answer_at - started, 120)

