"""Run the immutable Phase 8A retrieval benchmark."""

import hashlib
import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.chat.models import RAGEvaluationRun
from apps.knowledge.models import Document
from apps.rag.config import SIMILARITY_THRESHOLD, TOP_K
from apps.rag.evaluation import DeterministicEvaluationEmbedder, calculate_metrics
from apps.rag.hybrid import HybridRetriever, classify_confidence
from apps.rag.retriever import PgVectorRetriever
from apps.spaces.models import KnowledgeSpace


class Command(BaseCommand):
    help = "Evaluate hybrid retrieval against a versioned, read-only dataset."

    def add_arguments(self, parser):
        default_path = (
            Path(__file__).resolve().parents[3]
            / "rag"
            / "evaluation"
            / "phase8a_v1.json"
        )
        parser.add_argument("--dataset", default=str(default_path))

    def handle(self, *args, **options):
        dataset_path = Path(options["dataset"])
        if not dataset_path.is_file():
            raise CommandError(f"Evaluation dataset not found: {dataset_path}")
        raw = dataset_path.read_bytes()
        dataset = json.loads(raw)
        run = RAGEvaluationRun.objects.create(
            status="running",
            dataset_version=dataset["version"],
            config_fingerprint=hashlib.sha256(
                raw + f"{TOP_K}:{SIMILARITY_THRESHOLD}".encode()
            ).hexdigest(),
        )
        retriever = HybridRetriever(
            vector_retriever=PgVectorRetriever(
                embedder=DeterministicEvaluationEmbedder()
            )
        )
        reports = []
        try:
            for case in dataset["cases"]:
                space = KnowledgeSpace.objects.get(code=case["space_code"])
                expected_ids = list(
                    Document.objects.filter(
                        space=space,
                        title__in=case["expected_document_titles"],
                    ).values_list("id", flat=True)
                )
                started = time.monotonic()
                rows = retriever.search(
                    case["query"],
                    space_id=str(space.id),
                    top_k=TOP_K,
                    similarity_threshold=SIMILARITY_THRESHOLD,
                )
                result_document_ids = [str(row["document_id"]) for row in rows]
                quality = classify_confidence(rows)
                allowed_document_ids = {
                    str(value)
                    for value in Document.objects.filter(space=space).values_list(
                        "id", flat=True
                    )
                }
                reports.append(
                    {
                        "id": case["id"],
                        "answerable": case["answerable"],
                        "expected_document_ids": [str(value) for value in expected_ids],
                        "result_document_ids": result_document_ids,
                        "confidence": quality.label,
                        "refused": quality.label in {"low", "insufficient"},
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "space_leak": any(
                            value not in allowed_document_ids
                            for value in result_document_ids
                        ),
                    }
                )
            metrics = calculate_metrics(reports)
            run.status = "succeeded"
            run.metrics = metrics
            run.report = {"cases": reports}
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "metrics", "report", "completed_at"])
        except Exception as exc:
            run.status = "failed"
            run.report = {"error": type(exc).__name__}
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "report", "completed_at"])
            raise CommandError("RAG evaluation failed; inspect the persisted run.") from exc

        self.stdout.write(json.dumps(metrics, sort_keys=True))
        if (
            metrics["recall_at_5"] < 0.80
            or metrics["mrr"] < 0.65
            or metrics["refusal_accuracy"] < 1.0
            or metrics["cross_space_leaks"] != 0
        ):
            raise CommandError("Phase 8A quality thresholds were not met.")
