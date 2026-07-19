"""Phase 5B scoped review queue and knowledge-gap tests."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.chat.models import (
    ChatSession,
    Feedback,
    FeedbackReviewEvent,
    KnowledgeGapTicket,
    Message,
)
from apps.spaces.models import BusinessLine, KnowledgeSpace, Organization, SpaceMembership
from apps.spaces.test_utils import create_test_space


User = get_user_model()


class Phase5BBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Review Org", slug="review-org")
        cls.line = BusinessLine.objects.create(
            organization=cls.org, name="Review Line", code="review-line"
        )
        cls.owner = User.objects.create_user(
            username="review-owner", email="review-owner@example.com", password="test"
        )
        cls.space = create_test_space(
            organization=cls.org,
            owner=cls.owner,
            business_line=cls.line,
            name="Review Space",
            code="review-space",
        )
        cls.other_space = create_test_space(
            organization=cls.org,
            business_line=cls.line,
            name="Other Review Space",
            code="other-review-space",
        )
        cls.member = User.objects.create_user(
            username="review-member", email="review-member@example.com", password="test"
        )
        cls.reviewer = User.objects.create_user(
            username="reviewer", email="reviewer@example.com", password="test"
        )
        SpaceMembership.objects.create(
            user=cls.member, space=cls.space, role=SpaceMembership.ROLE_MEMBER
        )
        SpaceMembership.objects.create(
            user=cls.reviewer, space=cls.space, role=SpaceMembership.ROLE_REVIEWER
        )

    def setUp(self):
        self.session = ChatSession.objects.create(
            user=self.member, space=self.space, title="Review session"
        )
        self.question = Message.objects.create(
            session=self.session,
            space=self.space,
            role="user",
            content="Where is the latest expense policy?",
        )
        self.answer = Message.objects.create(
            session=self.session,
            space=self.space,
            role="assistant",
            content="Use the old wiki.",
            retrieval_count=0,
        )
        self.feedback = Feedback.objects.create(
            message=self.answer,
            user=self.member,
            space=self.space,
            feedback_type="missing_source",
            flag_for_review=True,
            status=Feedback.STATUS_PENDING_REVIEW,
            review_context={
                "question": self.question.content,
                "answer": self.answer.content,
                "citations": [],
                "retrieval_count": 0,
            },
        )


class ReviewQueueApiTest(Phase5BBase):
    def test_reviewer_can_list_claim_and_resolve_scoped_feedback(self):
        self.client.force_authenticate(self.reviewer)

        listing = self.client.get("/api/v1/admin/quality/feedback/", {"space": str(self.space.id)})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)

        claim = self.client.post(f"/api/v1/admin/quality/feedback/{self.feedback.id}/claim/")
        self.assertEqual(claim.status_code, 200)
        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.status, Feedback.STATUS_IN_REVIEW)
        self.assertEqual(self.feedback.reviewer, self.reviewer)

        resolve = self.client.post(
            f"/api/v1/admin/quality/feedback/{self.feedback.id}/resolve/",
            {"resolution_code": "source_updated", "resolution_notes": "Added current source."},
            format="json",
        )
        self.assertEqual(resolve.status_code, 200)
        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.status, Feedback.STATUS_RESOLVED)
        self.assertEqual(
            list(FeedbackReviewEvent.objects.values_list("event_type", flat=True)),
            ["claim", "resolve"],
        )
        self.assertTrue(AuditLog.objects.filter(action="feedback_review_resolve").exists())

    def test_member_cannot_access_review_queue(self):
        self.client.force_authenticate(self.member)
        response = self.client.get("/api/v1/admin/quality/feedback/")
        self.assertEqual(response.status_code, 403)

    def test_illegal_state_transition_returns_409(self):
        self.feedback.status = Feedback.STATUS_SUBMITTED
        self.feedback.save(update_fields=["status"])
        self.client.force_authenticate(self.reviewer)

        response = self.client.post(f"/api/v1/admin/quality/feedback/{self.feedback.id}/claim/")

        self.assertEqual(response.status_code, 409)

    def test_user_cannot_withdraw_after_review_started(self):
        self.feedback.status = Feedback.STATUS_IN_REVIEW
        self.feedback.reviewer = self.reviewer
        self.feedback.save(update_fields=["status", "reviewer"])
        self.client.force_authenticate(self.member)

        response = self.client.delete(f"/api/v1/chat/messages/{self.answer.id}/feedback/")

        self.assertEqual(response.status_code, 409)
        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.status, Feedback.STATUS_IN_REVIEW)

    def test_owner_can_assign_and_reopen_feedback(self):
        self.feedback.status = Feedback.STATUS_RESOLVED
        self.feedback.save(update_fields=["status"])
        self.client.force_authenticate(self.owner)

        assign = self.client.post(
            f"/api/v1/admin/quality/feedback/{self.feedback.id}/assign/",
            {"reviewer": str(self.reviewer.id)},
            format="json",
        )
        self.assertEqual(assign.status_code, 200)
        reopen = self.client.post(f"/api/v1/admin/quality/feedback/{self.feedback.id}/reopen/")
        self.assertEqual(reopen.status_code, 200)
        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.status, Feedback.STATUS_PENDING_REVIEW)
        self.assertEqual(self.feedback.reviewer, self.reviewer)


class KnowledgeGapApiTest(Phase5BBase):
    def test_duplicate_open_gap_returns_existing_ticket(self):
        self.client.force_authenticate(self.reviewer)
        url = "/api/v1/admin/quality/gaps/"
        body = {
            "space": str(self.space.id),
            "feedback": str(self.feedback.id),
            "question": "Where is the latest expense policy?",
            "priority": "high",
            "suggested_source": "Finance SharePoint",
        }

        first = self.client.post(url, body, format="json")
        second = self.client.post(url, body, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(KnowledgeGapTicket.objects.count(), 1)
        self.assertEqual(second.data["id"], first.data["id"])

    def test_gap_assign_resolve_and_reopen_are_audited(self):
        ticket = KnowledgeGapTicket.objects.create(
            space=self.space,
            feedback=self.feedback,
            question_snapshot=self.question.content,
            normalized_question_hash=KnowledgeGapTicket.hash_question(self.question.content),
            priority="medium",
        )
        self.client.force_authenticate(self.owner)

        assign = self.client.post(
            f"/api/v1/admin/quality/gaps/{ticket.id}/assign/",
            {"assignee": str(self.reviewer.id)},
            format="json",
        )
        resolve = self.client.post(
            f"/api/v1/admin/quality/gaps/{ticket.id}/resolve/",
            {"resolution_notes": "Published new policy."},
            format="json",
        )
        reopen = self.client.post(f"/api/v1/admin/quality/gaps/{ticket.id}/reopen/")

        self.assertEqual(assign.status_code, 200)
        self.assertEqual(resolve.status_code, 200)
        self.assertEqual(reopen.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="knowledge_gap_reopen").exists())
