# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Optional LLM reranking of retrieved chunks (KB/RAG audit spec P2 §A8).

Disabled by default (``RAG_LLM_RERANK_ENABLED = False``). When enabled, the
final (already diversified) top-k chunks are re-ordered by a single light
LLM call. Strictly best-effort: any failure or malformed output returns the
original ordering, and confidence classification is unaffected because it
reads ``rerank_score`` values, not positions.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

MAX_SNIPPET_CHARS = 300

RERANK_SYSTEM_PROMPT = (
    "You are a search result reranker. Given a query and numbered passages, "
    "reply ONLY with the passage numbers ordered from most to least relevant, "
    "comma-separated (e.g. 2,0,1). No other text."
)


def _parse_order(raw: str, count: int) -> list[int] | None:
    """Parse a comma/space separated index list; None when unusable."""
    indices = [int(m) for m in re.findall(r"\d+", raw or "")]
    seen: list[int] = []
    for index in indices:
        if 0 <= index < count and index not in seen:
            seen.append(index)
    if not seen:
        return None
    # Preserve original relative order for anything the model omitted.
    seen.extend(i for i in range(count) if i not in seen)
    return seen


def llm_rerank(query: str, chunks: list[dict], llm) -> list[dict]:
    """Reorder ``chunks`` by LLM-judged relevance. Never raises."""
    if len(chunks) < 2:
        return chunks
    try:
        numbered = "\n\n".join(
            f"[{i}] {(chunk.get('content') or '')[:MAX_SNIPPET_CHARS]}"
            for i, chunk in enumerate(chunks)
        )
        user_prompt = f"Query: {query}\n\nPassages:\n{numbered}"
        raw = "".join(llm.stream_chat(RERANK_SYSTEM_PROMPT, user_prompt))
        order = _parse_order(raw, len(chunks))
        if order is None:
            logger.warning("[llm-rerank] unusable output: %.80s", raw)
            return chunks
        return [chunks[i] for i in order]
    except Exception as exc:  # pragma: no cover — rerank must never break chat
        logger.warning("[llm-rerank] failed, keeping original order: %s", exc)
        return chunks
