# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Session-scoped conversation memory.

Single source of truth for the context handed to the RAG pipeline:

- Short-term memory: a token-budgeted window of the most recent messages
  (replaces the legacy count-based ``_conversation_history`` that lived in
  both ``views.py`` and ``generation.py``).
- Long-term memory: the rolling ``SessionMemory`` summary + key facts
  maintained asynchronously by ``apps.chat.tasks.update_session_memory``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)

# Upper bound on messages fetched from the DB — far above what any sane
# token budget can hold, purely to bound the query.
_MAX_FETCH_MESSAGES = 60

# Marker inserted where an overly long message was middle-truncated.
_TRUNCATION_MARKER = "\n…[内容过长，中间部分已省略]…\n"


def estimate_tokens(text: str) -> int:
    """Best-effort token estimate (tiktoken cl100k_base with a cheap fallback)."""
    if not text:
        return 0
    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def truncate_middle(content: str, cap_tokens: int) -> str:
    """Keep head and tail of an overly long message, dropping the middle.

    Guarantees one long message cannot evict the entire history window.
    """
    if cap_tokens <= 0:
        return content
    total = estimate_tokens(content)
    if total <= cap_tokens:
        return content
    ratio = cap_tokens / total
    head_chars = max(1, int(len(content) * ratio * 0.6))
    tail_chars = max(1, int(len(content) * ratio * 0.25))
    return content[:head_chars] + _TRUNCATION_MARKER + content[-tail_chars:]


@dataclass(frozen=True)
class MemoryContext:
    """Everything the pipeline needs to stay context-aware in one session."""

    summary: str = ""
    key_facts: tuple[str, ...] = ()
    recent_history: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def history_messages(self) -> list[dict]:
        """Recent history as a standard multi-turn messages array."""
        return [
            {
                "role": role if role in ("user", "assistant") else "user",
                "content": content,
            }
            for role, content in self.recent_history
        ]

    def __len__(self):  # keeps `if conversation_history:` style checks working
        return len(self.recent_history)

    def __iter__(self):
        return iter(self.recent_history)


def build_memory_context(
    session,
    question_message=None,
    *,
    token_budget: int | None = None,
    message_token_cap: int | None = None,
) -> MemoryContext:
    """Build the layered memory context for one turn.

    Selects messages newest-first until the token budget is exhausted
    (always keeping at least the newest message), middle-truncating any
    single message above the per-message cap, then restores chronological
    order. The rolling session summary and key facts are attached when
    session memory is enabled.
    """
    from .models import Message, SessionMemory

    budget = token_budget or getattr(settings, "CHAT_HISTORY_TOKEN_BUDGET", 2000)
    cap = message_token_cap or getattr(
        settings, "CHAT_HISTORY_MESSAGE_TOKEN_CAP", 600
    )

    queryset = Message.objects.filter(session=session)
    if question_message is not None:
        queryset = queryset.exclude(pk=question_message.pk)
    rows = list(
        queryset.order_by("-created_at")[:_MAX_FETCH_MESSAGES].values_list(
            "role", "content"
        )
    )

    selected: list[tuple[str, str]] = []
    used = 0
    for role, content in rows:  # newest → oldest
        trimmed = truncate_middle(content or "", cap)
        cost = estimate_tokens(trimmed) + 4  # +4: role/format overhead
        if selected and used + cost > budget:
            break
        selected.append((role, trimmed))
        used += cost
        if used >= budget:
            break
    selected.reverse()

    summary = ""
    key_facts: tuple[str, ...] = ()
    if getattr(settings, "CHAT_MEMORY_ENABLED", False):
        try:
            memory = (
                SessionMemory.objects.filter(session=session)
                .only("summary", "key_facts")
                .first()
            )
            if memory is not None:
                summary = memory.summary or ""
                key_facts = tuple(
                    str(fact)[:300] for fact in (memory.key_facts or [])[:12]
                )
        except Exception:
            # Memory must never break a turn — degrade to window-only context.
            logger.warning("session_memory_load_failed session_id=%s", session.pk)

    return MemoryContext(
        summary=summary,
        key_facts=key_facts,
        recent_history=tuple(selected),
    )
