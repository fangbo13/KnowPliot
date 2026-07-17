"""Phase 5A answer feedback foundation tests."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.chat.models import ChatSession, Feedback, Message, ModelInvocation
from apps.spaces.models import BusinessLine, KnowledgeSpace, Organization, SpaceMembership


User = get_user_model()


class Phase5AFeedbackBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Feedback Org", slug="feedback-org")
        cls.line = BusinessLine.objects.create(
            organization=cls.org, name="Feedback Line", code="feedback-line"
        )
        cls.space = KnowledgeSpace.objects.create(
            organization=cls.org,
            business_line=cls.line,
            name="Feedback Space",
            code="feedback-space",
        )
        cls.user = User.objects.create_user(
            username="feedback-user",
            email="feedback-user@example.com",
            password="test",
        )
        cls.other_user = User.objects.create_user(
            username="feedback-other",
            email="feedback-other@example.com",
            password="test",
        )
        SpaceMembership.objects.create(
            user=cls.user,
            space=cls.space,
            role=SpaceMembership.ROLE_MEMBER,
        )
        SpaceMembership.objects.create(
            user=cls.other_user,
            space=cls.space,
            role=SpaceMembership.ROLE_MEMBER,
        )

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.session = ChatSession.objects.create(
            user=self.user, space=self.space, title="Feedback session"
        )
        self.question = Message.objects.create(
            session=self.session,
            space=self.space,
            role="user",
            content="What is the reimbursement process?",
        )
        self.answer = Message.objects.create(
            session=self.session,
            space=self.space,
            role="assistant",
            content="Submit your receipt in the portal.",
            model_used="test-model",
            retrieval_count=1,
        )

    def url(self, message=None):
        return f"/api/v1/chat/messages/{message or self.answer.id}/feedback/"


class FeedbackApiTest(Phase5AFeedbackBase):
    def test_put_upserts_feedback_by_user_and_message_with_safe_snapshot_and_audit(self):
        response = self.client.put(
            self.url(),
            {
                "type": "incorrect",
                "comment": "The policy changed.",
                "suggested_source": "Finance portal",
                "flag_for_review": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        feedback = Feedback.objects.get(message=self.answer, user=self.user)
        self.assertEqual(feedback.feedback_type, "incorrect")
        self.assertEqual(feedback.status, "pending_review")
        self.assertEqual(feedback.suggested_source, "Finance portal")
        self.assertTrue(feedback.flag_for_review)
        self.assertEqual(feedback.review_context["question"], self.question.content)
        self.assertEqual(feedback.review_context["answer"], self.answer.content)
        self.assertEqual(feedback.review_context["retrieval_count"], 1)

        audit = AuditLog.objects.get(action="feedback_submit")
        self.assertEqual(audit.space_id, self.space.id)
        self.assertEqual(audit.result, "success")
        self.assertEqual(audit.details["feedback_type"], "incorrect")
        self.assertNotIn("The policy changed.", str(audit.details))

        second = self.client.put(
            self.url(),
            {"type": "outdated", "comment": "", "flag_for_review": False},
            format="json",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Feedback.objects.filter(message=self.answer, user=self.user).count(), 1)
        feedback.refresh_from_db()
        self.assertEqual(feedback.feedback_type, "outdated")
        self.assertEqual(feedback.status, "submitted")
        self.assertTrue(AuditLog.objects.filter(action="feedback_update").exists())

    def test_get_returns_current_users_feedback_only(self):
        Feedback.objects.create(
            message=self.answer,
            user=self.other_user,
            space=self.space,
            feedback_type="helpful",
            status="submitted",
        )

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["feedback"])

    def test_delete_withdraws_feedback_without_physical_delete(self):
        feedback = Feedback.objects.create(
            message=self.answer,
            user=self.user,
            space=self.space,
            feedback_type="unhelpful",
            status="submitted",
        )

        response = self.client.delete(self.url())

        self.assertEqual(response.status_code, 200)
        feedback.refresh_from_db()
        self.assertEqual(feedback.status, "withdrawn")
        self.assertTrue(AuditLog.objects.filter(action="feedback_withdraw").exists())

    def test_rejects_non_assistant_and_cross_user_messages(self):
        own_user_message = Message.objects.create(
            session=self.session,
            space=self.space,
            role="user",
            content="User message",
        )
        self.assertEqual(
            self.client.put(self.url(own_user_message.id), {"type": "helpful"}, format="json").status_code,
            400,
        )

        other_session = ChatSession.objects.create(
            user=self.other_user, space=self.space, title="Other"
        )
        other_answer = Message.objects.create(
            session=other_session,
            space=self.space,
            role="assistant",
            content="Other answer",
        )
        self.assertEqual(
            self.client.put(self.url(other_answer.id), {"type": "helpful"}, format="json").status_code,
            404,
        )


class ModelInvocationQuestionLinkTest(Phase5AFeedbackBase):
    def test_model_invocation_can_link_question_for_failed_and_successful_attempts(self):
        invocation = ModelInvocation.objects.create(
            session=self.session,
            question_message=self.question,
            message=self.answer,
            space=self.space,
            model="test-model",
            status="success",
        )

        self.assertEqual(invocation.question_message, self.question)
