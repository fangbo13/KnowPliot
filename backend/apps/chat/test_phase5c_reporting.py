"""Phase 5C analytics and compliance-reporting tests."""

import csv
import io

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.chat.models import (
    Citation,
    ChatSession,
    Feedback,
    KnowledgeGapTicket,
    Message,
    ModelInvocation,
)
from apps.knowledge.models import Document
from apps.spaces.models import BusinessLine, KnowledgeSpace, Organization, SpaceMembership
from apps.spaces.test_utils import create_test_space


User = get_user_model()


class Phase5CBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Report Org", slug="report-org")
        cls.line = BusinessLine.objects.create(
            organization=cls.org, name="Report Line", code="report-line"
        )
        cls.space = create_test_space(
            organization=cls.org,
            business_line=cls.line,
            name="Report Space",
            code="report-space",
        )
        cls.other_space = create_test_space(
            organization=cls.org,
            business_line=cls.line,
            name="Other Report Space",
            code="other-report-space",
        )
        cls.reviewer = User.objects.create_user(
            username="report-reviewer", email="report-reviewer@example.com", password="test"
        )
        cls.member = User.objects.create_user(
            username="report-member", email="report-member@example.com", password="test"
        )
        SpaceMembership.objects.create(
            user=cls.reviewer, space=cls.space, role=SpaceMembership.ROLE_REVIEWER
        )
        SpaceMembership.objects.create(
            user=cls.member, space=cls.space, role=SpaceMembership.ROLE_MEMBER
        )

    def setUp(self):
        self.client.force_authenticate(self.reviewer)
        self.session = ChatSession.objects.create(user=self.member, space=self.space, title="Report")
        self.question = Message.objects.create(
            session=self.session, space=self.space, role="user", content="Where is the handbook?"
        )
        self.answer = Message.objects.create(
            session=self.session,
            space=self.space,
            role="assistant",
            content="I do not know.",
            retrieval_count=0,
            model_used="test-model",
        )
        self.feedback = Feedback.objects.create(
            message=self.answer,
            user=self.member,
            space=self.space,
            feedback_type="missing_source",
            flag_for_review=True,
            status=Feedback.STATUS_RESOLVED,
            resolved_at=timezone.now(),
            review_context={"question": self.question.content, "answer": self.answer.content},
        )
        self.gap = KnowledgeGapTicket.objects.create(
            space=self.space,
            feedback=self.feedback,
            question_snapshot=self.question.content,
            normalized_question_hash=KnowledgeGapTicket.hash_question(self.question.content),
            status=KnowledgeGapTicket.STATUS_OPEN,
            priority="high",
        )
        ModelInvocation.objects.create(
            session=self.session,
            question_message=self.question,
            message=self.answer,
            space=self.space,
            model="test-model",
            status="failure",
            error_code="stream_error",
        )
        used_doc = Document.objects.create(
            space=self.space,
            uploaded_by=self.reviewer,
            title="Used Handbook",
            file="documents/used.txt",
            file_type="txt",
            file_size=12,
            status="active",
        )
        Document.objects.create(
            space=self.other_space,
            uploaded_by=self.reviewer,
            title="Hidden Handbook",
            file="documents/hidden.txt",
            file_type="txt",
            file_size=12,
            status="active",
        )
        for _ in range(5):
            Citation.objects.create(
                space=self.space,
                message=self.answer,
                document=used_doc,
                relevance_score=0.9,
                quoted_text="handbook",
            )


class KnowledgeQualityReportTest(Phase5CBase):
    def test_quality_report_scopes_metrics_and_groups_unanswered_questions(self):
        response = self.client.get("/api/v1/admin/reports/knowledge-quality/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["feedback"]["total"], 1)
        self.assertEqual(response.data["feedback"]["flagged_rate"], 1.0)
        self.assertEqual(response.data["reviews"]["resolved"], 1)
        self.assertEqual(response.data["knowledge_gaps"]["open"], 1)
        self.assertEqual(response.data["unanswered_questions"][0]["question"], self.question.content)
        self.assertEqual(response.data["documents"]["high_citation"][0]["title"], "Used Handbook")

    def test_member_cannot_access_quality_report(self):
        self.client.force_authenticate(self.member)
        response = self.client.get("/api/v1/admin/reports/knowledge-quality/")
        self.assertEqual(response.status_code, 403)


class ComplianceExportTest(Phase5CBase):
    def test_feedback_export_uses_utf8_bom_stable_columns_and_audits(self):
        response = self.client.get(
            "/api/v1/admin/reports/export/",
            {"dataset": "feedback", "format": "csv"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content)))
        self.assertEqual(
            rows[0],
            ["id", "space_id", "message_id", "user_id", "feedback_type", "status", "flag_for_review", "created_at"],
        )
        self.assertEqual(rows[1][4], "missing_source")
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        audit = AuditLog.objects.get(action="audit_export")
        self.assertEqual(audit.details["dataset"], "feedback")
        self.assertNotIn("missing_source", str(audit.details.get("content", "")))

    def test_export_rejects_unknown_dataset(self):
        response = self.client.get(
            "/api/v1/admin/reports/export/",
            {"dataset": "unknown", "format": "csv"},
        )
        self.assertEqual(response.status_code, 400)
