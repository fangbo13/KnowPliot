# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Precomputed document similarity (KB/RAG audit spec P1 §B2).

The knowledge graph previously computed O(n²) cosine similarity over lead
chunk vectors on every request. This module maintains:

- ``Document.pooled_embedding``: mean of the document's non-zero chunk
  embeddings (a better whole-document representation than the first chunk);
- ``DocumentSimilarity`` rows: pairwise edges >= SIMILAR_EDGE_THRESHOLD,
  refreshed whenever a document is (re)ingested.

All entry points are best-effort: similarity maintenance must never break
document ingestion.
"""

from __future__ import annotations

import logging

from django.db.models import Q

logger = logging.getLogger(__name__)

SIMILAR_EDGE_THRESHOLD = 0.8
# Bound the candidate set per refresh (mirrors the graph's node window).
MAX_CANDIDATES = 300


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def compute_pooled_embedding(document) -> list[float] | None:
    """Mean of the document's non-zero chunk embeddings (None if unusable)."""
    vectors = []
    for chunk in document.chunks.all().only("embedding"):
        emb = chunk.embedding
        if isinstance(emb, list) and emb and any(v != 0.0 for v in emb):
            vectors.append(emb)
    if not vectors:
        return None
    dim = len(vectors[0])
    pooled = [0.0] * dim
    for vec in vectors:
        if len(vec) != dim:
            continue
        for i, value in enumerate(vec):
            pooled[i] += value
    count = float(len(vectors))
    return [round(value / count, 8) for value in pooled]


def refresh_document_similarity(document) -> int:
    """Recompute pooled embedding + similarity edges for one document.

    Returns the number of edges stored. Best-effort — never raises.
    """
    from .models import Document, DocumentSimilarity

    try:
        pooled = compute_pooled_embedding(document)
        Document.objects.filter(pk=document.pk).update(pooled_embedding=pooled)
        DocumentSimilarity.objects.filter(
            Q(source=document) | Q(target=document)
        ).delete()
        if pooled is None:
            return 0

        candidates = (
            Document.objects.filter(
                space_id=document.space_id,
                status__in=["active", "stale"],
                pooled_embedding__isnull=False,
            )
            .exclude(pk=document.pk)
            .order_by("-updated_at")
            .only("id", "pooled_embedding")[:MAX_CANDIDATES]
        )
        rows = []
        for other in candidates:
            other_vec = other.pooled_embedding
            if not isinstance(other_vec, list) or not other_vec:
                continue
            score = _cosine(pooled, other_vec)
            if score < SIMILAR_EDGE_THRESHOLD:
                continue
            # Canonical pair order (by id string) so each pair exists once.
            source_id, target_id = sorted([str(document.pk), str(other.pk)])
            rows.append(
                DocumentSimilarity(
                    space_id=document.space_id,
                    source_id=source_id,
                    target_id=target_id,
                    score=round(score, 4),
                )
            )
        if rows:
            DocumentSimilarity.objects.bulk_create(rows, ignore_conflicts=True)
        return len(rows)
    except Exception as exc:  # pragma: no cover — must never break ingest
        logger.warning(
            "refresh_document_similarity failed for %s: %s", document.pk, exc
        )
        return 0
