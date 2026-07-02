"""Phase 4B operations, metrics, and document-lifecycle tests."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.chat.models import ChatSession, Citation, Message
from apps.knowledge.models import Document, DocumentChunk
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)


User = get_user_model()


class Phase4BBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Ops A", slug="ops-a")
        cls.org_b = Organization.objects.create(name="Ops B", slug="ops-b")
        cls.bl_a = BusinessLine.objects.create(
            organization=cls.org_a, name="Audit A", code="ops-a"
        )
        cls.bl_b = BusinessLine.objects.create(
            organization=cls.org_b, name="Audit B", code="ops-b"
        )
        cls.space_a = KnowledgeSpace.objects.create(
            organization=cls.org_a,
            business_line=cls.bl_a,
            name="Ops Space A",
            code="ops-space-a",
        )
        cls.space_b = KnowledgeSpace.objects.create(
            organization=cls.org_b,
            business_line=cls.bl_b,
            name="Ops Space B",
            code="ops-space-b",
        )
        cls.superuser = User.objects.create_superuser(
            username="ops-super",
            email="ops-super@example.com",
            password="test",
        )
        cls.org_admin = User.objects.create_user(
            username="ops-org-admin",
            email="ops-org-admin@example.com",
            password="test",
        )
        cls.member = User.objects.create_user(
            username="ops-member",
            email="ops-member@example.com",
            password="test",
        )
        OrganizationMembership.objects.create(
            user=cls.org_admin,
            organization=cls.org_a,
            role=OrganizationMembership.ROLE_ORG_ADMIN,
        )
        SpaceMembership.objects.create(
            user=cls.member,
            space=cls.space_a,
            role=SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
        )

    def make_document(self, space, title, status="active", effective_to=None):
        return Document.objects.create(
            space=space,
            uploaded_by=self.superuser,
            title=title,
            file=f"documents/{title}.txt",
            file_type="txt",
            file_size=10,
            status=status,
            effective_to=effective_to,
        )


class AdminOperationsApiTest(Phase4BBase):
    def test_health_endpoint_reports_real_service_payload_and_audits_view(self):
        payload = {
            "overall": "degraded",
            "services": {
                "backend": {"status": "up"},
                "database": {"status": "up"},
                "redis": {"status": "down"},
                "celery": {"status": "down"},
                "vector_db": {"status": "not_configured"},
                "llm": {"status": "configured"},
            },
        }
        self.client.force_authenticate(self.superuser)
        with patch(
            "apps.spaces.admin_views.collect_system_health",
            return_value=payload,
            create=True,
        ):
            response = self.client.get("/api/v1/admin/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.superuser,
                action="system_health_view",
                result="success",
            ).exists()
        )

    def test_regular_member_cannot_view_admin_operations(self):
        self.client.force_authenticate(self.member)

        self.assertEqual(self.client.get("/api/v1/admin/health/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/admin/metrics/").status_code, 403)

    def test_health_response_survives_audit_write_failure(self):
        payload = {
            "overall": "down",
            "services": {
                "backend": {"status": "up"},
                "database": {"status": "down"},
                "redis": {"status": "down"},
                "celery": {"status": "down"},
                "vector_db": {"status": "not_configured"},
                "llm": {"status": "not_configured"},
            },
        }
        self.client.force_authenticate(self.superuser)
        with (
            patch(
                "apps.spaces.admin_views.collect_system_health",
                return_value=payload,
            ),
            patch(
                "apps.audit.views.create_audit_log",
                side_effect=RuntimeError("audit database unavailable"),
            ),
        ):
            response = self.client.get("/api/v1/admin/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_metrics_are_scoped_and_calculated_from_persisted_records(self):
        doc_a = self.make_document(self.space_a, "metrics-a")
        self.make_document(self.space_b, "metrics-b")
        session = ChatSession.objects.create(
            user=self.member, space=self.space_a, title="metrics"
        )
        Message.objects.create(
            session=session,
            space=self.space_a,
            role="user",
            content="question",
        )
        answered = Message.objects.create(
            session=session,
            space=self.space_a,
            role="assistant",
            content="answer",
            response_time_ms=200,
            retrieval_count=1,
        )
        Message.objects.create(
            session=session,
            space=self.space_a,
            role="assistant",
            content="no evidence",
            response_time_ms=400,
            retrieval_count=0,
        )
        chunk = DocumentChunk.objects.create(
            document=doc_a,
            space=self.space_a,
            content="source",
            chunk_index=0,
        )
        Citation.objects.create(
            message=answered,
            document=doc_a,
            chunk=chunk,
            relevance_score=0.9,
            space=self.space_a,
        )
        self.client.force_authenticate(self.org_admin)

        response = self.client.get("/api/v1/admin/metrics/")

        self.assertEqual(response.status_code, 200)
        metrics = response.json()
        self.assertEqual(metrics["documents"]["total"], 1)
        self.assertEqual(metrics["usage"]["sessions"], 1)
        self.assertEqual(metrics["usage"]["questions"], 1)
        self.assertEqual(metrics["usage"]["citations"], 1)
        self.assertEqual(metrics["quality"]["average_response_time_ms"], 300.0)
        self.assertEqual(metrics["quality"]["no_evidence_rate"], 0.5)
        self.assertEqual(metrics["quality"]["citation_coverage_rate"], 0.5)


class DocumentLifecycleTest(Phase4BBase):
    def make_cited_document(self):
        document = self.make_document(self.space_a, "cited-lifecycle")
        chunk = DocumentChunk.objects.create(
            document=document,
            space=self.space_a,
            content="source",
            chunk_index=0,
        )
        session = ChatSession.objects.create(
            user=self.member, space=self.space_a, title="lifecycle"
        )
        message = Message.objects.create(
            session=session,
            space=self.space_a,
            role="assistant",
            content="answer",
        )
        citation = Citation.objects.create(
            message=message,
            document=document,
            chunk=chunk,
            relevance_score=0.8,
            space=self.space_a,
        )
        return document, chunk, citation

    def test_default_delete_archives_and_preserves_provenance(self):
        document, chunk, citation = self.make_cited_document()
        self.client.force_authenticate(self.member)

        response = self.client.delete(
            f"/api/v1/documents/{document.id}/",
            HTTP_X_SPACE_ID=str(self.space_a.id),
        )

        self.assertEqual(response.status_code, 204)
        document.refresh_from_db()
        self.assertEqual(document.status, "archived")
        self.assertTrue(DocumentChunk.objects.filter(id=chunk.id).exists())
        self.assertTrue(Citation.objects.filter(id=citation.id).exists())

    def test_hard_delete_is_superuser_only_and_rejects_cited_documents(self):
        document, _, _ = self.make_cited_document()
        self.client.force_authenticate(self.member)
        member_response = self.client.delete(
            f"/api/v1/documents/{document.id}/?hard=true",
            HTTP_X_SPACE_ID=str(self.space_a.id),
        )
        self.assertEqual(member_response.status_code, 403)

        self.client.force_authenticate(self.superuser)
        super_response = self.client.delete(
            f"/api/v1/documents/{document.id}/?hard=true",
            HTTP_X_SPACE_ID=str(self.space_a.id),
        )
        self.assertEqual(super_response.status_code, 409)
        self.assertTrue(Document.objects.filter(id=document.id).exists())

    def test_superuser_can_hard_delete_uncited_document(self):
        document = self.make_document(self.space_a, "uncited-lifecycle")
        self.client.force_authenticate(self.superuser)

        response = self.client.delete(
            f"/api/v1/documents/{document.id}/?hard=true",
            HTTP_X_SPACE_ID=str(self.space_a.id),
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Document.objects.filter(id=document.id).exists())

    def test_archived_documents_are_hidden_unless_explicitly_filtered(self):
        archived = self.make_document(self.space_a, "archived-list", status="archived")
        active = self.make_document(self.space_a, "active-list")
        self.client.force_authenticate(self.superuser)

        default_response = self.client.get(
            "/api/v1/documents/",
            HTTP_X_SPACE_ID=str(self.space_a.id),
        )
        archived_response = self.client.get(
            "/api/v1/documents/?status=archived",
            HTTP_X_SPACE_ID=str(self.space_a.id),
        )

        default_ids = {
            row["id"]
            for row in default_response.json().get("results", default_response.json())
        }
        archived_ids = {
            row["id"]
            for row in archived_response.json().get("results", archived_response.json())
        }
        self.assertIn(str(active.id), default_ids)
        self.assertNotIn(str(archived.id), default_ids)
        self.assertEqual(archived_ids, {str(archived.id)})

    def test_archived_document_cannot_be_reindexed(self):
        archived = self.make_document(self.space_a, "archived-reindex", status="archived")
        self.client.force_authenticate(self.superuser)

        response = self.client.post(
            f"/api/v1/documents/{archived.id}/reindex/",
            HTTP_X_SPACE_ID=str(self.space_a.id),
        )

        self.assertEqual(response.status_code, 409)
        archived.refresh_from_db()
        self.assertEqual(archived.status, "archived")

    def test_stale_command_is_idempotent_and_only_updates_expired_active_documents(self):
        stale = self.make_document(
            self.space_a,
            "becomes-stale",
            effective_to=timezone.localdate() - timedelta(days=1),
        )
        future = self.make_document(
            self.space_a,
            "remains-active",
            effective_to=timezone.localdate() + timedelta(days=1),
        )

        first_output = StringIO()
        call_command("mark_stale_documents", stdout=first_output)
        second_output = StringIO()
        call_command("mark_stale_documents", stdout=second_output)

        stale.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(stale.status, "stale")
        self.assertEqual(future.status, "active")
        self.assertIn("1", first_output.getvalue())
        self.assertIn("0", second_output.getvalue())
