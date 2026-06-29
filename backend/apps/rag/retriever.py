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
from django.db import connection
from django.conf import settings

from apps.knowledge.models import DocumentChunk
from .embedding import EmbeddingService
from .config import TOP_K, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


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
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        filters: dict | None = None,
        space_id: str | None = None,
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
        top_k = top_k or TOP_K
        threshold = similarity_threshold or SIMILARITY_THRESHOLD

        # Check if we're using pgvector (PostgreSQL) or JSON (SQLite)
        is_postgres = "postgresql" in settings.DATABASES["default"]["ENGINE"]

        # V3.7 P0.2: Log retrieval timing for performance monitoring
        start_time = time.time()

        if is_postgres:
            results = self._search_pgvector(query, top_k, threshold, filters, space_id)
        else:
            results = self._search_sqlite(query, top_k, threshold, filters, space_id)

        elapsed_ms = int((time.time() - start_time) * 1000)
        search_mode = "pgvector" if is_postgres else "sqlite"
        logger.info(
            "[Retriever] %s search completed in %dms — query='%s...' top_k=%d results=%d",
            search_mode, elapsed_ms, query[:50], top_k, len(results),
        )

        return results

    def _search_sqlite(
        self, query: str, top_k: int, threshold: float, filters: dict | None,
        space_id: str | None = None,
    ) -> list[dict]:
        """SQLite fallback: compute cosine similarity in Python."""
        embedder = EmbeddingService()
        query_embedding = embedder.embed(query)

        qs = DocumentChunk.objects.filter(embedding__isnull=False)
        if space_id:
            qs = qs.filter(space_id=space_id)  # V6.0 space isolation
        if filters:
            qs = qs.filter(**filters)

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
        self, query: str, top_k: int, threshold: float, filters: dict | None,
        space_id: str | None = None,
    ) -> list[dict]:
        """PostgreSQL + pgvector: use native vector similarity.

        V3.7 P0.2: Uses embedding_vector column (VectorField) for pgvector
        cosine similarity search. This column is populated by migration 0004
        from the JSON embedding data, and has an HNSW index for fast retrieval.
        """
        from pgvector.django import CosineDistance

        # V3.7 P0.2: Use EmbeddingService singleton — reuses global httpx.Client
        embedder = EmbeddingService()
        query_embedding = embedder.embed(query)

        # Use raw SQL to query embedding_vector column since it's added via migration
        # (not declared as a Django model field to maintain SQLite dev compatibility)
        with connection.cursor() as cursor:
            # Build WHERE clause for filters
            # V4.1 KB-V4.1-004: Whitelist allowed filter keys to prevent SQL column name injection.
            # Only allow known column names that are safe to interpolate into raw SQL.
            ALLOWED_FILTER_KEYS = {"document_id", "category_id", "document__status"}
            filter_sql = ""
            filter_params: list = []
            if filters:
                filter_parts = []
                for key, value in filters.items():
                    if key not in ALLOWED_FILTER_KEYS:
                        raise ValueError(f"Invalid filter key: '{key}'. Allowed keys: {sorted(ALLOWED_FILTER_KEYS)}")
                    filter_parts.append(f"{key} = %s")
                    filter_params.append(value)
                filter_sql = " AND " + " AND ".join(filter_parts)

            # V6.0 space isolation — qualified column (dc.space_id) avoids ambiguity
            # with the joined knowledge_document.space_id. Always parameterized.
            if space_id:
                filter_sql += " AND dc.space_id = %s"
                filter_params.append(str(space_id))

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
