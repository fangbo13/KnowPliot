"""Explainable single-space hybrid retrieval for Phase 8A."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection
from django.db.models import Q
from apps.knowledge.models import DocumentChunk

from .retriever import PgVectorRetriever, RetrievalFilters


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
ENGLISH_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "what", "when", "where", "which", "who", "why", "will",
    "with",
}
MIN_POSTGRES_FTS_RANK = 1e-6


def _effective_date_filter():
    """Part 1 (§1.5): Only retrieve chunks from currently effective documents.

    A document is effective when:
    - status != 'superseded' (handled separately as 'active')
    - effective_from is NULL or <= today
    - effective_to is NULL or >= today

    This prevents scheduled (future) versions and expired old versions from
    polluting retrieval results — the core "no interference" invariant.
    """
    today = date.today()
    return (
        Q(document__effective_from__isnull=True) | Q(document__effective_from__lte=today),
        Q(document__effective_to__isnull=True) | Q(document__effective_to__gte=today),
    )


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(value or "")
        if token.lower() not in ENGLISH_STOP_WORDS
    }


def _normalized_lexical_query(value: str) -> str:
    return " ".join(sorted(_tokens(value)))


def reciprocal_rank_fusion(
    vector_results: list[dict],
    lexical_results: list[dict],
    *,
    rrf_k: int = 60,
) -> list[dict]:
    """Fuse independent ranked lists without comparing incompatible scores."""
    combined: dict[str, dict] = {}
    contributions: defaultdict[str, float] = defaultdict(float)

    for mode, rows in (("vector", vector_results), ("lexical", lexical_results)):
        for rank, row in enumerate(rows, start=1):
            chunk_id = str(row["id"])
            combined.setdefault(chunk_id, dict(row))
            contributions[chunk_id] += 1.0 / (rrf_k + rank)
            combined[chunk_id][f"{mode}_score"] = float(row.get("score", 0.0))

    for chunk_id, row in combined.items():
        row.setdefault("vector_score", 0.0)
        row.setdefault("lexical_score", 0.0)
        row["fused_score"] = round(contributions[chunk_id], 8)

    return sorted(
        combined.values(),
        key=lambda row: (-row["fused_score"], str(row["id"])),
    )


def rerank_results(results: list[dict]) -> list[dict]:
    """Apply an explainable score using fused rank, evidence, and freshness."""
    if not results:
        return []
    max_fused = max(row["fused_score"] for row in results) or 1.0
    reranked = []
    for row in results:
        fused = row["fused_score"] / max_fused
        evidence = max(row.get("vector_score", 0.0), row.get("lexical_score", 0.0))
        freshness = float(row.get("freshness_score", 1.0))
        score = round(0.55 * fused + 0.35 * evidence + 0.10 * freshness, 4)
        reranked.append(
            {
                **row,
                "rerank_score": score,
                "score": score,
                "retrieval_mode": "hybrid",
            }
        )
    return sorted(
        reranked,
        key=lambda row: (-row["rerank_score"], str(row["id"])),
    )


def diversify_results(
    results: list[dict],
    *,
    top_k: int,
    max_per_document: int = 2,
) -> list[dict]:
    """Bound repeated chunks from one source document."""
    selected = []
    per_document: defaultdict[str, int] = defaultdict(int)
    for row in results:
        document_id = str(row["document_id"])
        if per_document[document_id] >= max_per_document:
            continue
        selected.append(row)
        per_document[document_id] += 1
        if len(selected) >= top_k:
            break
    return selected


@dataclass(frozen=True)
class QualityDecision:
    label: str
    score: float
    needs_human_review: bool


def classify_confidence(results: list[dict]) -> QualityDecision:
    """Classify evidence without using an opaque model judge."""
    if not results:
        return QualityDecision("insufficient", 0.0, True)

    top_scores = [float(row.get("rerank_score", row.get("score", 0.0))) for row in results[:3]]
    score = round(sum(top_scores) / len(top_scores), 4)
    source_count = len({str(row["document_id"]) for row in results})
    if score >= 0.75 and source_count >= 2:
        return QualityDecision("high", score, False)
    if score >= 0.55:
        return QualityDecision("medium", score, False)
    return QualityDecision("low", score, True)


class HybridRetriever:
    """Combine semantic and lexical candidates under one mandatory space."""

    def __init__(self, vector_retriever=None):
        self.vector_retriever = vector_retriever or PgVectorRetriever()

    def search(
        self,
        query: str,
        *,
        space_id: str,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
        filters: RetrievalFilters | None = None,
    ) -> list[dict]:
        normalized_space_id = str(UUID(str(space_id)))
        normalized_filters = (filters or RetrievalFilters()).normalized()
        candidate_k = max(top_k * 3, top_k)
        vector_results = self.vector_retriever.search(
            query,
            space_id=normalized_space_id,
            top_k=candidate_k,
            similarity_threshold=similarity_threshold,
            filters=normalized_filters,
        )
        lexical_results = self._lexical_search(
            query,
            space_id=normalized_space_id,
            top_k=candidate_k,
            filters=normalized_filters,
        )
        fused = reciprocal_rank_fusion(vector_results, lexical_results)
        return diversify_results(
            rerank_results(fused),
            top_k=top_k,
            max_per_document=2,
        )

    def _lexical_search(
        self,
        query: str,
        *,
        space_id: str,
        top_k: int,
        filters: RetrievalFilters,
    ) -> list[dict]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        if connection.vendor == "postgresql":
            return self._postgres_lexical_search(
                query,
                space_id=space_id,
                top_k=top_k,
                filters=filters,
            )
        qs = DocumentChunk.objects.filter(
            space_id=space_id,
            document__status="active",
        ).filter(*_effective_date_filter()).select_related("document")
        if filters.document_ids:
            qs = qs.filter(document_id__in=filters.document_ids)
        if filters.category_ids:
            qs = qs.filter(document__category_id__in=filters.category_ids)

        scored = []
        normalized_query = " ".join(query.lower().split())
        for chunk in qs:
            haystack = f"{chunk.document.title} {chunk.content}"
            haystack_tokens = _tokens(haystack)
            overlap = len(query_tokens & haystack_tokens) / len(query_tokens)
            phrase_bonus = 0.15 if normalized_query in " ".join(haystack.lower().split()) else 0.0
            lexical_score = min(1.0, overlap + phrase_bonus)
            if lexical_score <= 0:
                continue
            scored.append((lexical_score, chunk))
        scored.sort(key=lambda item: (-item[0], str(item[1].id)))
        return [
            {
                "id": str(chunk.id),
                "content": chunk.content,
                "document_id": str(chunk.document_id),
                "document_title": chunk.document.title,
                "space_id": str(chunk.space_id),
                "score": round(score, 4),
                "page_number": chunk.page_number,
                "metadata": chunk.metadata,
                "freshness_score": 1.0,
            }
            for score, chunk in scored[:top_k]
        ]

    def _postgres_lexical_search(
        self,
        query: str,
        *,
        space_id: str,
        top_k: int,
        filters: RetrievalFilters,
    ) -> list[dict]:
        """Use parameterized PostgreSQL FTS while preserving active-space scope."""
        vector = (
            SearchVector("document__title", weight="A", config="simple")
            + SearchVector("content", weight="B", config="simple")
        )
        search_query = SearchQuery(
            _normalized_lexical_query(query),
            search_type="plain",
            config="simple",
        )
        qs = (
            DocumentChunk.objects.filter(
                space_id=space_id,
                document__status="active",
            )
            .filter(*_effective_date_filter())
            .select_related("document")
            .annotate(lexical_rank=SearchRank(vector, search_query))
            # PostgreSQL ts_rank returns a tiny 1e-20 sentinel for no match,
            # so a plain > 0 filter incorrectly admits every row.
            .filter(lexical_rank__gt=MIN_POSTGRES_FTS_RANK)
            .order_by("-lexical_rank", "id")
        )
        if filters.document_ids:
            qs = qs.filter(document_id__in=filters.document_ids)
        if filters.category_ids:
            qs = qs.filter(document__category_id__in=filters.category_ids)
        return [
            {
                "id": str(chunk.id),
                "content": chunk.content,
                "document_id": str(chunk.document_id),
                "document_title": chunk.document.title,
                "space_id": str(chunk.space_id),
                "score": min(1.0, round(float(chunk.lexical_rank), 4)),
                "page_number": chunk.page_number,
                "metadata": chunk.metadata,
                "freshness_score": 1.0,
            }
            for chunk in qs[:top_k]
        ]
