"""Governed fast/deep generation policy contracts."""

from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.spaces.models import (
    GovernancePolicy,
    KnowledgeSpace,
    ModelProfile,
    Organization,
)

try:
    from apps.spaces.generation_policy import (
        ANSWER_MODE_DEEP,
        ANSWER_MODE_FAST,
        resolve_generation_policy,
    )
except ImportError:  # RED: Task 5 introduces governed generation policy.
    ANSWER_MODE_DEEP = "deep"
    ANSWER_MODE_FAST = "fast"
    resolve_generation_policy = None


class GenerationPolicyResolutionTest(TestCase):
    def setUp(self):
        self.assertIsNotNone(resolve_generation_policy)
        self.organization = Organization.objects.create(
            name="Generation Policy Org",
            slug="generation-policy-org",
        )
        self.space = KnowledgeSpace.objects.create(
            organization=self.organization,
            name="Generation Policy Space",
            code="generation-policy-space",
        )

    @override_settings(DEEP_ANSWER_MODE=True)
    def test_safe_defaults_are_fast_qwen_plus_and_deep_qwen_37(self):
        fast = resolve_generation_policy(self.space, ANSWER_MODE_FAST)
        deep = resolve_generation_policy(self.space, ANSWER_MODE_DEEP)

        self.assertEqual(fast.answer_mode, "fast")
        self.assertEqual(fast.model_id, "qwen-plus")
        self.assertFalse(fast.thinking_enabled)
        self.assertIsNone(fast.thinking_budget)
        self.assertEqual(deep.answer_mode, "deep")
        self.assertEqual(deep.model_id, "qwen3.7-plus")
        self.assertTrue(deep.thinking_enabled)
        self.assertEqual(deep.thinking_budget, 1024)

    @override_settings(DEEP_ANSWER_MODE=True)
    def test_space_binding_overrides_organization_binding_and_budget(self):
        org_deep = ModelProfile.objects.create(
            name="org-deep",
            provider="dashscope",
            model_id="org-deep-model",
        )
        space_deep = ModelProfile.objects.create(
            name="space-deep",
            provider="dashscope",
            model_id="space-deep-model",
        )
        GovernancePolicy.objects.create(
            organization=self.organization,
            values={
                "deep_model_profile_id": str(org_deep.id),
                "deep_thinking_budget": 2048,
            },
        )
        GovernancePolicy.objects.create(
            space=self.space,
            values={
                "deep_model_profile_id": str(space_deep.id),
                "deep_thinking_budget": 4096,
            },
        )

        resolved = resolve_generation_policy(self.space, ANSWER_MODE_DEEP)

        self.assertEqual(resolved.model_id, "space-deep-model")
        self.assertEqual(resolved.model_profile_id, space_deep.id)
        self.assertEqual(resolved.thinking_budget, 4096)

    @override_settings(DEEP_ANSWER_MODE=True)
    def test_explicit_disabled_or_missing_deep_profile_falls_back_to_fast(self):
        fast = ModelProfile.objects.create(
            name="configured-fast",
            provider="dashscope",
            model_id="configured-fast-model",
        )
        disabled = ModelProfile.objects.create(
            name="disabled-deep",
            provider="dashscope",
            model_id="disabled-deep-model",
            enabled=False,
        )
        GovernancePolicy.objects.create(
            space=self.space,
            values={
                "fast_model_profile_id": str(fast.id),
                "deep_model_profile_id": str(disabled.id),
            },
        )

        disabled_result = resolve_generation_policy(self.space, ANSWER_MODE_DEEP)
        self.assertEqual(disabled_result.answer_mode, "fast")
        self.assertEqual(disabled_result.model_id, "configured-fast-model")
        self.assertEqual(disabled_result.fallback_code, "deep_profile_unavailable")

        GovernancePolicy.objects.create(
            space=self.space,
            revision=2,
            values={
                "fast_model_profile_id": str(fast.id),
                "deep_model_profile_id": str(uuid4()),
            },
        )
        missing_result = resolve_generation_policy(self.space, ANSWER_MODE_DEEP)
        self.assertEqual(missing_result.answer_mode, "fast")
        self.assertEqual(missing_result.model_id, "configured-fast-model")
        self.assertEqual(missing_result.fallback_code, "deep_profile_unavailable")

    @override_settings(DEEP_ANSWER_MODE=False)
    def test_default_off_flag_resolves_direct_deep_request_to_fast(self):
        resolved = resolve_generation_policy(self.space, ANSWER_MODE_DEEP)

        self.assertEqual(resolved.answer_mode, "fast")
        self.assertEqual(resolved.model_id, "qwen-plus")
        self.assertEqual(resolved.fallback_code, "deep_mode_disabled")

    @override_settings(DEEP_ANSWER_MODE=False)
    def test_fast_profile_binding_applies_while_deep_rollout_is_disabled(self):
        from apps.chat.views import _request_generation_policy

        fast = ModelProfile.objects.create(
            name="rollout-independent-fast",
            provider="dashscope",
            model_id="governed-fast-model",
        )
        GovernancePolicy.objects.create(
            space=self.space,
            values={"fast_model_profile_id": str(fast.id)},
        )

        resolved = _request_generation_policy(self.space, ANSWER_MODE_FAST)

        self.assertEqual(resolved.answer_mode, ANSWER_MODE_FAST)
        self.assertEqual(resolved.model_id, "governed-fast-model")
        self.assertFalse(resolved.thinking_enabled)


class GenerationPolicyValidationTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Policy Validation Org",
            slug="policy-validation-org",
        )

    def test_mode_bindings_require_uuid_strings_and_budget_is_bounded_integer(self):
        invalid_values = [
            {"fast_model_profile_id": "not-a-uuid"},
            {"deep_model_profile_id": 7},
            {"deep_thinking_budget": True},
            {"deep_thinking_budget": 0},
            {"deep_thinking_budget": 32769},
        ]
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                GovernancePolicy.objects.create(
                    organization=self.organization,
                    values=values,
                )
