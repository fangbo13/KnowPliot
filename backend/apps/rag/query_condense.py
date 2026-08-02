# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Follow-up query condensation for retrieval.

Context-dependent follow-ups ("那第二条呢？" / "what about it?") embed poorly
and break retrieval. When a query looks contextual, one fast LLM call rewrites
it into a standalone question using the session memory. The rewrite is used
for retrieval ONLY — the user's original wording still goes to the answer LLM,
so a bad rewrite can never contaminate the answer itself.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

# Fail fast: retrieval must not stall behind a slow rewrite call.
_REWRITE_TIMEOUT_SECONDS = 2.5
_MAX_REWRITE_OUTPUT_CHARS = 512
# Queries this short are almost always context-dependent follow-ups.
_SHORT_QUERY_CHARS = 12
# History lines fed to the rewriter (freshest rounds only).
_HISTORY_LINES = 6
_HISTORY_LINE_CHARS = 400

# Anaphora / follow-up markers (CJK + English).
_CONTEXTUAL_PATTERN = re.compile(
    r"它|他们|她们|它们|这个|那个|这些|那些|该|上面|前面|刚才|之前|上述|其中"
    r"|第[一二三四五六七八九十百0-9]+[条点项个章节步]"
    r"|呢[？?]?$|还有呢|继续|详细说|展开|再说说|为什么呢"
    r"|\b(it|its|this|that|these|those|they|them|the above|the previous)\b"
    r"|\bwhat about\b|\bhow about\b|\band then\b|\btell me more\b",
    re.IGNORECASE,
)


def looks_contextual(query: str, has_history: bool) -> bool:
    """Gate: rewrite only when history exists and the query needs context."""
    if not has_history:
        return False
    stripped = (query or "").strip()
    if not stripped:
        return False
    if len(stripped) <= _SHORT_QUERY_CHARS:
        return True
    return bool(_CONTEXTUAL_PATTERN.search(stripped))


def _memory_snippet(summary: str, recent_history) -> str:
    parts = []
    if summary:
        parts.append(f"[早前对话摘要]\n{summary}")
    lines = []
    for role, content in list(recent_history)[-_HISTORY_LINES:]:
        text = (content or "").strip()
        if not text:
            continue
        lines.append(f"{role}: {text[:_HISTORY_LINE_CHARS]}")
    if lines:
        parts.append("[近期对话]\n" + "\n".join(lines))
    return "\n\n".join(parts)


_REWRITE_SYSTEM_PROMPT = (
    "You rewrite a follow-up question into ONE standalone, self-contained "
    "question for knowledge-base retrieval, resolving all pronouns and "
    "references using the provided conversation memory. Keep the original "
    "language of the question. Output ONLY the rewritten question — no "
    "explanation, no quotes, no prefix."
)


def condense_query(query: str, *, summary: str = "", recent_history=(), language: str = "en") -> str:
    """Return a standalone retrieval query, or the original on any failure."""
    if not getattr(settings, "CHAT_QUERY_REWRITE_ENABLED", False):
        return query
    if not looks_contextual(query, bool(summary) or bool(recent_history)):
        return query

    snippet = _memory_snippet(summary, recent_history)
    if not snippet:
        return query

    try:
        from .guardrails import get_llm_service

        llm = get_llm_service()
        rewritten = llm.complete(
            _REWRITE_SYSTEM_PROMPT,
            f"{snippet}\n\n[追问原文]\n{query}\n\n[独立问题]",
            max_tokens=128,
            temperature=0.0,
            timeout=_REWRITE_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.info("query_condense_failed code=rewrite_fallback")
        return query

    rewritten = (rewritten or "").strip().strip('"').strip()
    # Reject degenerate rewrites — retrieval falls back to the raw query.
    if not rewritten or len(rewritten) > _MAX_REWRITE_OUTPUT_CHARS:
        return query
    if "\n" in rewritten:
        rewritten = rewritten.splitlines()[0].strip()
        if not rewritten:
            return query
    logger.info("query_condensed original_len=%d rewritten_len=%d", len(query), len(rewritten))
    return rewritten
