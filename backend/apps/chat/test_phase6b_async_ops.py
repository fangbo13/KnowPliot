"""Phase 6B async export and quality SLA tests."""

from datetime import timedelta

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
from apps.notifications.models import Notification
from apps.spaces.models import BusinessLine, KnowledgeSpace, Organization, SpaceMembership
from apps.spaces.test_utils import create_test_space


User = get_user_model()


class Phase6BBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Async Org", slug="async-org")
        cls.line = BusinessLine.objects.create(
            organization=cls.org, name="Async Line", code="async-line"
        )
        cls.owner = User.objects.create_user(
            username="async-owner", email="async-owner@example.com", password="test"
        )
        cls.space = create_test_space(
            organization=cls.org,
            owner=cls.owner,
            business_line=cls.line,
            name="Async Space",
            code="async-space",
        )
        cls.reviewer = User.objects.create_user(
            username="async-reviewer", email="async-reviewer@example.com", password="test"
        )
        cls.member = User.objects.create_user(
            username="async-member", email="async-member@example.com", password="test"
        )
        cls.other = User.objects.create_user(
            username="async-other", email="async-other@example.com", password="test"
        )
        SpaceMembership.objects.create(user=cls.reviewer, space=cls.space, role=SpaceMembership.ROLE_REVIEWER)
        SpaceMembership.objects.create(user=cls.member, space=cls.space, role=SpaceMembership.ROLE_MEMBER)

    def setUp(self):
        self.client.force_authenticate(self.reviewer)
        self.session = ChatSession.objects.create(user=self.member, space=self.space, title="Async")
        self.question = Message.objects.create(
            session=self.session, space=self.space, role="user", content="Where is the new policy?"
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


class AsyncExportJobApiTest(Phase6BBase):
    def test_create_list_download_export_job_and_audit(self):
        create = self.client.post(
            "/api/v1/admin/reports/export-jobs/",
            {"dataset": "feedback", "space": str(self.space.id)},
            format="json",
        )
        self.assertEqual(create.status_code, 201)
        job_id = create.data["id"]
        job = ComplianceExportJob.objects.get(id=job_id)
        self.assertEqual(job.status, ComplianceExportJob.STATUS_SUCCEEDED)
        self.assertEqual(job.row_count, 1)

        listing = self.client.get("/api/v1/admin/reports/export-jobs/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)

        download = self.client.get(f"/api/v1/admin/reports/export-jobs/{job_id}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download.content.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(AuditLog.objects.filter(action="export_job_create").exists())
        self.assertTrue(AuditLog.objects.filter(action="export_job_complete").exists())
        self.assertTrue(AuditLog.objects.filter(action="audit_export_download").exists())

    def test_export_job_download_is_creator_scoped(self):
        job = ComplianceExportJob.objects.create(
            requested_by=self.reviewer,
            space=self.space,
            dataset="feedback",
            status=ComplianceExportJob.STATUS_SUCCEEDED,
            result_file="missing.csv",
        )
        self.client.force_authenticate(self.other)
        response = self.client.get(f"/api/v1/admin/reports/export-jobs/{job.id}/download/")
        self.assertEqual(response.status_code, 403)


class QualitySlaCommandTest(Phase6BBase):
    def test_sla_command_creates_notifications_once_for_overdue_feedback_and_gaps(self):
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

        call_command("scan_quality_sla")
        call_command("scan_quality_sla")

        notifications = Notification.objects.filter(type=Notification.TYPE_SYSTEM)
        self.assertGreaterEqual(notifications.count(), 2)
        keys = list(notifications.values_list("metadata__dedupe_key", flat=True))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(AuditLog.objects.filter(action="sla_alert_created").exists())
