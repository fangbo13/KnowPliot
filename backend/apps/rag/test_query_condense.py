# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Follow-up query condensation tests (retrieval-only rewrite + fallbacks)."""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.rag.query_condense import condense_query, looks_contextual


class LooksContextualTest(SimpleTestCase):
    def test_no_history_never_rewrites(self):
        self.assertFalse(looks_contextual("那第二条呢？", has_history=False))

    def test_short_query_with_history(self):
        self.assertTrue(looks_contextual("那第二条呢？", has_history=True))

    def test_anaphora_in_longer_query(self):
        self.assertTrue(
            looks_contextual("请把上面提到的第三点流程再详细说一下", has_history=True)
        )
        self.assertTrue(
            looks_contextual("what about the previous policy you mentioned", has_history=True)
        )

    def test_standalone_question_not_rewritten(self):
        self.assertFalse(
            looks_contextual("公司差旅报销的具体流程和金额上限是多少", has_history=True)
        )

    def test_blank_query(self):
        self.assertFalse(looks_contextual("   ", has_history=True))


@override_settings(CHAT_QUERY_REWRITE_ENABLED=True)
class CondenseQueryTest(SimpleTestCase):
    HISTORY = (
        ("user", "报销制度有哪些规定？"),
        ("assistant", "报销制度共有三条：一、需发票；二、上限5000元；三、需审批。"),
    )

    def _mock_llm(self, reply):
        llm = Mock()
        llm.complete.return_value = reply
        return llm

    def test_rewrites_follow_up(self):
        llm = self._mock_llm("报销制度的第二条规定是什么？")
        with patch("apps.rag.guardrails.get_llm_service", return_value=llm):
            result = condense_query(
                "那第二条呢？", recent_history=self.HISTORY, language="zh"
            )
        self.assertEqual(result, "报销制度的第二条规定是什么？")
        llm.complete.assert_called_once()

    def test_llm_failure_falls_back_to_original(self):
        llm = Mock()
        llm.complete.side_effect = TimeoutError("slow provider")
        with patch("apps.rag.guardrails.get_llm_service", return_value=llm):
            result = condense_query(
                "那第二条呢？", recent_history=self.HISTORY, language="zh"
            )
        self.assertEqual(result, "那第二条呢？")

    def test_empty_rewrite_falls_back(self):
        with patch(
            "apps.rag.guardrails.get_llm_service",
            return_value=self._mock_llm("   "),
        ):
            result = condense_query(
                "那第二条呢？", recent_history=self.HISTORY, language="zh"
            )
        self.assertEqual(result, "那第二条呢？")

    def test_multiline_rewrite_keeps_first_line(self):
        with patch(
            "apps.rag.guardrails.get_llm_service",
            return_value=self._mock_llm("报销制度的第二条是什么？\n解释：因为..."),
        ):
            result = condense_query(
                "那第二条呢？", recent_history=self.HISTORY, language="zh"
            )
        self.assertEqual(result, "报销制度的第二条是什么？")

    def test_standalone_query_skips_llm(self):
        with patch("apps.rag.guardrails.get_llm_service") as get_llm:
            result = condense_query(
                "公司差旅报销的具体流程和金额上限是多少",
                recent_history=self.HISTORY,
                language="zh",
            )
        self.assertEqual(result, "公司差旅报销的具体流程和金额上限是多少")
        get_llm.assert_not_called()

    @override_settings(CHAT_QUERY_REWRITE_ENABLED=False)
    def test_disabled_switch_skips_llm(self):
        with patch("apps.rag.guardrails.get_llm_service") as get_llm:
            result = condense_query(
                "那第二条呢？", recent_history=self.HISTORY, language="zh"
            )
        self.assertEqual(result, "那第二条呢？")
        get_llm.assert_not_called()
