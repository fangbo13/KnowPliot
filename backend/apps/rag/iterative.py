# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Agentic retrieval refinement (RAG optimization spec Phase 5).

Sufficiency judgement reuses ``classify_confidence``: high/medium evidence
stops retrieval and answers directly; low/insufficient triggers ONE bounded
refinement round — an LLM query rewrite followed by a second search whose
results are merged (dedup by chunk id) with the first round.

Stop conditions (any one): confidence reached medium+, round budget
exhausted, or the refined search adds no new chunks. Failures at any step
degrade silently to the first-round results — refinement must never break
a chat turn.
"""

import logging

from .hybrid import classify_confidence

logger = logging.getLogger(__name__)

_REWRITE_TIMEOUT_SECONDS = 2.5
_MAX_REWRITE_CHARS = 256

_REFINE_SYSTEM_PROMPT = (
    "You rewrite a knowledge-base search query whose first attempt returned "
    "weak results. Extract the core entities/terms and produce ONE broader "
    "alternative query in the SAME language — expand abbreviations, add "
    "synonyms, drop filler words. Output ONLY the rewritten query."
)


def _rewrite_query(query: str, llm) -> str | None:
    """One bounded LLM rewrite; None on any failure or degenerate output."""
    try:
        rewritten = llm.complete(
            _REFINE_SYSTEM_PROMPT,
            query,
            max_tokens=96,
            temperature=0.0,
            timeout=_REWRITE_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.info("retrieval_refine_rewrite_failed code=rewrite_fallback")
        return None
    rewritten = (rewritten or "").strip().strip('"').strip()
    if not rewritten or len(rewritten) > _MAX_REWRITE_CHARS:
        return None
    if "\n" in rewritten:
        rewritten = rewritten.splitlines()[0].strip()
    if not rewritten or rewritten == query:
        return None
    return rewritten


def retrieve_with_refinement(
    retriever,
    query: str,
    *,
    llm,
    max_rounds: int,
    search_kwargs: dict,
):
    """Bounded multi-round retrieval. Returns (chunks, rounds_used, refined).

    Round 1 always runs. Further rounds run only while confidence stays
    low/insufficient and the budget allows; merged results keep first-round
    ordering first (dedup by chunk id) and are re-classified after merge.
    """
    chunks = retriever.search(query=query, **search_kwargs)
    rounds_used = 1
    refined = False
    while rounds_used < max_rounds:
        quality = classify_confidence(chunks)
        if quality.label not in {"low", "insufficient"}:
            break
        rewritten = _rewrite_query(query, llm)
        if rewritten is None:
            break
        try:
            extra = retriever.search(query=rewritten, **search_kwargs)
        except Exception:
            logger.warning("retrieval_refine_search_failed", exc_info=True)
            break
        rounds_used += 1
        seen = {str(chunk["id"]) for chunk in chunks}
        new_chunks = [c for c in extra if str(c["id"]) not in seen]
        if not new_chunks:
            logger.info("retrieval_refine_no_new_chunks rounds=%d", rounds_used)
            break
        refined = True
        # Merge: keep round-1 ranking first, then novel refined results,
        # bounded to the caller's top_k.
        top_k = int(search_kwargs.get("top_k") or len(chunks) or 8)
        chunks = (chunks + new_chunks)[: max(top_k, len(chunks))]
        logger.info(
            "retrieval_refined rounds=%d added=%d rewritten='%.60s'",
            rounds_used, len(new_chunks), rewritten,
        )
    return chunks, rounds_used, refined
