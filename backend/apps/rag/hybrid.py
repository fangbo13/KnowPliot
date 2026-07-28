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
from apps.knowledge.models import Document, DocumentChunk

from .cjk import cjk_tokens
from .retriever import PgVectorRetriever, RetrievalFilters


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
# Spec §4: FY-shaped term codes (fy26) — used for cross-FY downweighting.
FY_CODE_PATTERN = re.compile(r"^fy\d{2}$")
# Spec §4 L3/L4 tuning constants.
STALE_PENALTY = 0.7
CROSS_FY_PENALTY = 0.6
TERM_MATCH_BOOST = 0.1
ENGLISH_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "was", "what", "when", "where", "which", "who", "why", "will",
    "with",
}
MIN_POSTGRES_FTS_RANK = 1e-6


def _valid_uuid_subset(values) -> set[str]:
    """Keep only well-formed UUID strings (drops synthetic test/legacy ids).

    Passing a non-UUID into ``id__in`` on a UUIDField raises ValidationError
    mid-query; pre-filtering keeps metadata enrichment best-effort instead of
    silently losing everything (or crashing the retrieval path).
    """
    subset = set()
    for value in values:
        try:
            subset.add(str(UUID(str(value))))
        except (TypeError, ValueError):
            continue
    return subset


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


def _cjk_expanded_lexical_query(value: str) -> str:
    """P1 §A6: plain tokens + CJK bigrams so the query matches BOTH legacy
    rows (raw title/content vectors) and new rows (content_tokens bigrams)."""
    plain = _tokens(value)
    bigrams = {
        token for token in cjk_tokens(value)
        if token not in ENGLISH_STOP_WORDS
    }
    return " ".join(sorted(plain | bigrams))


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
    primary_space_id: str | None = None,
    max_reference_ratio: float = 0.5,
) -> list[dict]:
    """Bound repeated chunks from one source document.

    P0 fix (KB/RAG audit spec §A1): when ``primary_space_id`` is given, results
    coming from other spaces (opted-in reference libraries) are capped at
    ``max_reference_ratio`` of ``top_k`` so a large shared library cannot crowd
    out the workspace's own documents. Deferred reference rows backfill only
    when the primary space cannot fill the remaining slots.
    """
    max_reference = (
        top_k
        if primary_space_id is None
        else max(1, int(top_k * max_reference_ratio))
    )
    selected = []
    deferred_references = []
    reference_count = 0
    per_document: defaultdict[str, int] = defaultdict(int)
    for row in results:
        document_id = str(row["document_id"])
        if per_document[document_id] >= max_per_document:
            continue
        is_reference = (
            primary_space_id is not None
            and str(row.get("space_id") or primary_space_id) != primary_space_id
        )
        if is_reference and reference_count >= max_reference:
            deferred_references.append(row)
            continue
        selected.append(row)
        per_document[document_id] += 1
        if is_reference:
            reference_count += 1
        if len(selected) >= top_k:
            break
    # Backfill with over-quota reference rows only when the primary space
    # cannot fill top_k on its own.
    for row in deferred_references:
        if len(selected) >= top_k:
            break
        document_id = str(row["document_id"])
        if per_document[document_id] >= max_per_document:
            continue
        selected.append(row)
        per_document[document_id] += 1
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
        space_ids: list[str] | None = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
        filters: RetrievalFilters | None = None,
    ) -> list[dict]:
        normalized_space_id = str(UUID(str(space_id)))
        # KB optimization spec §3.3: retrieve across the primary space + any
        # opted-in reference libraries. Defaults to single-space isolation.
        if space_ids:
            normalized_space_ids = list(
                dict.fromkeys(str(UUID(str(value))) for value in space_ids)
            )
            if normalized_space_id not in normalized_space_ids:
                normalized_space_ids.insert(0, normalized_space_id)
        else:
            normalized_space_ids = [normalized_space_id]
        normalized_filters = (filters or RetrievalFilters()).normalized()
        candidate_k = max(top_k * 3, top_k)
        # P2 §A4: analyze query signals ONCE — reused for lexical expansion
        # here and for boost/penalty adjustments after fusion.
        signals = None
        try:
            from .query_understanding import analyze_query

            signals = analyze_query(query, space_id=normalized_space_id)
        except Exception:
            signals = None
        lexical_query = query
        if signals and signals.expansion_terms:
            lexical_query = f"{query} {' '.join(signals.expansion_terms)}"
        vector_results = self.vector_retriever.search(
            query,
            space_id=normalized_space_id,
            space_ids=normalized_space_ids,
            top_k=candidate_k,
            similarity_threshold=similarity_threshold,
            filters=normalized_filters,
        )
        lexical_results = self._lexical_search(
            lexical_query,
            space_ids=normalized_space_ids,
            top_k=candidate_k,
            filters=normalized_filters,
        )
        fused = reciprocal_rank_fusion(vector_results, lexical_results)
        self._annotate_document_signals(fused, space_id=normalized_space_id)
        reranked = rerank_results(fused)
        reranked = self._apply_query_signals(
            reranked, query=query, space_id=normalized_space_id, signals=signals
        )
        return diversify_results(
            reranked,
            top_k=top_k,
            max_per_document=2,
            # P0 fix (§A1): reference-library results are quota-bounded.
            primary_space_id=normalized_space_id,
        )

    def _annotate_document_signals(self, rows: list[dict], *, space_id: str) -> None:
        """Spec §4 L3: real freshness (exponential decay) replaces the 1.0 stub.

        P0 fix (KB/RAG audit spec §A3): each document uses its own space's
        half-life, and documents living in a published reference library are
        exempt from time decay — standards (IFRS/CAS) expire by revision, not
        by age. They are flagged so stale penalties skip them too.
        """
        if not rows:
            return
        from apps.knowledge.freshness import compute_freshness, space_half_life_days
        from apps.knowledge.models import ReferenceLibrary

        doc_ids = _valid_uuid_subset(
            str(row["document_id"]) for row in rows
        )
        docs = {
            str(d.id): d
            for d in Document.objects.filter(id__in=doc_ids).select_related("space")
        }
        library_space_ids = {
            str(value)
            for value in ReferenceLibrary.objects.filter(
                space_id__in={str(d.space_id) for d in docs.values()},
                status=ReferenceLibrary.STATUS_PUBLISHED,
            ).values_list("space_id", flat=True)
        }
        half_life_by_space: dict[str, int] = {}
        for row in rows:
            doc = docs.get(str(row["document_id"]))
            if doc is None:
                row.setdefault("freshness_score", 1.0)
                continue
            doc_space_id = str(doc.space_id)
            is_reference = doc_space_id in library_space_ids
            if is_reference:
                row["freshness_score"] = 1.0
            else:
                if doc_space_id not in half_life_by_space:
                    half_life_by_space[doc_space_id] = space_half_life_days(doc.space)
                row["freshness_score"] = compute_freshness(
                    doc, half_life_days=half_life_by_space[doc_space_id]
                )
            row["is_reference_library"] = is_reference
            row["document_status"] = doc.status
            row["document_version"] = doc.version

    def _apply_query_signals(
        self, rows: list[dict], *, query: str, space_id: str, signals=None
    ) -> list[dict]:
        """Spec §4 L4: query understanding — term boost, cross-FY + stale penalties.

        P2 §A4: accepts pre-computed ``signals`` from ``search()`` to avoid a
        second vocabulary scan; falls back to analyzing here when called
        directly (kept for backwards compatibility).
        """
        if not rows:
            return rows
        if signals is None:
            try:
                from .query_understanding import analyze_query

                signals = analyze_query(query, space_id=space_id)
            except Exception:
                signals = None
        query_terms = set(signals.term_codes) if signals else set()
        query_fys = set(signals.fiscal_year_codes) if signals else set()

        adjusted = []
        for row in rows:
            score = float(row["score"])
            doc_terms = set((row.get("metadata") or {}).get("terms") or [])
            doc_fys = {code for code in doc_terms if FY_CODE_PATTERN.match(code)}
            matched = sorted(query_terms & doc_terms)
            if matched:
                score += TERM_MATCH_BOOST
            # Query pins a fiscal year the document does not carry → downweight
            # (history stays retrievable, never hard-excluded).
            if query_fys and doc_fys and not (query_fys & doc_fys):
                score *= CROSS_FY_PENALTY
            # P0 fix (§A3): reference-library standards never take the stale hit.
            if row.get("document_status") == "stale" and not row.get(
                "is_reference_library"
            ):
                score *= STALE_PENALTY
            # P0 fix (§A2): boosts/penalties change the score scale, so they
            # only drive ORDERING (score / signal_adjusted_score). rerank_score
            # is left untouched — classify_confidence reads it against the
            # calibrated 0.75/0.55 thresholds.
            row = {
                **row,
                "score": round(score, 4),
                "signal_adjusted_score": round(score, 4),
            }
            if matched:
                row["matched_terms"] = matched
            adjusted.append(row)
        return sorted(adjusted, key=lambda r: (-r["score"], str(r["id"])))

    def _lexical_search(
        self,
        query: str,
        *,
        space_ids: list[str],
        top_k: int,
        filters: RetrievalFilters,
    ) -> list[dict]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        if connection.vendor == "postgresql":
            return self._postgres_lexical_search(
                query,
                space_ids=space_ids,
                top_k=top_k,
                filters=filters,
            )
        qs = DocumentChunk.objects.filter(
            space_id__in=space_ids,
            document__status__in=["active", "stale"],
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
                "document_status": chunk.document.status,
            }
            for score, chunk in scored[:top_k]
        ]

    def _postgres_lexical_search(
        self,
        query: str,
        *,
        space_ids: list[str],
        top_k: int,
        filters: RetrievalFilters,
    ) -> list[dict]:
        """Use parameterized PostgreSQL FTS while preserving active-space scope.

        P1 §A6: the vector now includes the CJK-bigram ``content_tokens``
        column (weight A, carries tokenized title + content) alongside the
        legacy raw title/content vectors, so pre-backfill rows keep matching
        while new rows gain proper unspaced-Chinese recall.
        """
        vector = (
            SearchVector("content_tokens", weight="A", config="simple")
            + SearchVector("document__title", weight="A", config="simple")
            + SearchVector("content", weight="B", config="simple")
        )
        search_query = SearchQuery(
            _cjk_expanded_lexical_query(query),
            search_type="plain",
            config="simple",
        )
        qs = (
            DocumentChunk.objects.filter(
                space_id__in=space_ids,
                document__status__in=["active", "stale"],
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
                "document_status": chunk.document.status,
            }
            for chunk in qs[:top_k]
        ]
