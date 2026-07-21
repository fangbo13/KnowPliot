"""Server-owned fixed-model and independent-thinking policy resolution."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.conf import settings

from .models import ModelProfile, resolve_effective_policy

ANSWER_MODE_FAST = "fast"
ANSWER_MODE_DEEP = "deep"
CANONICAL_FAST_MODEL = "qwen3.6-flash"
CANONICAL_DEEP_MODEL = "qwen3.7-plus"
DEFAULT_FAST_MODEL = CANONICAL_FAST_MODEL
DEFAULT_DEEP_MODEL = CANONICAL_DEEP_MODEL
DEFAULT_PROVIDER = "dashscope"
DEFAULT_THINKING_BUDGET = 1024


class GenerationPolicyNotReady(RuntimeError):
    """A bounded fail-closed signal raised before a new Turn is created."""

    code = "model_policy_not_ready"

    def __init__(self, reason: str = "model_policy_not_ready"):
        self.reason = reason
        super().__init__(self.code)


@dataclass(frozen=True)
class GenerationPolicy:
    answer_mode: str
    provider: str
    model_id: str
    model_profile_id: UUID
    thinking_enabled: bool
    thinking_budget: int | None
    fallback_code: str = ""


def _profile(profile_id: object) -> ModelProfile | None:
    if not profile_id:
        return None
    try:
        parsed = UUID(str(profile_id))
    except (TypeError, ValueError, AttributeError):
        return None
    return ModelProfile.objects.filter(pk=parsed, enabled=True).first()


def _legacy_aliases_match() -> bool:
    for setting_name in ("QWEN_CHAT_MODEL", "RAG_LLM_MODEL"):
        if not hasattr(settings, setting_name):
            continue
        if getattr(settings, setting_name) != CANONICAL_FAST_MODEL:
            return False
    return True


def _canonical_profile(values: dict, key: str, expected_model: str) -> ModelProfile:
    configured_id = values.get(key)
    profile = _profile(configured_id)
    if profile is None or profile.model_id != expected_model:
        raise GenerationPolicyNotReady(f"{key}_unavailable")
    return profile


def _valid_budget(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 32768


def resolve_generation_policy(
    space,
    requested_mode: str,
    requested_thinking_enabled: bool = False,
) -> GenerationPolicy:
    """Resolve fixed server policy without accepting browser model authority.

    A missing/mismatched canonical binding or legacy alias is a readiness error.
    Flag/policy races after authorization may safely downgrade effective mode or
    thinking while preserving the caller's requested snapshot on ``ChatTurn``.
    """

    if requested_mode not in {ANSWER_MODE_FAST, ANSWER_MODE_DEEP}:
        raise ValueError("unsupported_answer_mode")
    if not _legacy_aliases_match():
        raise GenerationPolicyNotReady("legacy_alias_mismatch")

    values = resolve_effective_policy(space)
    fast_profile = _canonical_profile(
        values,
        "fast_model_profile_id",
        CANONICAL_FAST_MODEL,
    )
    profile = fast_profile
    effective_mode = ANSWER_MODE_FAST
    fallback_code = ""

    if requested_mode == ANSWER_MODE_DEEP:
        if bool(getattr(settings, "DEEP_ANSWER_MODE", False)):
            profile = _canonical_profile(
                values,
                "deep_model_profile_id",
                CANONICAL_DEEP_MODEL,
            )
            effective_mode = ANSWER_MODE_DEEP
        else:
            fallback_code = "deep_mode_disabled"

    thinking_enabled = False
    thinking_budget = None
    if requested_thinking_enabled:
        if not bool(getattr(settings, "THINKING_MODE", False)):
            fallback_code = fallback_code or "thinking_mode_disabled"
        else:
            budget_key = f"{effective_mode}_thinking_budget"
            budget = values.get(budget_key, DEFAULT_THINKING_BUDGET)
            if _valid_budget(budget):
                thinking_enabled = True
                thinking_budget = budget
            else:
                fallback_code = fallback_code or "thinking_budget_invalid"

    return GenerationPolicy(
        answer_mode=effective_mode,
        provider=profile.provider,
        model_id=profile.model_id,
        model_profile_id=profile.id,
        thinking_enabled=thinking_enabled,
        thinking_budget=thinking_budget,
        fallback_code=fallback_code,
    )


def deep_mode_available(space) -> bool:
    """Return whether the selected space has an exact governed deep path."""

    if not bool(getattr(settings, "DEEP_ANSWER_MODE", False)):
        return False
    try:
        result = resolve_generation_policy(space, ANSWER_MODE_DEEP, False)
    except GenerationPolicyNotReady:
        return False
    return result.answer_mode == ANSWER_MODE_DEEP


def thinking_mode_available(space) -> bool:
    """Return independent thinking availability for a non-guest membership."""

    if not bool(getattr(settings, "THINKING_MODE", False)):
        return False
    try:
        result = resolve_generation_policy(space, ANSWER_MODE_FAST, True)
    except GenerationPolicyNotReady:
        return False
    return result.thinking_enabled
