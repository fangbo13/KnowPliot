# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Session long/short-term memory tests.

Covers the token-budgeted short-term window (apps.chat.memory), the rolling
summary Celery task (apps.chat.tasks.update_session_memory) and the summary
injection contract of the prompt builder.
"""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.chat.memory import (
    MemoryContext,
    build_memory_context,
    estimate_tokens,
    truncate_middle,
)
from apps.chat.models import ChatSession, Message, SessionMemory
from apps.chat.tasks import _parse_memory_payload, update_session_memory
from apps.spaces.models import BusinessLine, Organization
from apps.spaces.test_utils import create_test_space

User = get_user_model()


class MemoryTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Memory Org", slug="memory-org")
        cls.line = BusinessLine.objects.create(
            organization=cls.org, name="Memory Line", code="memory-line"
        )
        cls.space = create_test_space(
            organization=cls.org,
            business_line=cls.line,
            name="Memory Space",
            code="memory-space",
        )
        cls.user = User.objects.create_user(
            username="memory-user",
            email="memory-user@example.com",
            password="test",
        )

    def setUp(self):
        self.session = ChatSession.objects.create(
            user=self.user, space=self.space, title="Memory session"
        )

    def _add_messages(self, count, content="消息内容", role_cycle=("user", "assistant")):
        messages = []
        for i in range(count):
            messages.append(
                Message.objects.create(
                    session=self.session,
                    space=self.space,
                    role=role_cycle[i % len(role_cycle)],
                    content=f"{content}-{i}",
                )
            )
        return messages


class BuildMemoryContextTest(MemoryTestBase):
    def test_keeps_chronological_order_within_budget(self):
        self._add_messages(6)
        context = build_memory_context(self.session)
        self.assertIsInstance(context, MemoryContext)
        contents = [content for _, content in context.recent_history]
        self.assertEqual(contents, [f"消息内容-{i}" for i in range(6)])

    def test_token_budget_drops_oldest_first(self):
        # Budget sized to exactly two messages — the three oldest must drop.
        long_text = "报销流程第一步需要提交发票凭证并由经理审批通过后财务复核归档" * 8
        for i in range(5):
            Message.objects.create(
                session=self.session,
                space=self.space,
                role="user",
                content=f"{i}-{long_text}",
            )
        per_message = estimate_tokens(f"0-{long_text}") + 4
        context = build_memory_context(
            self.session,
            token_budget=per_message * 2,
            message_token_cap=100_000,
        )
        contents = [content for _, content in context.recent_history]
        self.assertEqual(len(contents), 2)
        # The newest message must always survive, and order stays chronological.
        self.assertTrue(contents[-1].startswith("4-"))
        indexes = [int(content.split("-", 1)[0]) for content in contents]
        self.assertEqual(indexes, sorted(indexes))

    def test_single_oversized_message_is_middle_truncated_not_evicting_window(self):
        self._add_messages(4)
        Message.objects.create(
            session=self.session,
            space=self.space,
            role="user",
            content="头" * 2000 + "尾" * 2000,
        )
        context = build_memory_context(
            self.session, token_budget=2000, message_token_cap=200
        )
        # The oversized newest message is capped, so older messages still fit.
        self.assertGreater(len(context.recent_history), 1)
        newest = context.recent_history[-1][1]
        self.assertLessEqual(estimate_tokens(newest), 260)
        self.assertIn("已省略", newest)

    def test_question_message_is_excluded(self):
        messages = self._add_messages(3)
        context = build_memory_context(self.session, question_message=messages[-1])
        contents = [content for _, content in context.recent_history]
        self.assertNotIn(messages[-1].content, contents)

    @override_settings(CHAT_MEMORY_ENABLED=True)
    def test_session_summary_and_key_facts_attached(self):
        self._add_messages(2)
        SessionMemory.objects.create(
            session=self.session,
            space=self.space,
            summary="用户正在办理报销，公司为安永。",
            key_facts=["报销上限 5000 元", "用户属于审计业务线"],
            summary_version=1,
        )
        context = build_memory_context(self.session)
        self.assertEqual(context.summary, "用户正在办理报销，公司为安永。")
        self.assertEqual(len(context.key_facts), 2)

    @override_settings(CHAT_MEMORY_ENABLED=False)
    def test_memory_disabled_returns_window_only(self):
        self._add_messages(2)
        SessionMemory.objects.create(
            session=self.session, space=self.space, summary="不应注入"
        )
        context = build_memory_context(self.session)
        self.assertEqual(context.summary, "")
        self.assertEqual(context.key_facts, ())

    def test_history_messages_coerces_roles(self):
        context = MemoryContext(
            recent_history=(("user", "你好"), ("assistant", "您好"), ("system", "x"))
        )
        roles = [item["role"] for item in context.history_messages()]
        self.assertEqual(roles, ["user", "assistant", "user"])


class TruncateMiddleTest(TestCase):
    def test_short_content_untouched(self):
        self.assertEqual(truncate_middle("短消息", 100), "短消息")

    def test_long_content_keeps_head_and_tail(self):
        content = "A" * 4000 + "B" * 4000
        result = truncate_middle(content, 100)
        self.assertLess(estimate_tokens(result), estimate_tokens(content))
        self.assertTrue(result.startswith("A"))
        self.assertTrue(result.endswith("B"))


@override_settings(CHAT_MEMORY_ENABLED=True, CHAT_MEMORY_SUMMARY_TRIGGER=8)
class UpdateSessionMemoryTaskTest(MemoryTestBase):
    def _mock_llm(self, reply):
        llm = Mock()
        llm.complete.return_value = reply
        return llm

    def _run_task(self):
        return update_session_memory.apply(args=[str(self.session.id)]).result

    def test_below_trigger_makes_no_llm_call(self):
        self._add_messages(4)
        with patch("apps.rag.guardrails.get_llm_service") as get_llm:
            result = self._run_task()
        self.assertEqual(result["status"], "below_trigger")
        get_llm.assert_not_called()

    def test_summarizes_and_advances_watermark(self):
        self._add_messages(10)
        reply = '{"summary": "早前讨论了报销流程。", "key_facts": ["上限5000元"]}'
        with patch(
            "apps.rag.guardrails.get_llm_service",
            return_value=self._mock_llm(reply),
        ):
            result = self._run_task()
        self.assertEqual(result["status"], "updated")
        memory = SessionMemory.objects.get(session=self.session)
        self.assertEqual(memory.summary, "早前讨论了报销流程。")
        self.assertEqual(memory.key_facts, ["上限5000元"])
        self.assertEqual(memory.summary_version, 1)
        self.assertIsNotNone(memory.summarized_until)
        # The freshest messages stay out of the summary (verbatim-only lag).
        self.assertEqual(result["summarized"], 6)

    def test_idempotent_watermark_no_duplicate_summary(self):
        self._add_messages(10)
        reply = '{"summary": "第一次摘要", "key_facts": []}'
        with patch(
            "apps.rag.guardrails.get_llm_service",
            return_value=self._mock_llm(reply),
        ):
            first = self._run_task()
            # Re-run without new messages: only 4 pending → below trigger.
            second = self._run_task()
        self.assertEqual(first["status"], "updated")
        self.assertEqual(second["status"], "below_trigger")
        self.assertEqual(
            SessionMemory.objects.get(session=self.session).summary_version, 1
        )

    def test_llm_failure_keeps_previous_summary(self):
        SessionMemory.objects.create(
            session=self.session,
            space=self.space,
            summary="旧摘要",
            key_facts=["旧事实"],
            summary_version=3,
        )
        self._add_messages(10)
        failing = Mock()
        failing.complete.side_effect = RuntimeError("provider down")
        with patch("apps.rag.guardrails.get_llm_service", return_value=failing):
            result = self._run_task()
        self.assertEqual(result["status"], "llm_failed")
        memory = SessionMemory.objects.get(session=self.session)
        self.assertEqual(memory.summary, "旧摘要")
        self.assertEqual(memory.summary_version, 3)

    @override_settings(CHAT_MEMORY_ENABLED=False)
    def test_disabled_switch_is_a_noop(self):
        self._add_messages(10)
        result = self._run_task()
        self.assertEqual(result["status"], "disabled")
        self.assertFalse(SessionMemory.objects.filter(session=self.session).exists())


class ParseMemoryPayloadTest(TestCase):
    def test_plain_json(self):
        summary, facts = _parse_memory_payload(
            '{"summary": "s", "key_facts": ["a", "b"]}'
        )
        self.assertEqual(summary, "s")
        self.assertEqual(facts, ["a", "b"])

    def test_json_inside_code_fence(self):
        raw = '```json\n{"summary": "s2", "key_facts": []}\n```'
        summary, facts = _parse_memory_payload(raw)
        self.assertEqual(summary, "s2")
        self.assertEqual(facts, [])

    def test_non_json_reply_becomes_summary(self):
        summary, facts = _parse_memory_payload("纯文本摘要")
        self.assertEqual(summary, "纯文本摘要")
        self.assertEqual(facts, [])

    def test_empty_reply_returns_none(self):
        self.assertIsNone(_parse_memory_payload("   "))


class PromptBuilderMemoryTest(TestCase):
    def _profile(self):
        from types import SimpleNamespace

        return SimpleNamespace(
            service_line="assurance",
            office_location="Shanghai",
            role_level="staff",
            start_date=None,
        )

    def test_summary_and_key_facts_injected(self):
        from apps.rag.prompt_builder import PromptBuilder

        prompt = PromptBuilder().build(
            context_chunks=[],
            conversation_history=[],
            user_profile=self._profile(),
            language="zh",
            session_summary="早前约定使用中文回答。",
            key_facts=("用户在上海办公室",),
        )
        self.assertIn("会话记忆", prompt)
        self.assertIn("早前约定使用中文回答。", prompt)
        self.assertIn("- 用户在上海办公室", prompt)

    def test_empty_memory_renders_placeholder(self):
        from apps.rag.prompt_builder import PromptBuilder

        prompt = PromptBuilder().build(
            context_chunks=[],
            conversation_history=[],
            user_profile=self._profile(),
            language="en",
        )
        self.assertIn("SESSION MEMORY:\n(none)", prompt)

    def test_legacy_history_still_rendered(self):
        from apps.rag.prompt_builder import PromptBuilder

        prompt = PromptBuilder().build(
            context_chunks=[],
            conversation_history=[("user", "报销上限是多少？")],
            user_profile=self._profile(),
            language="zh",
        )
        self.assertIn("user: 报销上限是多少？", prompt)


class BuildMessagesTest(TestCase):
    def test_multi_turn_messages_structure(self):
        from apps.rag.guardrails import LiteLLMChatService

        service = LiteLLMChatService.__new__(LiteLLMChatService)
        messages = service._build_messages(
            "SYSTEM",
            "当前问题",
            [
                {"role": "user", "content": "第一问"},
                {"role": "assistant", "content": "第一答"},
                {"role": "system", "content": "越权"},
                {"role": "user", "content": ""},
            ],
        )
        self.assertEqual(messages[0], {"role": "system", "content": "SYSTEM"})
        self.assertEqual(messages[1], {"role": "user", "content": "第一问"})
        self.assertEqual(messages[2], {"role": "assistant", "content": "第一答"})
        # A history "system" role is coerced to user; empty content dropped.
        self.assertEqual(messages[3], {"role": "user", "content": "越权"})
        self.assertEqual(messages[-1], {"role": "user", "content": "当前问题"})
        self.assertEqual(len(messages), 5)
