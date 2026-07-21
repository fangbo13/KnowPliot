# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Post-V3 Part 4: AI reply-language resolution (bilingual).

Resolution order (high -> low):
1. Query-language auto-detection (primary): zh query -> zh reply; en -> en.
2. User `language_preference` explicit override (zh/en beats detection).
3. Space `default_language` (auto/zh/en, default auto) fallback.

KB content language MUST NOT drive reply language. The system prompt uses a
dynamic "Respond in {resolved_language}" instruction (no hardcoded "en").
"""

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.rag.language import (
    LANGUAGE_AUTO,
    LANGUAGE_EN,
    LANGUAGE_ZH,
    detect_query_language,
    resolve_reply_language,
)
from apps.rag.prompt_builder import PromptBuilder


class DetectQueryLanguageTests(SimpleTestCase):
    def test_chinese_query_detected_as_zh(self):
        self.assertEqual(detect_query_language("我想了解入职流程"), LANGUAGE_ZH)

    def test_english_query_detected_as_en(self):
        self.assertEqual(detect_query_language("What is the onboarding process?"), LANGUAGE_EN)

    def test_mixed_query_prefers_cjk_when_present(self):
        # A query that contains CJK characters resolves to zh.
        self.assertEqual(detect_query_language("how to onboarding 入职流程"), LANGUAGE_ZH)

    def test_empty_query_is_auto_inconclusive(self):
        # An empty/whitespace query is inconclusive (auto) so the space
        # default fallback can apply; it must NOT force "en".
        self.assertEqual(detect_query_language(""), LANGUAGE_AUTO)
        self.assertEqual(detect_query_language("   "), LANGUAGE_AUTO)


class ResolveReplyLanguageTests(SimpleTestCase):
    def _user(self, pref=LANGUAGE_AUTO):
        return SimpleNamespace(language_preference=pref)

    def _space(self, default=LANGUAGE_AUTO):
        return SimpleNamespace(default_language=default)

    def test_query_detection_is_primary(self):
        # Chinese query, auto user, auto space -> zh (detection wins).
        resolved = resolve_reply_language(
            "我想了解入职流程", self._user(), self._space()
        )
        self.assertEqual(resolved, LANGUAGE_ZH)

    def test_english_query_detected_as_en(self):
        resolved = resolve_reply_language(
            "What is onboarding?", self._user(), self._space()
        )
        self.assertEqual(resolved, LANGUAGE_EN)

    def test_user_preference_overrides_detection(self):
        # User pref=zh overrides an English query -> zh.
        resolved = resolve_reply_language(
            "What is onboarding?", self._user(pref=LANGUAGE_ZH), self._space()
        )
        self.assertEqual(resolved, LANGUAGE_ZH)

    def test_space_default_fallback_when_user_auto(self):
        # User auto + space default=zh + ambiguous/empty query -> zh fallback.
        resolved = resolve_reply_language(
            "", self._user(pref=LANGUAGE_AUTO), self._space(default=LANGUAGE_ZH)
        )
        self.assertEqual(resolved, LANGUAGE_ZH)

    def test_space_default_auto_with_empty_query_defaults_en(self):
        resolved = resolve_reply_language(
            "", self._user(pref=LANGUAGE_AUTO), self._space(default=LANGUAGE_AUTO)
        )
        self.assertEqual(resolved, LANGUAGE_EN)

    def test_user_auto_space_auto_uses_detection(self):
        # Detection still wins when both user + space are auto.
        resolved = resolve_reply_language(
            "帮我看看福利", self._user(pref=LANGUAGE_AUTO), self._space(default=LANGUAGE_AUTO)
        )
        self.assertEqual(resolved, LANGUAGE_ZH)


class PromptBuilderDynamicLanguageTests(SimpleTestCase):
    def test_prompt_does_not_hardcode_english_reply(self):
        # The EN template must use a dynamic {resolved_language} placeholder,
        # not a hardcoded "Respond in English."
        self.assertNotIn("Respond in English.", PromptBuilder.SYSTEM_PROMPT_EN)
        self.assertIn("{resolved_language}", PromptBuilder.SYSTEM_PROMPT_EN)

    def test_prompt_renders_resolved_language(self):
        builder = PromptBuilder()
        prompt = builder.build(
            context_chunks=[],
            conversation_history=[],
            user_profile=SimpleNamespace(
                service_line="tax",
                office_location=None,
                role_level=None,
                start_date=None,
            ),
            language=LANGUAGE_ZH,
        )
        # The zh prompt instructs a Chinese reply (resolved_language=Chinese).
        self.assertIn("Chinese", prompt)

    def test_prompt_renders_english_for_en(self):
        builder = PromptBuilder()
        prompt = builder.build(
            context_chunks=[],
            conversation_history=[],
            user_profile=SimpleNamespace(
                service_line="tax",
                office_location=None,
                role_level=None,
                start_date=None,
            ),
            language=LANGUAGE_EN,
        )
        self.assertIn("English", prompt)
