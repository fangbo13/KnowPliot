"""Server-owned generation policy resolution for one knowledge space."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.conf import settings

from .models import ModelProfile, resolve_effective_policy

ANSWER_MODE_FAST = "fast"
ANSWER_MODE_DEEP = "deep"
DEFAULT_FAST_MODEL = "qwen-plus"
DEFAULT_DEEP_MODEL = "qwen3.7-plus"
DEFAULT_PROVIDER = "dashscope"
DEFAULT_DEEP_THINKING_BUDGET = 1024


@dataclass(frozen=True)
class GenerationPolicy:
    answer_mode: str
    provider: str
    model_id: str
    model_profile_id: UUID | None
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


def _fast_policy(values: dict, *, fallback_code: str = "") -> GenerationPolicy:
    configured_id = values.get("fast_model_profile_id") or values.get("model_profile")
    profile = _profile(configured_id)
    return GenerationPolicy(
        answer_mode=ANSWER_MODE_FAST,
        provider=profile.provider if profile else DEFAULT_PROVIDER,
        model_id=(
            profile.model_id
            if profile
            else getattr(settings, "RAG_LLM_MODEL", DEFAULT_FAST_MODEL)
        ),
        model_profile_id=profile.id if profile else None,
        thinking_enabled=False,
        thinking_budget=None,
        fallback_code=fallback_code,
    )


def resolve_generation_policy(space, requested_mode: str) -> GenerationPolicy:
    """Resolve defaults < organization < space and fail safely to fast."""

    values = resolve_effective_policy(space)
    fast = _fast_policy(values)
    if requested_mode != ANSWER_MODE_DEEP:
        return fast
    if not bool(getattr(settings, "DEEP_ANSWER_MODE", False)):
        return _fast_policy(values, fallback_code="deep_mode_disabled")

    configured_id = values.get("deep_model_profile_id")
    if configured_id:
        profile = _profile(configured_id)
        if profile is None:
            return _fast_policy(values, fallback_code="deep_profile_unavailable")
        provider = profile.provider
        model_id = profile.model_id
        profile_id = profile.id
    else:
        provider = DEFAULT_PROVIDER
        model_id = DEFAULT_DEEP_MODEL
        profile_id = None

    budget = values.get("deep_thinking_budget", DEFAULT_DEEP_THINKING_BUDGET)
    if (
        isinstance(budget, bool)
        or not isinstance(budget, int)
        or not 1 <= budget <= 32768
    ):
        return _fast_policy(values, fallback_code="deep_budget_invalid")
    return GenerationPolicy(
        answer_mode=ANSWER_MODE_DEEP,
        provider=provider,
        model_id=model_id,
        model_profile_id=profile_id,
        thinking_enabled=True,
        thinking_budget=budget,
    )


def deep_mode_available(space) -> bool:
    """Return whether this space currently has a usable governed deep path."""

    return (
        resolve_generation_policy(space, ANSWER_MODE_DEEP).answer_mode
        == ANSWER_MODE_DEEP
    )
