"""V3 independent-thinking, fixed-model, and snapshot contracts."""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from django.test import SimpleTestCase, override_settings

from apps.chat.models import ChatTurn
from apps.chat.serializers import ChatMessageRequestSerializer, ChatTurnStatusSerializer


class IndependentThinkingSchemaContractTest(SimpleTestCase):
    def test_turn_exposes_requested_and_effective_execution_snapshot(self):
        fields = {field.name: field for field in ChatTurn._meta.get_fields()}

        self.assertIn("requested_answer_mode", fields)
        self.assertIn("requested_thinking_enabled", fields)
        self.assertIn("thinking_enabled", fields)
        self.assertIn("thinking_snapshot_known", fields)
        self.assertIn("thinking_budget", fields)
        self.assertIn("policy_fallback_code", fields)

    def test_send_accepts_only_mode_and_independent_thinking_as_policy_inputs(self):
        serializer = ChatMessageRequestSerializer(
            data={
                "content": "Question",
                "client_request_id": str(uuid4()),
                "answer_mode": "deep",
                "thinking_enabled": True,
                "protocol_version": 2,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertTrue(serializer.validated_data["thinking_enabled"])

    def test_client_model_or_budget_authority_is_rejected_with_stable_code(self):
        for forbidden_field, value in (
            ("model_id", "forged-model"),
            ("model_profile_id", str(uuid4())),
            ("provider", "forged-provider"),
            ("thinking_budget", 32000),
        ):
            with self.subTest(forbidden_field=forbidden_field):
                serializer = ChatMessageRequestSerializer(
                    data={"content": "Question", forbidden_field: value}
                )
                self.assertFalse(serializer.is_valid())
                self.assertEqual(
                    serializer.errors.get("code"),
                    "client_policy_authority_forbidden",
                )

    def test_status_serializer_has_one_truthful_read_only_snapshot(self):
        expected = {
            "requested_answer_mode",
            "answer_mode",
            "requested_thinking_enabled",
            "thinking_enabled",
            "thinking_snapshot_known",
            "thinking_budget",
            "model_id",
            "policy_fallback_code",
        }

        self.assertTrue(expected.issubset(set(ChatTurnStatusSerializer.Meta.fields)))


class FixedModelIndependentThinkingPolicyTest(SimpleTestCase):
    def _profiles(self):
        fast_id = uuid4()
        deep_id = uuid4()
        profiles = {
            fast_id: SimpleNamespace(
                id=fast_id,
                provider="dashscope",
                model_id="qwen3.6-flash",
                enabled=True,
            ),
            deep_id: SimpleNamespace(
                id=deep_id,
                provider="dashscope",
                model_id="qwen3.7-plus",
                enabled=True,
            ),
        }
        values = {
            "fast_model_profile_id": str(fast_id),
            "deep_model_profile_id": str(deep_id),
            "fast_thinking_budget": 1024,
            "deep_thinking_budget": 2048,
        }
        return profiles, values

    @override_settings(
        DEEP_ANSWER_MODE=True,
        THINKING_MODE=True,
        RAG_LLM_MODEL="qwen3.6-flash",
        QWEN_CHAT_MODEL="qwen3.6-flash",
    )
    def test_all_four_mode_thinking_combinations_are_independent(self):
        from apps.spaces import generation_policy as policy

        profiles, values = self._profiles()

        def get_profile(profile_id):
            return profiles.get(UUID(str(profile_id)))

        with (
            patch.object(policy, "resolve_effective_policy", return_value=values),
            patch.object(policy, "_profile", side_effect=get_profile),
        ):
            fast_off = policy.resolve_generation_policy(object(), "fast", False)
            fast_on = policy.resolve_generation_policy(object(), "fast", True)
            deep_off = policy.resolve_generation_policy(object(), "deep", False)
            deep_on = policy.resolve_generation_policy(object(), "deep", True)

        self.assertEqual((fast_off.model_id, fast_off.thinking_enabled), ("qwen3.6-flash", False))
        self.assertIsNone(fast_off.thinking_budget)
        self.assertEqual((fast_on.model_id, fast_on.thinking_enabled), ("qwen3.6-flash", True))
        self.assertEqual(fast_on.thinking_budget, 1024)
        self.assertEqual((deep_off.model_id, deep_off.thinking_enabled), ("qwen3.7-plus", False))
        self.assertIsNone(deep_off.thinking_budget)
        self.assertEqual((deep_on.model_id, deep_on.thinking_enabled), ("qwen3.7-plus", True))
        self.assertEqual(deep_on.thinking_budget, 2048)

    @override_settings(
        DEEP_ANSWER_MODE=True,
        THINKING_MODE=True,
        RAG_LLM_MODEL="qwen-plus",
        QWEN_CHAT_MODEL="qwen3.6-flash",
    )
    def test_mismatched_legacy_alias_fails_closed(self):
        from apps.spaces import generation_policy as policy

        profiles, values = self._profiles()
        with (
            patch.object(policy, "resolve_effective_policy", return_value=values),
            patch.object(
                policy,
                "_profile",
                side_effect=lambda profile_id: profiles[UUID(str(profile_id))],
            ),
            self.assertRaises(policy.GenerationPolicyNotReady) as raised,
        ):
            policy.resolve_generation_policy(object(), "fast", False)

        self.assertEqual(raised.exception.code, "model_policy_not_ready")

    @override_settings(
        DEEP_ANSWER_MODE=True,
        THINKING_MODE=True,
        RAG_LLM_MODEL="qwen3.6-flash",
        QWEN_CHAT_MODEL="qwen3.6-flash",
    )
    def test_invalid_thinking_budget_falls_back_off_without_changing_mode(self):
        from apps.spaces import generation_policy as policy

        profiles, values = self._profiles()
        values["fast_thinking_budget"] = True
        with (
            patch.object(policy, "resolve_effective_policy", return_value=values),
            patch.object(
                policy,
                "_profile",
                side_effect=lambda profile_id: profiles[UUID(str(profile_id))],
            ),
        ):
            result = policy.resolve_generation_policy(object(), "fast", True)

        self.assertEqual(result.answer_mode, "fast")
        self.assertFalse(result.thinking_enabled)
        self.assertIsNone(result.thinking_budget)
        self.assertEqual(result.fallback_code, "thinking_budget_invalid")
