# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Vector retrieval with metadata filtering.

Supports both pgvector (PostgreSQL) and JSON embeddings (SQLite dev).

V3.7 P0.2: Added retrieval timing logs for pgvector performance verification.
"""

import time
import math
import logging
from dataclasses import dataclass
from uuid import UUID

from django.db import connection
from django.conf import settings

from apps.knowledge.models import DocumentChunk
from .embedding import EmbeddingService
from .config import TOP_K, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


def _validated_uuid(value, *, field_name: str) -> str:
    """Return one canonical UUID string or fail before database access."""
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must contain valid UUID values") from exc


@dataclass(frozen=True)
class RetrievalFilters:
    """The complete allowlist of caller-controlled retrieval filters."""

    document_ids: tuple[str, ...] = ()
    category_ids: tuple[str, ...] = ()

    def normalized(self) -> "RetrievalFilters":
        return RetrievalFilters(
            document_ids=tuple(
                _validated_uuid(value, field_name="document_ids")
                for value in self.document_ids
            ),
            category_ids=tuple(
                _validated_uuid(value, field_name="category_ids")
                for value in self.category_ids
            ),
        )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


class PgVectorRetriever:
    """Handles vector similarity search with metadata filtering.

    In production (PostgreSQL + pgvector), uses native vector operations.
    In development (SQLite), falls back to Python cosine similarity.
    """

    def search(
        self,
        query: str,
        *,
        space_id: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        filters: RetrievalFilters | None = None,
    ) -> list[dict]:
        """Search for relevant chunks.

        Args:
            query: The user's question.
            top_k: Number of results to return.
            similarity_threshold: Minimum similarity score.
            filters: Django ORM filters to apply before search.
            space_id: V6.0 — restrict retrieval to a single knowledge space.
                Enforces space isolation: answers can only cite documents in the
                active space. Handled explicitly (not via ``filters``) so the
                pgvector SQL qualifies the column as ``dc.space_id`` and avoids
                ambiguity with the joined document table.

        Returns:
            List of dicts with 'content', 'document', 'score', 'page_number', 'metadata', 'id'.
        """
        normalized_space_id = _validated_uuid(space_id, field_name="space_id")
        if filters is not None and not isinstance(filters, RetrievalFilters):
            raise ValueError("filters must be a RetrievalFilters instance")
        normalized_filters = filters.normalized() if filters else RetrievalFilters()

        top_k = TOP_K if top_k is None else top_k
        threshold = (
            SIMILARITY_THRESHOLD
            if similarity_threshold is None
            else similarity_threshold
        )

        # Check if we're using pgvector (PostgreSQL) or JSON (SQLite)
        is_postgres = "postgresql" in settings.DATABASES["default"]["ENGINE"]

        # V3.7 P0.2: Log retrieval timing for performance monitoring
        start_time = time.time()

        if is_postgres:
            results = self._search_pgvector(
                query, top_k, threshold, normalized_filters, normalized_space_id
            )
        else:
            results = self._search_sqlite(
                query, top_k, threshold, normalized_filters, normalized_space_id
            )

        elapsed_ms = int((time.time() - start_time) * 1000)
        search_mode = "pgvector" if is_postgres else "sqlite"
        logger.info(
            "[Retriever] %s search completed in %dms — query='%s...' top_k=%d results=%d",
            search_mode, elapsed_ms, query[:50], top_k, len(results),
        )

        return results

    def _search_sqlite(
        self, query: str, top_k: int, threshold: float,
        filters: RetrievalFilters | None, space_id: str,
    ) -> list[dict]:
        """SQLite fallback: compute cosine similarity in Python."""
        embedder = EmbeddingService()
        query_embedding = embedder.embed(query)

        normalized_filters = (filters or RetrievalFilters()).normalized()
        qs = DocumentChunk.objects.filter(
            embedding__isnull=False,
            space_id=space_id,
            document__status="active",
        )
        if normalized_filters.document_ids:
            qs = qs.filter(document_id__in=normalized_filters.document_ids)
        if normalized_filters.category_ids:
            qs = qs.filter(document__category_id__in=normalized_filters.category_ids)

        # Compute similarity for all chunks
        scored = []
        for chunk in qs.select_related("document"):
            if chunk.embedding is None:
                continue
            sim = cosine_similarity(query_embedding, chunk.embedding)
            if sim >= threshold:
                scored.append((sim, chunk))

        # Sort by similarity (descending) and take top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:top_k]

        return [
            {
                "id": str(chunk.id),
                "content": chunk.content,
                "document_id": str(chunk.document.id),
                "document_title": chunk.document.title,
                "score": round(sim, 4),
                "page_number": chunk.page_number,
                "metadata": chunk.metadata,
            }
            for sim, chunk in results
        ]

    def _search_pgvector(
        self, query: str, top_k: int, threshold: float,
        filters: RetrievalFilters | None, space_id: str,
    ) -> list[dict]:
        """PostgreSQL + pgvector: use native vector similarity.

        V3.7 P0.2: Uses embedding_vector column (VectorField) for pgvector
        cosine similarity search. This column is populated by migration 0004
        from the JSON embedding data, and has an HNSW index for fast retrieval.
        """

        # V3.7 P0.2: Use EmbeddingService singleton — reuses global httpx.Client
        embedder = EmbeddingService()
        query_embedding = embedder.embed(query)

        # Use raw SQL to query embedding_vector column since it's added via migration
        # (not declared as a Django model field to maintain SQLite dev compatibility)
        with connection.cursor() as cursor:
            # Build WHERE clause for filters
            # V4.1 KB-V4.1-004: Whitelist allowed filter keys to prevent SQL column name injection.
            # Only allow known column names that are safe to interpolate into raw SQL.
            normalized_filters = (filters or RetrievalFilters()).normalized()
            filter_parts = ["dc.space_id = %s", "d.status = %s"]
            filter_params: list = [space_id, "active"]
            if normalized_filters.document_ids:
                placeholders = ", ".join(["%s"] * len(normalized_filters.document_ids))
                filter_parts.append(f"dc.document_id IN ({placeholders})")
                filter_params.extend(normalized_filters.document_ids)
            if normalized_filters.category_ids:
                placeholders = ", ".join(["%s"] * len(normalized_filters.category_ids))
                filter_parts.append(f"d.category_id IN ({placeholders})")
                filter_params.extend(normalized_filters.category_ids)
            filter_sql = " AND " + " AND ".join(filter_parts)

            # V6.0 space isolation — qualified column (dc.space_id) avoids ambiguity
            # with the joined knowledge_document.space_id. Always parameterized.

            # V3.7 P0.2: Query embedding_vector (vector column) with HNSW index
            # Cosine distance operator <=> provided by pgvector
            # V4.2 KB-V4.2-BATCH-012: Exclude zero vectors and failed embeddings
            # V4.3 UAT FIX: Double-escape curly braces in f-string SQL — Python interprets
            # single {}/{} as format placeholders. '{"embedding_failed": true}' was being parsed
            # as format specifier `: true` causing ValueError: "Invalid format specifier ' true'"
            # Double braces {{}} produce literal braces in the output SQL string.
            threshold_distance = 1 - threshold
            cursor.execute(
                f"""
                SELECT dc.id, dc.content, dc.page_number, dc.metadata,
                       dc.document_id, d.title AS document_title,
                       (dc.embedding_vector <=> %s) AS distance
                FROM knowledge_documentchunk dc
                JOIN knowledge_document d ON dc.document_id = d.id
                WHERE dc.embedding_vector IS NOT NULL
                AND (dc.embedding_vector <=> %s) <= %s
                AND NOT (dc.metadata @> '{{"embedding_failed": true}}'::jsonb)
                {filter_sql}
                ORDER BY distance ASC
                LIMIT %s
                """,
                [
                    str(query_embedding),  # pgvector expects string format for vector param
                    str(query_embedding),
                    threshold_distance,
                    *filter_params,
                    top_k,
                ],
            )
            rows = cursor.fetchall()

        return [
            {
                "id": str(row[0]),
                "content": row[1],
                "document_id": str(row[4]),
                "document_title": row[5],
                "score": round(1 - float(row[6]), 4),
                "page_number": row[2],
                "metadata": row[3],
            }
            for row in rows
        ]
