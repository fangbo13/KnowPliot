# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Deep-mode self-critique (RAG optimization spec Phase 6).

Draft → critique → revise, strictly bounded to ONE critic round. The critic
is anchored to the retrieved context + the original question ONLY — its sole
mandate is deleting/correcting claims the context does not support, which
pulls a drifted ("辩偏") answer back onto the evidence.

Every step is fail-open: any error returns the draft untouched. Fast mode
never enters this path, so its latency is unchanged.
"""

import logging

logger = logging.getLogger(__name__)

_CRITIQUE_TIMEOUT_SECONDS = 20
_CRITIQUE_MAX_TOKENS = 400
_REVISE_TIMEOUT_SECONDS = 30
_NO_ISSUE_MARKER = "OK"

_CRITIC_SYSTEM_PROMPT = (
    "You are a strict evidence auditor for a knowledge-base assistant. "
    "You judge a DRAFT answer against ONLY two anchors: the CONTEXT documents "
    "and the QUESTION. List every claim in the draft that the context does "
    "not support or that contradicts the context, one per line. Ignore style. "
    f"If every claim is supported, reply exactly '{_NO_ISSUE_MARKER}'."
)

_REVISE_SYSTEM_PROMPT = (
    "You revise a DRAFT answer for a knowledge-base assistant. Apply the "
    "CRITIQUE: delete or correct every unsupported/contradicted claim so the "
    "final answer states only what the CONTEXT documents support, keeping "
    "citations, formatting and the draft's language. Output ONLY the revised "
    "answer."
)


def critique_and_revise(llm, *, question: str, context: str, draft: str) -> str:
    """One bounded critique round. Returns the revised (or original) draft."""
    if not (draft or "").strip():
        return draft
    try:
        critique = llm.complete(
            _CRITIC_SYSTEM_PROMPT,
            f"[QUESTION]\n{question}\n\n[CONTEXT]\n{context}\n\n[DRAFT]\n{draft}",
            max_tokens=_CRITIQUE_MAX_TOKENS,
            temperature=0.0,
            timeout=_CRITIQUE_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("self_critique_failed code=critique_error")
        return draft
    critique = (critique or "").strip()
    if not critique or critique.upper().startswith(_NO_ISSUE_MARKER):
        logger.info("self_critique_clean draft_len=%d", len(draft))
        return draft
    try:
        revised = llm.complete(
            _REVISE_SYSTEM_PROMPT,
            f"[QUESTION]\n{question}\n\n[CONTEXT]\n{context}\n\n"
            f"[DRAFT]\n{draft}\n\n[CRITIQUE]\n{critique}",
            max_tokens=2000,
            temperature=0.0,
            timeout=_REVISE_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("self_critique_revise_failed code=revise_error")
        return draft
    revised = (revised or "").strip()
    if not revised:
        return draft
    logger.info(
        "self_critique_revised draft_len=%d revised_len=%d", len(draft), len(revised)
    )
    return revised
