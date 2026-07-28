# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""KB/RAG audit spec P0 fixes — contract tests.

Covers:
- §A2: query-signal boosts/penalties must not pollute rerank_score, so
  classify_confidence keeps its calibrated 0.75/0.55 thresholds.
- §A3: reference-library documents are exempt from time decay and the
  stale penalty (standards expire by revision, not by age).
- §A1: reference-library results are quota-bounded in the final top-k.
- §C: refusal fallback copy is domain-neutral (no HR wording).
"""

from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.knowledge.models import Document, ReferenceLibrary
from apps.spaces.models import Organization
from apps.spaces.test_utils import create_test_space
from apps.rag.hybrid import (
    HybridRetriever,
    classify_confidence,
    diversify_results,
)

User = get_user_model()


def row(chunk_id, document_id, *, score=0.8, space_id="primary", status=None):
    data = {
        "id": chunk_id,
        "content": f"content {chunk_id}",
        "document_id": document_id,
        "document_title": "Doc",
        "space_id": space_id,
        "score": score,
        "rerank_score": score,
        "page_number": 1,
        "metadata": {},
    }
    if status is not None:
        data["document_status"] = status
    return data


class SignalScaleConfidenceTest(TestCase):
    """§A2: signal adjustments drive ordering only, never confidence."""

    def test_stale_penalty_keeps_rerank_score_for_confidence(self):
        retriever = HybridRetriever(vector_retriever=Mock())
        rows = [row("a", "doc-a", score=0.8, status="stale")]

        adjusted = retriever._apply_query_signals(
            rows, query="revenue recognition", space_id="00000000-0000-0000-0000-000000000001"
        )

        # Ordering score took the ×0.7 stale penalty…
        self.assertAlmostEqual(adjusted[0]["score"], 0.56, places=4)
        self.assertAlmostEqual(adjusted[0]["signal_adjusted_score"], 0.56, places=4)
        # …but the confidence basis is untouched.
        self.assertAlmostEqual(adjusted[0]["rerank_score"], 0.8, places=4)
        self.assertEqual(classify_confidence(adjusted).label, "medium")


class ReferenceLibraryFreshnessTest(TestCase):
    """§A3: published-library documents never decay and skip the stale hit."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p0audit", email="p0audit@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P0 Audit", slug="p0-audit")
        cls.primary = create_test_space(
            organization=cls.org, name="Primary", code="p0-primary"
        )
        cls.library_space = create_test_space(
            organization=cls.org, name="IFRS Library", code="p0-ifrs-lib"
        )
        ReferenceLibrary.objects.create(
            space=cls.library_space,
            name="IFRS Reference",
            category="ifrs",
            status=ReferenceLibrary.STATUS_PUBLISHED,
        )
        cls.library_doc = Document.objects.create(
            space=cls.library_space,
            uploaded_by=cls.user,
            title="IFRS 15",
            file="documents/ifrs15.txt",
            file_type="txt",
            file_size=10,
            status="stale",
        )
        cls.primary_doc = Document.objects.create(
            space=cls.primary,
            uploaded_by=cls.user,
            title="Own workpaper",
            file="documents/own.txt",
            file_type="txt",
            file_size=10,
            status="active",
        )

    def test_reference_document_is_exempt_from_decay_and_stale_penalty(self):
        retriever = HybridRetriever(vector_retriever=Mock())
        rows = [
            row(
                "lib-1",
                str(self.library_doc.id),
                score=0.8,
                space_id=str(self.library_space.id),
            ),
            row(
                "own-1",
                str(self.primary_doc.id),
                score=0.8,
                space_id=str(self.primary.id),
            ),
        ]

        retriever._annotate_document_signals(rows, space_id=str(self.primary.id))

        lib_row = next(r for r in rows if r["id"] == "lib-1")
        own_row = next(r for r in rows if r["id"] == "own-1")
        self.assertEqual(lib_row["freshness_score"], 1.0)
        self.assertTrue(lib_row["is_reference_library"])
        self.assertFalse(own_row["is_reference_library"])

        adjusted = retriever._apply_query_signals(
            rows, query="ifrs", space_id=str(self.primary.id)
        )
        lib_adjusted = next(r for r in adjusted if r["id"] == "lib-1")
        # Stale library standard keeps its ordering score (no ×0.7 hit).
        self.assertAlmostEqual(lib_adjusted["score"], 0.8, places=4)


class ReferenceQuotaTest(TestCase):
    """§A1: a large shared library cannot crowd out the workspace's own docs."""

    def test_reference_rows_are_capped_at_half_of_top_k(self):
        primary_id = "00000000-0000-0000-0000-0000000000aa"
        # 10 higher-scoring library rows + 6 primary rows, distinct documents.
        results = [
            row(f"ref-{i}", f"ref-doc-{i}", score=0.9, space_id="lib-space")
            for i in range(10)
        ] + [
            row(f"own-{i}", f"own-doc-{i}", score=0.5, space_id=primary_id)
            for i in range(6)
        ]

        selected = diversify_results(
            results, top_k=6, max_per_document=2, primary_space_id=primary_id
        )

        reference_count = sum(1 for r in selected if r["space_id"] == "lib-space")
        own_count = sum(1 for r in selected if r["space_id"] == primary_id)
        self.assertEqual(len(selected), 6)
        self.assertEqual(reference_count, 3)  # int(6 * 0.5)
        self.assertEqual(own_count, 3)

    def test_reference_rows_backfill_when_primary_space_is_short(self):
        primary_id = "00000000-0000-0000-0000-0000000000aa"
        results = [
            row(f"ref-{i}", f"ref-doc-{i}", score=0.9, space_id="lib-space")
            for i in range(10)
        ] + [
            row("own-0", "own-doc-0", score=0.5, space_id=primary_id),
        ]

        selected = diversify_results(
            results, top_k=6, max_per_document=2, primary_space_id=primary_id
        )

        # Quota is 3, primary has only 1 → deferred references backfill to 6.
        self.assertEqual(len(selected), 6)
        self.assertIn("own-0", [r["id"] for r in selected])

    def test_without_primary_space_behaviour_is_unchanged(self):
        results = [row(f"r-{i}", f"d-{i}", score=0.9) for i in range(4)]
        selected = diversify_results(results, top_k=3, max_per_document=2)
        self.assertEqual(len(selected), 3)


class NeutralFallbackCopyTest(TestCase):
    """§C: refusal copy is domain-neutral — no HR wording remains."""

    def make_pipeline(self, rows):
        from apps.rag.pipeline import RAGPipeline

        pipeline = object.__new__(RAGPipeline)
        pipeline.retriever = Mock()
        pipeline.retriever.search.return_value = rows
        pipeline.guardrails = Mock()
        pipeline.guardrails.check_input.return_value = True
        pipeline.prompt_builder = Mock()
        pipeline.prompt_builder.build.return_value = "system"
        pipeline.llm = Mock()
        pipeline.llm.stream_chat_parts = None
        pipeline.llm.stream_chat.return_value = iter(["answer"])
        pipeline.model_name = "test-model"
        return pipeline

    def test_refusal_uses_knowledge_admin_copy(self):
        pipeline = self.make_pipeline([])

        events = list(
            pipeline.retrieve_and_generate(
                "unanswerable",
                user_profile=Mock(),
                conversation_history=[],
                space_id="00000000-0000-0000-0000-000000000001",
                language="zh",
            )
        )

        token = next(e for e in events if e["event"] == "token")["data"]["token"]
        self.assertIn("知识库管理员", token)
        self.assertNotIn("人力资源", token)
        self.assertNotIn("HR", token)
