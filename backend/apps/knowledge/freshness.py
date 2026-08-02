# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §4 L3 — freshness scoring.

freshness = 0.5 ** (age_days / half_life_days)

The half-life is space-configurable via KnowledgeSpace.settings
["freshness_half_life_days"], default 365. ``last_reviewed_at`` (owner
"confirm still fresh") counts as an update for age purposes so confirming
freshness genuinely restores retrieval weight.
"""

from __future__ import annotations

from django.utils import timezone

DEFAULT_HALF_LIFE_DAYS = 365
DEFAULT_STALE_AFTER_DAYS = 540


def space_half_life_days(space) -> int:
    try:
        value = int((space.settings or {}).get("freshness_half_life_days", 0))
        return value if value > 0 else DEFAULT_HALF_LIFE_DAYS
    except (TypeError, ValueError, AttributeError):
        return DEFAULT_HALF_LIFE_DAYS


def space_stale_after_days(space) -> int:
    try:
        value = int((space.settings or {}).get("stale_after_days", 0))
        return value if value > 0 else DEFAULT_STALE_AFTER_DAYS
    except (TypeError, ValueError, AttributeError):
        return DEFAULT_STALE_AFTER_DAYS


def freshness_reference_time(document):
    """Most recent of updated_at / last_reviewed_at — the effective 'age zero'."""
    candidates = [document.updated_at, getattr(document, "last_reviewed_at", None)]
    candidates = [c for c in candidates if c is not None]
    return max(candidates) if candidates else None


def compute_freshness(document, *, half_life_days: int = DEFAULT_HALF_LIFE_DAYS) -> float:
    """Exponential decay freshness in [0, 1]. Unknown age scores 1.0."""
    reference = freshness_reference_time(document)
    if reference is None:
        return 1.0
    age_days = max((timezone.now() - reference).total_seconds() / 86400.0, 0.0)
    return round(0.5 ** (age_days / max(half_life_days, 1)), 4)
