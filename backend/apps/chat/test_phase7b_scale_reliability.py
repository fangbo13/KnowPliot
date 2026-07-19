"""Phase 7B scale hardening and background reliability tests."""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.chat.models import (
    ChatSession,
    ComplianceExportJob,
    Feedback,
    KnowledgeGapTicket,
    Message,
)
from apps.knowledge.models import IngestionJob
from apps.notifications.models import Notification
from apps.spaces.models import BusinessLine, KnowledgeSpace, Organization, SpaceMembership
from apps.spaces.test_utils import create_test_space


User = get_user_model()


class Phase7BBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Scale Org", slug="scale-org")
        cls.line = BusinessLine.objects.create(
            organization=cls.org, name="Scale Line", code="scale-line"
        )
        cls.owner = User.objects.create_user(
            username="scale-owner", email="scale-owner@example.com", password="test"
        )
        cls.space = create_test_space(
            organization=cls.org,
            owner=cls.owner,
            business_line=cls.line,
            name="Scale Space",
            code="scale-space",
        )
        cls.reviewer = User.objects.create_user(
            username="scale-reviewer", email="scale-reviewer@example.com", password="test"
        )
        cls.member = User.objects.create_user(
            username="scale-member", email="scale-member@example.com", password="test"
        )
        cls.other = User.objects.create_user(
            username="scale-other", email="scale-other@example.com", password="test"
        )
        SpaceMembership.objects.create(user=cls.reviewer, space=cls.space, role=SpaceMembership.ROLE_REVIEWER)
        SpaceMembership.objects.create(user=cls.member, space=cls.space, role=SpaceMembership.ROLE_MEMBER)

    def setUp(self):
        self.client.force_authenticate(self.reviewer)
        self.session = ChatSession.objects.create(user=self.member, space=self.space, title="Scale")
        self.question = Message.objects.create(
            session=self.session, space=self.space, role="user", content="Where is policy?"
        )
        self.answer = Message.objects.create(
            session=self.session, space=self.space, role="assistant", content="Old policy"
        )
        self.feedback = Feedback.objects.create(
            message=self.answer,
            user=self.member,
            space=self.space,
            feedback_type="outdated",
            flag_for_review=True,
            status=Feedback.STATUS_PENDING_REVIEW,
            review_context={"question": self.question.content, "answer": self.answer.content},
        )


class ExportRetryApiTest(Phase7BBase):
    def test_failed_export_job_retry_creates_new_job_and_preserves_failure_evidence(self):
        failed = ComplianceExportJob.objects.create(
            requested_by=self.reviewer,
            space=self.space,
            dataset=ComplianceExportJob.DATASET_FEEDBACK,
            status=ComplianceExportJob.STATUS_FAILED,
            error_code="worker_timeout",
            safe_error_summary="Export worker timed out.",
            date_from=timezone.now() - timedelta(days=30),
            date_to=timezone.now(),
        )

        response = self.client.post(f"/api/v1/admin/reports/export-jobs/{failed.id}/retry/")

        self.assertEqual(response.status_code, 202)
        retry = ComplianceExportJob.objects.get(id=response.data["id"])
        self.assertEqual(retry.status, ComplianceExportJob.STATUS_SUCCEEDED)
        self.assertEqual(retry.retry_of_id, failed.id)
        failed.refresh_from_db()
        self.assertEqual(failed.status, ComplianceExportJob.STATUS_FAILED)
        self.assertEqual(failed.error_code, "worker_timeout")
        self.assertTrue(AuditLog.objects.filter(action="export_job_retry").exists())

    def test_export_job_retry_is_scoped(self):
        failed = ComplianceExportJob.objects.create(
            requested_by=self.reviewer,
            space=self.space,
            dataset=ComplianceExportJob.DATASET_FEEDBACK,
            status=ComplianceExportJob.STATUS_FAILED,
        )
        self.client.force_authenticate(self.other)

        response = self.client.post(f"/api/v1/admin/reports/export-jobs/{failed.id}/retry/")

        self.assertEqual(response.status_code, 403)


class SlaDryRunTest(Phase7BBase):
    def test_sla_scan_dry_run_reports_candidates_without_notifications_or_audit(self):
        old = timezone.now() - timedelta(days=4)
        Feedback.objects.filter(id=self.feedback.id).update(created_at=old)
        KnowledgeGapTicket.objects.create(
            space=self.space,
            feedback=self.feedback,
            question_snapshot=self.question.content,
            normalized_question_hash=KnowledgeGapTicket.hash_question(self.question.content),
            status=KnowledgeGapTicket.STATUS_OPEN,
            priority="high",
            created_at=old,
        )
        out = StringIO()

        call_command("scan_quality_sla", "--dry-run", stdout=out)

        self.assertIn("dry_run=true", out.getvalue())
        self.assertIn("candidates=", out.getvalue())
        self.assertEqual(Notification.objects.filter(type=Notification.TYPE_SYSTEM).count(), 0)
        self.assertFalse(AuditLog.objects.filter(action="sla_alert_created").exists())


class ScaleIndexGuardTest(APITestCase):
    def _index_fields(self, model):
        return {tuple(index.fields) for index in model._meta.indexes}

    def test_scale_path_indexes_exist(self):
        self.assertIn(("recipient", "type", "is_read", "created_at"), self._index_fields(Notification))
        self.assertIn(("space_id", "action", "result", "created_at"), self._index_fields(AuditLog))
        self.assertIn(("status", "space", "created_at"), self._index_fields(IngestionJob))
        self.assertIn(("status", "requested_by", "created_at"), self._index_fields(ComplianceExportJob))
