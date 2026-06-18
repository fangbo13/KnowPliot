"""Vector retrieval with metadata filtering.

Supports both pgvector (PostgreSQL) and JSON embeddings (SQLite dev).
"""

import math
from django.db import connection
from django.conf import settings

from apps.knowledge.models import DocumentChunk
from .embedding import EmbeddingService
from .config import TOP_K, SIMILARITY_THRESHOLD


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
    ) -> list[dict]:
        """Search for relevant chunks.

        Args:
            query: The user's question.
            top_k: Number of results to return.
            similarity_threshold: Minimum similarity score.
            filters: Django ORM filters to apply before search.

        Returns:
            List of dicts with 'content', 'document', 'score', 'page_number', 'metadata', 'id'.
        """
        top_k = top_k or TOP_K
        threshold = similarity_threshold or SIMILARITY_THRESHOLD

        # Check if we're using pgvector (PostgreSQL) or JSON (SQLite)
        is_postgres = "postgresql" in settings.DATABASES["default"]["ENGINE"]

        if is_postgres:
            return self._search_pgvector(query, top_k, threshold, filters)
        else:
            return self._search_sqlite(query, top_k, threshold, filters)

    def _search_sqlite(
        self, query: str, top_k: int, threshold: float, filters: dict | None
    ) -> list[dict]:
        """SQLite fallback: compute cosine similarity in Python."""
        embedder = EmbeddingService()
        query_embedding = embedder.embed(query)

        qs = DocumentChunk.objects.filter(embedding__isnull=False)
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
        self, query: str, top_k: int, threshold: float, filters: dict | None
    ) -> list[dict]:
        """PostgreSQL + pgvector: use native vector similarity."""
        from pgvector.django import CosineDistance

        embedder = EmbeddingService()
        query_embedding = embedder.embed(query)

        qs = DocumentChunk.objects.filter(embedding__isnull=False)
        if filters:
            qs = qs.filter(**filters)

        results = (
            qs.annotate(distance=CosineDistance("embedding"))
            .filter(distance__lte=1 - threshold)
            .order_by("distance")[:top_k]
        )

        return [
            {
                "id": str(r.id),
                "content": r.content,
                "document_id": str(r.document.id),
                "document_title": r.document.title,
                "score": round(1 - float(r.distance), 4),
                "page_number": r.page_number,
                "metadata": r.metadata,
            }
            for r in results
        ]
