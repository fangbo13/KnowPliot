"""Deterministic metrics and corpus for versioned RAG evaluation runs."""

import hashlib
import math
import re
from math import ceil

from django.contrib.auth import get_user_model
from django.db import connection, transaction

from apps.knowledge.models import Document, DocumentChunk
from apps.spaces.models import KnowledgeSpace, Organization


EVALUATION_DOCUMENTS = (
    (
        "Annual Leave Policy",
        "Employees receive 20 days of annual leave per calendar year. "
        "Leave requests must be approved by the employee's manager.",
    ),
    (
        "Security Training Guide",
        "Security awareness training must be completed within 30 days "
        "of an employee's start date.",
    ),
)


def deterministic_embedding(text: str, dimensions: int = 1024) -> list[float]:
    """Create a stable normalized token vector for an offline benchmark."""
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", (text or "").lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % dimensions] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


class DeterministicEvaluationEmbedder:
    def embed(self, text: str) -> list[float]:
        return deterministic_embedding(text)


@transaction.atomic
def seed_evaluation_corpus() -> dict:
    """Idempotently provision the isolated Phase 8A benchmark corpus."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        email="rag-evaluation@local.invalid",
        defaults={"username": "rag-evaluation", "is_active": False},
    )
    organization, _ = Organization.objects.get_or_create(
        slug="rag-evaluation",
        defaults={"name": "RAG Evaluation"},
    )
    space, _ = KnowledgeSpace.objects.get_or_create(
        code="evaluation-hr",
        defaults={"name": "Evaluation HR", "organization": organization},
    )
    for title, content in EVALUATION_DOCUMENTS:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document, _ = Document.objects.update_or_create(
            space=space,
            title=title,
            defaults={
                "file": f"evaluation/{content_hash}.txt",
                "file_type": "txt",
                "file_size": len(content.encode("utf-8")),
                "uploaded_by": user,
                "status": "active",
                "content_hash": content_hash,
                "chunk_count": 1,
            },
        )
        embedding = deterministic_embedding(f"{title} {content}")
        chunk, _ = DocumentChunk.objects.update_or_create(
            document=document,
            chunk_index=0,
            defaults={
                "space": space,
                "content": content,
                "page_number": 1,
                "metadata": {"evaluation_dataset": "phase8a-v1"},
                "embedding": embedding,
            },
        )
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE knowledge_documentchunk
                    SET embedding_vector = %s::vector
                    WHERE id = %s
                    """,
                    [str(embedding), str(chunk.id)],
                )
    return {
        "space_id": str(space.id),
        "documents": len(EVALUATION_DOCUMENTS),
        "chunks": len(EVALUATION_DOCUMENTS),
    }


def calculate_metrics(cases: list[dict]) -> dict:
    answerable = [case for case in cases if case["answerable"]]
    reciprocal_ranks = []
    recalled = 0
    for case in answerable:
        expected = set(case["expected_document_ids"])
        results = case["result_document_ids"][:5]
        matching_ranks = [
            index for index, document_id in enumerate(results, start=1)
            if document_id in expected
        ]
        if matching_ranks:
            recalled += 1
            reciprocal_ranks.append(1 / min(matching_ranks))
        else:
            reciprocal_ranks.append(0.0)

    unanswerable = [case for case in cases if not case["answerable"]]
    refusals = sum(
        bool(case.get("refused", not case["result_document_ids"]))
        for case in unanswerable
    )
    latencies = sorted(int(case["latency_ms"]) for case in cases)
    p95_index = max(0, ceil(len(latencies) * 0.95) - 1) if latencies else 0
    return {
        "recall_at_5": round(recalled / len(answerable), 4) if answerable else 1.0,
        "mrr": round(sum(reciprocal_ranks) / len(answerable), 4) if answerable else 1.0,
        "refusal_accuracy": round(refusals / len(unanswerable), 4) if unanswerable else 1.0,
        "cross_space_leaks": sum(bool(case.get("space_leak")) for case in cases),
        "latency_p95_ms": latencies[p95_index] if latencies else 0,
    }
