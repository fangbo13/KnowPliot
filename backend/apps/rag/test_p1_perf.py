# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""KB/RAG audit spec P1 performance fixes — contract tests.

Covers:
- §A5 embed_batch sends true batched requests and degrades gracefully;
- §A6 CJK bigram tokenization on both the ingest and query side;
- §B2 precomputed document similarity (pooled embedding + edge rows);
- §B4 batched stale scan keeps updated_at untouched (freshness clock).
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.knowledge.models import Document, DocumentChunk, DocumentSimilarity
from apps.knowledge.similarity import refresh_document_similarity
from apps.knowledge.tasks import scan_stale_documents
from apps.spaces.models import Organization
from apps.spaces.test_utils import create_test_space
from apps.rag.cjk import cjk_token_text, cjk_tokens
from apps.rag.embedding import EMBED_BATCH_SIZE, EmbeddingService, _embedding_cache
from apps.rag.hybrid import _cjk_expanded_lexical_query

User = get_user_model()


class CjkTokenizationTest(TestCase):
    """§A6: bigrams for CJK runs, whole lowercased words for latin."""

    def test_mixed_text_produces_bigrams_and_words(self):
        self.assertEqual(
            cjk_tokens("IFRS15收入确认"),
            ["ifrs15", "收入", "入确", "确认"],
        )

    def test_single_cjk_char_is_kept(self):
        self.assertEqual(cjk_tokens("税 policy"), ["税", "policy"])

    def test_token_text_is_space_joined(self):
        self.assertEqual(cjk_token_text("坏账准备"), "坏账 账准 准备")

    def test_query_expansion_contains_bigrams(self):
        expanded = _cjk_expanded_lexical_query("坏账准备计提")
        for bigram in ["坏账", "账准", "准备", "备计", "计提"]:
            self.assertIn(bigram, expanded.split())


class EmbedBatchTest(TestCase):
    """§A5: one API request per EMBED_BATCH_SIZE inputs, ordered results."""

    def setUp(self):
        _embedding_cache.clear()

    def tearDown(self):
        _embedding_cache.clear()

    def test_batched_requests_and_result_order(self):
        service = EmbeddingService()
        texts = [f"text-{i}" for i in range(EMBED_BATCH_SIZE + 2)]
        calls = []

        def fake_request(input_texts, retries=3):
            calls.append(list(input_texts))
            return {
                "data": [
                    {"index": i, "embedding": [float(hash(t) % 97)] * 4}
                    for i, t in enumerate(input_texts)
                ]
            }

        with patch.object(service, "_make_request", side_effect=fake_request):
            embeddings = service.embed_batch(texts)

        # 12 texts → 2 requests (10 + 2), not 12.
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls[0]), EMBED_BATCH_SIZE)
        self.assertEqual(len(calls[1]), 2)
        self.assertEqual(len(embeddings), len(texts))
        for text, embedding in zip(texts, embeddings):
            self.assertEqual(embedding[0], float(hash(text) % 97))

    def test_failed_batch_degrades_to_singles_then_zero_vectors(self):
        service = EmbeddingService()

        def always_fail(input_texts, retries=3):
            raise RuntimeError("api down")

        with patch.object(service, "_make_request", side_effect=always_fail):
            embeddings = service.embed_batch(["a", "b"])

        self.assertEqual(len(embeddings), 2)
        for embedding in embeddings:
            self.assertTrue(all(v == 0.0 for v in embedding))


class DocumentSimilarityTest(TestCase):
    """§B2: pooled embedding + precomputed edges refreshed per document."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p1sim", email="p1sim@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P1 Sim", slug="p1-sim")
        cls.space = create_test_space(
            organization=cls.org, name="Sim Space", code="p1-sim"
        )

    def _doc_with_chunk(self, title, vector):
        doc = Document.objects.create(
            space=self.space,
            uploaded_by=self.user,
            title=title,
            file=f"documents/{title}.txt",
            file_type="txt",
            file_size=10,
            status="active",
        )
        DocumentChunk.objects.create(
            document=doc,
            space=self.space,
            content=f"content of {title}",
            chunk_index=0,
            embedding=vector,
        )
        return doc

    def test_refresh_creates_edge_for_similar_documents(self):
        doc_a = self._doc_with_chunk("doc-a", [1.0, 0.0, 0.0, 0.0])
        doc_b = self._doc_with_chunk("doc-b", [0.99, 0.05, 0.0, 0.0])
        refresh_document_similarity(doc_a)
        edges = refresh_document_similarity(doc_b)

        self.assertEqual(edges, 1)
        doc_a.refresh_from_db()
        self.assertIsNotNone(doc_a.pooled_embedding)
        edge = DocumentSimilarity.objects.get(space=self.space)
        self.assertGreaterEqual(edge.score, 0.8)
        self.assertEqual(
            sorted([str(edge.source_id), str(edge.target_id)]),
            sorted([str(doc_a.id), str(doc_b.id)]),
        )

    def test_dissimilar_documents_produce_no_edge(self):
        doc_a = self._doc_with_chunk("far-a", [1.0, 0.0, 0.0, 0.0])
        doc_b = self._doc_with_chunk("far-b", [0.0, 1.0, 0.0, 0.0])
        refresh_document_similarity(doc_a)
        edges = refresh_document_similarity(doc_b)

        self.assertEqual(edges, 0)
        self.assertFalse(DocumentSimilarity.objects.exists())


class StaleScanBatchTest(TestCase):
    """§B4: bulk stale marking must not touch updated_at (freshness clock)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p1stale", email="p1stale@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P1 Stale", slug="p1-stale")
        cls.space = create_test_space(
            organization=cls.org, name="Stale Space", code="p1-stale"
        )

    def test_overdue_document_marked_without_resetting_clock(self):
        doc = Document.objects.create(
            space=self.space,
            uploaded_by=self.user,
            title="old doc",
            file="documents/old.txt",
            file_type="txt",
            file_size=10,
            status="active",
        )
        old = timezone.now() - timedelta(days=600)
        Document.objects.filter(pk=doc.pk).update(updated_at=old)

        result = scan_stale_documents()

        doc.refresh_from_db()
        self.assertEqual(doc.status, "stale")
        self.assertEqual(result["marked_stale"], 1)
        # auto_now clock preserved — stale doc must NOT look freshly edited.
        self.assertLess(
            abs((doc.updated_at - old).total_seconds()), 5
        )

    def test_recently_reviewed_document_is_skipped(self):
        doc = Document.objects.create(
            space=self.space,
            uploaded_by=self.user,
            title="reviewed doc",
            file="documents/reviewed.txt",
            file_type="txt",
            file_size=10,
            status="active",
            last_reviewed_at=timezone.now(),
        )
        Document.objects.filter(pk=doc.pk).update(
            updated_at=timezone.now() - timedelta(days=600)
        )

        scan_stale_documents()

        doc.refresh_from_db()
        self.assertEqual(doc.status, "active")
