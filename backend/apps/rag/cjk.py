# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""CJK-aware tokenization for lexical search (KB/RAG audit spec P1 §A6).

PostgreSQL FTS with the ``simple`` config splits on whitespace, so unspaced
Chinese runs collapse into one giant token and never match query terms. We fix
this without new dependencies by emitting character bigrams for CJK runs
(the classic bigram/n-gram CJK indexing approach) on BOTH sides:

- ingest side: chunk title+content -> space-joined token string stored in
  ``DocumentChunk.content_tokens`` (indexed by FTS as normal words);
- query side: the same tokenization expands the user query.

Latin/digit words are lowercased and kept whole. Single-character CJK runs
are emitted as-is so one-char terms still match.
"""

from __future__ import annotations

import re

WORD_RE = re.compile(r"[A-Za-z0-9_]+")
CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")


def cjk_tokens(text: str) -> list[str]:
    """Return latin words + CJK bigrams for ``text`` (order preserved)."""
    if not text:
        return []
    tokens: list[str] = []
    for match in re.finditer(r"[A-Za-z0-9_]+|[\u4e00-\u9fff\u3400-\u4dbf]+", text):
        run = match.group(0)
        if WORD_RE.fullmatch(run):
            tokens.append(run.lower())
            continue
        if len(run) == 1:
            tokens.append(run)
            continue
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def cjk_token_text(text: str, *, max_chars: int = 40_000) -> str:
    """Space-joined token string for FTS storage (bounded for safety)."""
    joined = " ".join(cjk_tokens(text))
    return joined[:max_chars]
