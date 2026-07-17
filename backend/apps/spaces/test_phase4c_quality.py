"""Phase 4C ingestion operations and knowledge-quality tests."""

import sys
from types import ModuleType
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.chat.models import ChatSession, Citation, Message, ModelInvocation
from apps.audit.models import AuditLog
from apps.knowledge.models import Document, DocumentChunk, IngestionJob
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
)


User = get_user_model()


class Phase4CBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Quality A", slug="quality-a")
        cls.org_b = Organization.objects.create(name="Quality B", slug="quality-b")
        cls.bl_a = BusinessLine.objects.create(
            organization=cls.org_a, name="Quality A", code="quality-a"
        )
        cls.bl_b = BusinessLine.objects.create(
            organization=cls.org_b, name="Quality B", code="quality-b"
        )
        cls.space_a = KnowledgeSpace.objects.create(
            organization=cls.org_a,
            business_line=cls.bl_a,
            name="Quality Space A",
            code="quality-space-a",
        )
        cls.space_b = KnowledgeSpace.objects.create(
            organization=cls.org_b,
            business_line=cls.bl_b,
            name="Quality Space B",
            code="quality-space-b",
        )
        cls.superuser = User.objects.create_superuser(
            username="quality-super",
            email="quality-super@example.com",
            password="test",
        )
        cls.org_admin = User.objects.create_user(
            username="quality-org-admin",
            email="quality-org-admin@example.com",
            password="test",
        )
        OrganizationMembership.objects.create(
            user=cls.org_admin,
            organization=cls.org_a,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )

    def document(self, space, title, status="active"):
        return Document.objects.create(
            space=space,
            uploaded_by=self.superuser,
            title=title,
            file=f"documents/{title}.txt",
            file_type="txt",
            file_size=10,
            status=status,
        )


class IngestionOperationsApiTest(Phase4CBase):
    def test_job_list_is_scoped_to_administered_spaces(self):
        doc_a = self.document(self.space_a, "job-a", status="failed")
        doc_b = self.document(self.space_b, "job-b", status="failed")
        job_a = IngestionJob.objects.create(
            document=doc_a, space=self.space_a, status="failed", last_error="parse"
        )
        IngestionJob.objects.create(
            document=doc_b, space=self.space_b, status="failed", last_error="secret"
        )
        self.client.force_authenticate(self.org_admin)

        response = self.client.get("/api/v1/admin/ingestion-jobs/?status=failed")

        self.assertEqual(response.status_code, 200)
        rows = response.json().get("results", response.json())
        self.assertEqual([row["id"] for row in rows], [str(job_a.id)])
        self.assertEqual(rows[0]["document_title"], "job-a")

    @patch("apps.rag.services.ingest_document.delay")
    def test_failed_job_can_be_safely_retried_without_mutating_history(self, delay):
        delay.return_value = Mock(id="celery-retry-1")
        document = self.document(self.space_a, "retry-me", status="failed")
        failed = IngestionJob.objects.create(
            document=document,
            space=self.space_a,
            requested_by=self.org_admin,
            status="failed",
            attempt=3,
            last_error="embedding unavailable",
        )
        self.client.force_authenticate(self.org_admin)

        response = self.client.post(
            f"/api/v1/admin/ingestion-jobs/{failed.id}/retry/"
        )

        self.assertEqual(response.status_code, 202)
        failed.refresh_from_db()
        self.assertEqual(failed.status, "failed")
        retry = IngestionJob.objects.get(retry_of=failed)
        self.assertEqual(retry.status, "queued")
        self.assertEqual(retry.celery_task_id, "celery-retry-1")
        self.assertEqual(retry.requested_by, self.org_admin)
        document.refresh_from_db()
        self.assertEqual(document.status, "processing")
        delay.assert_called_once_with(str(document.id), str(retry.id))
        audit = AuditLog.objects.get(action="ingestion_retry")
        self.assertEqual(audit.space_id, self.space_a.id)
        self.assertEqual(audit.organization_id, self.org_a.id)
        self.assertEqual(audit.result, "success")

    @patch("apps.rag.services.ingest_document.delay")
    def test_retry_rejects_nonfailed_cross_scope_and_duplicate_work(self, delay):
        own_document = self.document(self.space_a, "own-processing", status="processing")
        queued = IngestionJob.objects.create(
            document=own_document, space=self.space_a, status="queued"
        )
        foreign_document = self.document(self.space_b, "foreign-failed", status="failed")
        foreign = IngestionJob.objects.create(
            document=foreign_document, space=self.space_b, status="failed"
        )
        self.client.force_authenticate(self.org_admin)

        self.assertEqual(
            self.client.post(
                f"/api/v1/admin/ingestion-jobs/{queued.id}/retry/"
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/admin/ingestion-jobs/{foreign.id}/retry/"
            ).status_code,
            404,
        )
        delay.assert_not_called()

    @patch(
        "apps.rag.services.ingest_document.delay",
        side_effect=RuntimeError("broker credentials must not leak"),
    )
    def test_retry_dispatch_failure_is_durable_audited_and_sanitized(self, _delay):
        document = self.document(self.space_a, "dispatch-failure", status="failed")
        failed = IngestionJob.objects.create(
            document=document,
            space=self.space_a,
            status="failed",
        )
        self.client.force_authenticate(self.org_admin)

        response = self.client.post(
            f"/api/v1/admin/ingestion-jobs/{failed.id}/retry/"
        )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("credentials", str(response.json()))
        retry = IngestionJob.objects.get(retry_of=failed)
        self.assertEqual(retry.status, "failed")
        self.assertEqual(retry.last_error, "dispatch_failed")
        audit = AuditLog.objects.get(action="ingestion_retry", result="failure")
        self.assertEqual(audit.space_id, self.space_a.id)
        self.assertEqual(audit.details["error_code"], "RuntimeError")


class QualityMetricsApiTest(Phase4CBase):
    def test_model_token_error_metrics_are_calculated_from_invocations(self):
        session = ChatSession.objects.create(
            user=self.org_admin, space=self.space_a, title="quality"
        )
        answer = Message.objects.create(
            session=session,
            space=self.space_a,
            role="assistant",
            content="answer",
            token_count=120,
            model_used="qwen-plus",
        )
        ModelInvocation.objects.create(
            session=session,
            message=answer,
            space=self.space_a,
            model="qwen-plus",
            status="success",
            token_count=120,
            latency_ms=300,
        )
        ModelInvocation.objects.create(
            session=session,
            space=self.space_a,
            model="qwen-plus",
            status="failure",
            error_code="stream_error",
            latency_ms=50,
        )
        foreign_session = ChatSession.objects.create(
            user=self.superuser, space=self.space_b, title="foreign"
        )
        ModelInvocation.objects.create(
            session=foreign_session,
            space=self.space_b,
            model="hidden-model",
            status="failure",
            error_code="hidden",
        )
        self.client.force_authenticate(self.org_admin)

        response = self.client.get("/api/v1/admin/metrics/")

        self.assertEqual(response.status_code, 200)
        model = response.json()["model_api"]
        self.assertEqual(model["calls"], 2)
        self.assertEqual(model["failures"], 1)
        self.assertEqual(model["error_rate"], 0.5)
        self.assertEqual(model["total_tokens"], 120)
        self.assertEqual(model["average_tokens"], 120.0)
        self.assertEqual(model["by_model"], [{"model": "qwen-plus", "calls": 2}])

    def test_document_quality_returns_scoped_usage_and_risk_flags(self):
        cited = self.document(self.space_a, "well-used")
        unused = self.document(self.space_a, "unused")
        stale = self.document(self.space_a, "stale", status="stale")
        self.document(self.space_b, "foreign")
        chunk = DocumentChunk.objects.create(
            document=cited,
            space=self.space_a,
            content="source",
            chunk_index=0,
        )
        session = ChatSession.objects.create(
            user=self.org_admin, space=self.space_a, title="citations"
        )
        for index in range(3):
            message = Message.objects.create(
                session=session,
                space=self.space_a,
                role="assistant",
                content=f"answer {index}",
            )
            Citation.objects.create(
                message=message,
                document=cited,
                chunk=chunk,
                space=self.space_a,
                relevance_score=0.8 + index * 0.05,
            )
        stale_chunk = DocumentChunk.objects.create(
            document=stale,
            space=self.space_a,
            content="stale source",
            chunk_index=0,
        )
        stale_message = Message.objects.create(
            session=session,
            space=self.space_a,
            role="assistant",
            content="stale answer",
        )
        Citation.objects.create(
            message=stale_message,
            document=stale,
            chunk=stale_chunk,
            space=self.space_a,
            relevance_score=0.4,
        )
        self.client.force_authenticate(self.org_admin)

        response = self.client.get("/api/v1/admin/quality/documents/")

        self.assertEqual(response.status_code, 200)
        rows = response.json().get("results", response.json())
        by_title = {row["title"]: row for row in rows}
        self.assertEqual(set(by_title), {"well-used", "unused", "stale"})
        self.assertEqual(by_title["well-used"]["citation_count"], 3)
        self.assertTrue(by_title["well-used"]["flags"]["high_usage"])
        self.assertTrue(by_title["unused"]["flags"]["unused"])
        self.assertTrue(by_title["stale"]["flags"]["stale_source"])
        self.assertAlmostEqual(by_title["well-used"]["average_relevance"], 0.85)
        self.assertIsNotNone(by_title["well-used"]["last_cited_at"])

        metrics = self.client.get("/api/v1/admin/metrics/").json()
        self.assertEqual(metrics["knowledge_quality"]["unused_documents"], 1)
        self.assertEqual(metrics["knowledge_quality"]["high_usage_documents"], 1)
        self.assertEqual(metrics["knowledge_quality"]["stale_cited_documents"], 1)


class IngestionTaskLifecycleTest(Phase4CBase):
    def test_task_marks_durable_job_succeeded(self):
        from apps.rag.services import ingest_document

        document = self.document(self.space_a, "task-success", status="processing")
        job = IngestionJob.objects.create(
            document=document,
            space=self.space_a,
            status="queued",
        )

        fake_pipeline = ModuleType("apps.rag.pipeline")
        pipeline_class = Mock()
        pipeline_class.return_value.ingest.return_value = [Mock(), Mock()]
        fake_pipeline.RAGPipeline = pipeline_class
        with patch.dict(sys.modules, {"apps.rag.pipeline": fake_pipeline}):
            result = ingest_document.apply(
                args=[str(document.id), str(job.id)],
                throw=True,
            ).get()

        job.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(result, {"status": "success", "chunks": 2})
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.attempt, 1)
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.completed_at)
        self.assertEqual(document.status, "active")
        self.assertEqual(document.chunk_count, 2)

    def test_task_records_safe_retry_state_without_raw_error(self):
        from apps.rag.services import ingest_document

        document = self.document(self.space_a, "task-retry", status="processing")
        job = IngestionJob.objects.create(
            document=document,
            space=self.space_a,
            status="queued",
        )

        fake_pipeline = ModuleType("apps.rag.pipeline")
        pipeline_class = Mock()
        pipeline_class.return_value.ingest.side_effect = RuntimeError("secret")
        fake_pipeline.RAGPipeline = pipeline_class
        with (
            patch.dict(sys.modules, {"apps.rag.pipeline": fake_pipeline}),
            patch.object(
                ingest_document,
                "retry",
                side_effect=RuntimeError("retry scheduled"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "retry scheduled"):
                ingest_document.run(str(document.id), str(job.id))

        job.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(job.status, "retrying")
        self.assertEqual(job.last_error, "RuntimeError")
        self.assertNotIn("secret", job.last_error)
        self.assertEqual(document.status, "processing")

    def test_task_marks_zero_chunk_result_failed(self):
        from apps.rag.services import ingest_document

        document = self.document(self.space_a, "task-empty", status="processing")
        job = IngestionJob.objects.create(
            document=document,
            space=self.space_a,
            status="queued",
        )
        fake_pipeline = ModuleType("apps.rag.pipeline")
        pipeline_class = Mock()

        def no_chunks(doc):
            doc.status = "failed"
            doc.processing_error = "no embeddings"
            doc.save(update_fields=["status", "processing_error"])
            return []

        pipeline_class.return_value.ingest.side_effect = no_chunks
        fake_pipeline.RAGPipeline = pipeline_class

        with patch.dict(sys.modules, {"apps.rag.pipeline": fake_pipeline}):
            result = ingest_document.apply(
                args=[str(document.id), str(job.id)],
                throw=True,
            ).get()

        job.refresh_from_db()
        self.assertEqual(result["status"], "error")
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.last_error, "no embeddings")
