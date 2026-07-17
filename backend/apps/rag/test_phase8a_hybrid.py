"""Phase 8A hybrid retrieval and confidence contract tests."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.chat.models import ChatSession, Message
from apps.chat.serializers import MessageSerializer
from apps.knowledge.models import Document, DocumentChunk
from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership
from apps.rag.hybrid import (
    HybridRetriever,
    _normalized_lexical_query,
    _tokens,
    classify_confidence,
    diversify_results,
    reciprocal_rank_fusion,
)


User = get_user_model()


def result(chunk_id, document_id, score=0.8, title="Policy"):
    return {
        "id": chunk_id,
        "content": f"content {chunk_id}",
        "document_id": document_id,
        "document_title": title,
        "score": score,
        "page_number": 1,
        "metadata": {},
    }


class HybridRankingUnitTest(TestCase):
    def test_common_english_stop_words_are_not_evidence(self):
        self.assertEqual(
            _tokens("What will the company share price be tomorrow?"),
            {"company", "share", "price", "tomorrow"},
        )

    def test_postgres_query_uses_the_same_normalized_terms(self):
        self.assertEqual(
            _normalized_lexical_query(
                "What will the company share price be tomorrow?"
            ),
            "company price share tomorrow",
        )

    def test_rrf_keeps_lexical_only_exact_reference_candidate(self):
        vector = [result("v1", "d1", 0.91)]
        lexical = [
            result("l1", "d2", 1.0, "ISA 315"),
            result("v1", "d1", 0.5),
        ]

        fused = reciprocal_rank_fusion(vector, lexical)

        self.assertEqual({row["id"] for row in fused}, {"v1", "l1"})
        exact = next(row for row in fused if row["id"] == "l1")
        self.assertEqual(exact["lexical_score"], 1.0)
        self.assertEqual(exact["vector_score"], 0.0)

    def test_rrf_rewards_candidates_found_by_both_retrievers(self):
        vector = [result("shared", "d1"), result("vector-only", "d2")]
        lexical = [result("shared", "d1"), result("lexical-only", "d3")]

        fused = reciprocal_rank_fusion(vector, lexical)

        self.assertEqual(fused[0]["id"], "shared")
        self.assertGreater(fused[0]["fused_score"], fused[1]["fused_score"])

    def test_source_diversity_limits_each_document_to_two_chunks(self):
        rows = [
            {**result(f"a{i}", "doc-a"), "rerank_score": 1 - i / 10}
            for i in range(4)
        ] + [
            {**result("b1", "doc-b"), "rerank_score": 0.5},
        ]

        selected = diversify_results(rows, top_k=4, max_per_document=2)

        self.assertEqual(
            sum(row["document_id"] == "doc-a" for row in selected),
            2,
        )
        self.assertIn("b1", [row["id"] for row in selected])

    def test_confidence_is_insufficient_without_evidence(self):
        decision = classify_confidence([])

        self.assertEqual(decision.label, "insufficient")
        self.assertEqual(decision.score, 0.0)
        self.assertTrue(decision.needs_human_review)

    def test_confidence_requires_diverse_strong_sources_for_high_label(self):
        diverse = [
            {**result("a", "doc-a"), "rerank_score": 0.9},
            {**result("b", "doc-b"), "rerank_score": 0.82},
        ]
        one_source = [
            {**result("a", "doc-a"), "rerank_score": 0.9},
            {**result("b", "doc-a"), "rerank_score": 0.82},
        ]

        self.assertEqual(classify_confidence(diverse).label, "high")
        self.assertNotEqual(classify_confidence(one_source).label, "high")


class HybridRetrieverIsolationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="phase8a",
            email="phase8a@example.com",
            password="test",
        )
        cls.org = Organization.objects.create(name="Phase 8", slug="phase-8")
        cls.space_a = KnowledgeSpace.objects.create(
            organization=cls.org,
            name="Space A",
            code="phase8-a",
        )
        cls.space_b = KnowledgeSpace.objects.create(
            organization=cls.org,
            name="Space B",
            code="phase8-b",
        )
        cls.active = Document.objects.create(
            space=cls.space_a,
            uploaded_by=cls.user,
            title="ISA 315 Risk Assessment",
            file="documents/isa315.txt",
            file_type="txt",
            file_size=20,
            status="active",
        )
        cls.archived = Document.objects.create(
            space=cls.space_a,
            uploaded_by=cls.user,
            title="Archived ISA 315",
            file="documents/archived315.txt",
            file_type="txt",
            file_size=20,
            status="archived",
        )
        cls.foreign = Document.objects.create(
            space=cls.space_b,
            uploaded_by=cls.user,
            title="Foreign ISA 315",
            file="documents/foreign315.txt",
            file_type="txt",
            file_size=20,
            status="active",
        )
        cls.active_chunk = DocumentChunk.objects.create(
            document=cls.active,
            space=cls.space_a,
            content="ISA 315 requires identifying and assessing risks.",
            chunk_index=0,
        )
        DocumentChunk.objects.create(
            document=cls.archived,
            space=cls.space_a,
            content="ISA 315 archived wording.",
            chunk_index=0,
        )
        DocumentChunk.objects.create(
            document=cls.foreign,
            space=cls.space_b,
            content="ISA 315 confidential foreign guidance.",
            chunk_index=0,
        )

    def test_lexical_candidates_are_active_and_single_space(self):
        vector = Mock()
        vector.search.return_value = []
        retriever = HybridRetriever(vector_retriever=vector)

        rows = retriever.search(
            "ISA 315",
            space_id=str(self.space_a.id),
            top_k=5,
            similarity_threshold=0.3,
        )

        self.assertEqual([row["id"] for row in rows], [str(self.active_chunk.id)])
        self.assertEqual(rows[0]["retrieval_mode"], "hybrid")
        self.assertGreater(rows[0]["lexical_score"], 0)


class PipelineQualityEventTest(TestCase):
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

    def test_pipeline_emits_quality_before_citations(self):
        rows = [
            {**result("a", "doc-a"), "rerank_score": 0.9},
            {**result("b", "doc-b"), "rerank_score": 0.82},
        ]
        pipeline = self.make_pipeline(rows)

        events = list(
            pipeline.retrieve_and_generate(
                "question",
                user_profile=Mock(),
                conversation_history=[],
                space_id="00000000-0000-0000-0000-000000000001",
            )
        )

        quality = next(event for event in events if event["event"] == "quality")
        self.assertEqual(quality["data"]["confidence"], "high")
        self.assertFalse(quality["data"]["needs_human_review"])
        self.assertEqual(quality["data"]["retrieval_mode"], "hybrid")
        self.assertGreaterEqual(quality["data"]["retrieval_latency_ms"], 0)
        self.assertLess(
            next(i for i, event in enumerate(events) if event["event"] == "quality"),
            next(i for i, event in enumerate(events) if event["event"] == "citations"),
        )

    def test_pipeline_emits_insufficient_quality_and_refuses_without_llm(self):
        pipeline = self.make_pipeline([])

        events = list(
            pipeline.retrieve_and_generate(
                "unanswerable",
                user_profile=Mock(),
                conversation_history=[],
                space_id="00000000-0000-0000-0000-000000000001",
            )
        )

        quality = next(event for event in events if event["event"] == "quality")
        self.assertEqual(quality["data"]["confidence"], "insufficient")
        self.assertTrue(quality["data"]["needs_human_review"])
        pipeline.llm.stream_chat.assert_not_called()

    def test_pipeline_refuses_low_confidence_evidence_without_llm(self):
        pipeline = self.make_pipeline(
            [{**result("a", "doc-a"), "rerank_score": 0.42}]
        )

        events = list(
            pipeline.retrieve_and_generate(
                "weak evidence",
                user_profile=Mock(),
                conversation_history=[],
                space_id="00000000-0000-0000-0000-000000000001",
            )
        )

        quality = next(event for event in events if event["event"] == "quality")
        self.assertEqual(quality["data"]["confidence"], "low")
        pipeline.llm.stream_chat.assert_not_called()


class MessageQualityPersistenceTest(TestCase):
    def test_message_serializer_exposes_persisted_quality_fields(self):
        user = User.objects.create_user(
            username="quality-message",
            email="quality-message@example.com",
            password="test",
        )
        org = Organization.objects.create(name="Quality Message", slug="quality-message")
        space = KnowledgeSpace.objects.create(
            organization=org,
            name="Quality Message",
            code="quality-message",
        )
        session = ChatSession.objects.create(user=user, space=space, title="quality")
        message = Message.objects.create(
            session=session,
            space=space,
            role="assistant",
            content="answer",
            confidence_score=0.42,
            confidence_label="low",
            needs_human_review=True,
            retrieval_mode="hybrid",
            retrieval_latency_ms=184,
        )

        data = MessageSerializer(message).data

        self.assertEqual(data["confidence_label"], "low")
        self.assertEqual(data["confidence_score"], 0.42)
        self.assertTrue(data["needs_human_review"])
        self.assertEqual(data["retrieval_mode"], "hybrid")
        self.assertEqual(data["retrieval_latency_ms"], 184)


class ChatQualitySseTest(APITestCase):
    def test_quality_event_is_forwarded_and_persisted(self):
        user = User.objects.create_user(
            username="quality-sse",
            email="quality-sse@example.com",
            password="test",
        )
        org = Organization.objects.create(name="Quality SSE", slug="quality-sse")
        space = KnowledgeSpace.objects.create(
            organization=org,
            name="Quality SSE",
            code="quality-sse",
        )
        SpaceMembership.objects.create(
            user=user,
            space=space,
            role=SpaceMembership.ROLE_MEMBER,
        )
        session = ChatSession.objects.create(user=user, space=space, title="quality")
        self.client.force_authenticate(user)
        fake_pipeline = Mock()
        fake_pipeline.model_name = "test-model"
        fake_pipeline.retrieve_and_generate.return_value = iter(
            [
                {
                    "event": "quality",
                    "data": {
                        "confidence": "low",
                        "score": 0.42,
                        "needs_human_review": True,
                        "retrieval_mode": "hybrid",
                        "retrieval_latency_ms": 184,
                    },
                },
                {"event": "citations", "data": []},
                {"event": "token", "data": {"token": "answer"}},
                {"event": "done", "data": {}},
            ]
        )

        from apps.chat.test_stream_coordination import FakeRedis

        with (
            patch("apps.rag.pipeline.RAGPipeline", return_value=fake_pipeline),
            patch("apps.chat.views.create_redis_client", return_value=FakeRedis()),
        ):
            response = self.client.post(
                f"/api/v1/chat/sessions/{session.id}/send/",
                {"content": "question"},
                format="json",
                HTTP_X_SPACE_ID=str(space.id),
            )
            body = b"".join(response.streaming_content).decode()

        self.assertIn("event: quality", body)
        answer = Message.objects.get(session=session, role="assistant")
        self.assertEqual(answer.confidence_label, "low")
        self.assertEqual(answer.confidence_score, 0.42)
        self.assertTrue(answer.needs_human_review)
        self.assertEqual(answer.retrieval_mode, "hybrid")
        self.assertEqual(answer.retrieval_latency_ms, 184)


class EvaluationMetricsTest(TestCase):
    def test_metrics_include_recall_mrr_refusal_isolation_and_p95(self):
        from apps.rag.evaluation import calculate_metrics

        metrics = calculate_metrics(
            [
                {
                    "answerable": True,
                    "expected_document_ids": ["doc-a"],
                    "result_document_ids": ["doc-b", "doc-a"],
                    "latency_ms": 100,
                    "space_leak": False,
                },
                {
                    "answerable": False,
                    "expected_document_ids": [],
                    "result_document_ids": [],
                    "latency_ms": 300,
                    "space_leak": False,
                },
            ]
        )

        self.assertEqual(metrics["recall_at_5"], 1.0)
        self.assertEqual(metrics["mrr"], 0.5)
        self.assertEqual(metrics["refusal_accuracy"], 1.0)
        self.assertEqual(metrics["cross_space_leaks"], 0)
        self.assertEqual(metrics["latency_p95_ms"], 300)

    def test_low_confidence_candidate_counts_as_a_refusal(self):
        from apps.rag.evaluation import calculate_metrics

        metrics = calculate_metrics(
            [
                {
                    "answerable": False,
                    "expected_document_ids": [],
                    "result_document_ids": ["weak-match"],
                    "refused": True,
                    "latency_ms": 10,
                    "space_leak": False,
                }
            ]
        )

        self.assertEqual(metrics["refusal_accuracy"], 1.0)


class EvaluationRunApiTest(APITestCase):
    def test_evaluation_list_is_admin_only_and_read_only(self):
        from apps.chat.models import RAGEvaluationRun

        admin = User.objects.create_superuser(
            username="evaluation-admin",
            email="evaluation-admin@example.com",
            password="test",
        )
        member = User.objects.create_user(
            username="evaluation-member",
            email="evaluation-member@example.com",
            password="test",
        )
        run = RAGEvaluationRun.objects.create(
            requested_by=admin,
            status="succeeded",
            dataset_version="phase8a-v1",
            metrics={"recall_at_5": 1.0},
        )

        self.client.force_authenticate(member)
        self.assertEqual(
            self.client.get("/api/v1/admin/quality/evaluations/").status_code,
            403,
        )
        self.client.force_authenticate(admin)
        response = self.client.get("/api/v1/admin/quality/evaluations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["id"], str(run.id))
        self.assertEqual(
            self.client.post("/api/v1/admin/quality/evaluations/", {}).status_code,
            405,
        )


class EvaluationCorpusTest(TestCase):
    def test_seed_command_is_idempotent(self):
        call_command("seed_rag_evaluation")
        call_command("seed_rag_evaluation")

        space = KnowledgeSpace.objects.get(code="evaluation-hr")
        self.assertEqual(space.documents.count(), 2)
        self.assertEqual(space.document_chunks.count(), 2)
        self.assertEqual(
            set(space.documents.values_list("title", flat=True)),
            {"Annual Leave Policy", "Security Training Guide"},
        )

    def test_deterministic_embedding_is_stable_and_keyword_sensitive(self):
        from apps.rag.evaluation import deterministic_embedding
        from apps.rag.retriever import cosine_similarity

        leave = deterministic_embedding("annual leave policy days")
        same = deterministic_embedding("annual leave policy days")
        unrelated = deterministic_embedding("security training deadline")

        self.assertEqual(len(leave), 1024)
        self.assertEqual(leave, same)
        self.assertGreater(
            cosine_similarity(leave, deterministic_embedding("annual leave days")),
            cosine_similarity(leave, unrelated),
        )

    def test_retriever_accepts_injected_embedder(self):
        from apps.rag.retriever import PgVectorRetriever

        embedder = Mock()
        retriever = PgVectorRetriever(embedder=embedder)
        self.assertIs(retriever.embedder, embedder)

    def test_evaluation_failure_is_persisted_without_sensitive_details(self):
        from apps.chat.models import RAGEvaluationRun

        dataset = {
            "version": "missing-space-v1",
            "cases": [
                {
                    "id": "missing",
                    "space_code": "does-not-exist",
                    "query": "question",
                    "answerable": False,
                    "expected_document_titles": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.json"
            path.write_text(json.dumps(dataset), encoding="utf-8")
            with self.assertRaises(CommandError):
                call_command("evaluate_rag", dataset=str(path))

        run = RAGEvaluationRun.objects.get(dataset_version="missing-space-v1")
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.report, {"error": "DoesNotExist"})
