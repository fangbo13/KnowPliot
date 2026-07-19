"""Governed fixed-model and independent-thinking policy contracts."""

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.spaces.generation_policy import (
    ANSWER_MODE_DEEP,
    ANSWER_MODE_FAST,
    GenerationPolicyNotReady,
    deep_mode_available,
    resolve_generation_policy,
    thinking_mode_available,
)
from apps.spaces.models import GovernancePolicy, ModelProfile, Organization
from apps.spaces.ownership import create_space_with_owner


@override_settings(
    RAG_LLM_MODEL="qwen3.6-flash",
    QWEN_CHAT_MODEL="qwen3.6-flash",
)
class GenerationPolicyResolutionTest(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="generation-policy-owner",
            email="generation-policy-owner@example.test",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Generation Policy Org",
            slug="generation-policy-org",
        )
        self.space = create_space_with_owner(
            organization=self.organization,
            owner=self.owner,
            name="Generation Policy Space",
            code="generation-policy-space",
        )
        self.fast = ModelProfile.objects.create(
            name="canonical-fast",
            provider="dashscope",
            model_id="qwen3.6-flash",
        )
        self.deep = ModelProfile.objects.create(
            name="canonical-deep",
            provider="dashscope",
            model_id="qwen3.7-plus",
        )
        self.policy = GovernancePolicy.objects.create(
            space=self.space,
            values={
                "fast_model_profile_id": str(self.fast.id),
                "deep_model_profile_id": str(self.deep.id),
                "fast_thinking_budget": 1024,
                "deep_thinking_budget": 2048,
            },
        )

    @override_settings(DEEP_ANSWER_MODE=True, THINKING_MODE=True)
    def test_all_four_mode_thinking_combinations_are_independent(self):
        fast_off = resolve_generation_policy(self.space, ANSWER_MODE_FAST, False)
        fast_on = resolve_generation_policy(self.space, ANSWER_MODE_FAST, True)
        deep_off = resolve_generation_policy(self.space, ANSWER_MODE_DEEP, False)
        deep_on = resolve_generation_policy(self.space, ANSWER_MODE_DEEP, True)

        self.assertEqual((fast_off.model_id, fast_off.thinking_enabled), ("qwen3.6-flash", False))
        self.assertIsNone(fast_off.thinking_budget)
        self.assertEqual((fast_on.model_id, fast_on.thinking_enabled), ("qwen3.6-flash", True))
        self.assertEqual(fast_on.thinking_budget, 1024)
        self.assertEqual((deep_off.model_id, deep_off.thinking_enabled), ("qwen3.7-plus", False))
        self.assertIsNone(deep_off.thinking_budget)
        self.assertEqual((deep_on.model_id, deep_on.thinking_enabled), ("qwen3.7-plus", True))
        self.assertEqual(deep_on.thinking_budget, 2048)

    @override_settings(DEEP_ANSWER_MODE=False, THINKING_MODE=True)
    def test_deep_flag_downgrades_only_mode_and_preserves_explicit_thinking(self):
        resolved = resolve_generation_policy(self.space, ANSWER_MODE_DEEP, True)

        self.assertEqual(resolved.answer_mode, ANSWER_MODE_FAST)
        self.assertTrue(resolved.thinking_enabled)
        self.assertEqual(resolved.thinking_budget, 1024)
        self.assertEqual(resolved.fallback_code, "deep_mode_disabled")

    @override_settings(DEEP_ANSWER_MODE=True, THINKING_MODE=False)
    def test_thinking_flag_downgrades_only_thinking(self):
        resolved = resolve_generation_policy(self.space, ANSWER_MODE_DEEP, True)

        self.assertEqual(resolved.answer_mode, ANSWER_MODE_DEEP)
        self.assertFalse(resolved.thinking_enabled)
        self.assertIsNone(resolved.thinking_budget)
        self.assertEqual(resolved.fallback_code, "thinking_mode_disabled")

    @override_settings(DEEP_ANSWER_MODE=True, THINKING_MODE=True)
    def test_disabled_or_mismatched_canonical_profile_fails_closed(self):
        self.deep.enabled = False
        self.deep.save(update_fields=["enabled"])
        with self.assertRaises(GenerationPolicyNotReady):
            resolve_generation_policy(self.space, ANSWER_MODE_DEEP, False)

        self.fast.model_id = "qwen-plus"
        self.fast.save(update_fields=["model_id"])
        with self.assertRaises(GenerationPolicyNotReady):
            resolve_generation_policy(self.space, ANSWER_MODE_FAST, False)

    @override_settings(
        DEEP_ANSWER_MODE=True,
        THINKING_MODE=True,
        RAG_LLM_MODEL="qwen-plus",
        QWEN_CHAT_MODEL="qwen-plus",
    )
    def test_legacy_alias_mismatch_fails_closed(self):
        with self.assertRaises(GenerationPolicyNotReady) as raised:
            resolve_generation_policy(self.space, ANSWER_MODE_FAST, False)

        self.assertEqual(raised.exception.code, "model_policy_not_ready")

    @override_settings(DEEP_ANSWER_MODE=True, THINKING_MODE=True)
    def test_deep_and_thinking_availability_are_independent(self):
        self.assertTrue(deep_mode_available(self.space))
        self.assertTrue(thinking_mode_available(self.space))

        with override_settings(DEEP_ANSWER_MODE=False):
            self.assertFalse(deep_mode_available(self.space))
            self.assertTrue(thinking_mode_available(self.space))
        with override_settings(THINKING_MODE=False):
            self.assertTrue(deep_mode_available(self.space))
            self.assertFalse(thinking_mode_available(self.space))


class GenerationPolicyValidationTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Policy Validation Org",
            slug="policy-validation-org",
        )

    def test_mode_bindings_require_uuid_strings_and_budgets_are_bounded_integers(self):
        invalid_values = [
            {"fast_model_profile_id": "not-a-uuid"},
            {"deep_model_profile_id": 7},
            {"fast_thinking_budget": True},
            {"fast_thinking_budget": 0},
            {"deep_thinking_budget": 32769},
        ]
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                GovernancePolicy.objects.create(
                    organization=self.organization,
                    values=values,
                )

    def test_policy_bindings_remain_uuid_snapshots(self):
        with self.assertRaises(ValidationError):
            GovernancePolicy.objects.create(
                organization=self.organization,
                values={"fast_model_profile_id": str(uuid4()), "unknown": True},
            )
