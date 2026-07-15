# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat serializers."""

import uuid

from rest_framework import serializers

from .models import (
    ChatSession,
    ChatTurn,
    Feedback,
    FeedbackReviewEvent,
    KnowledgeGapTicket,
    Message,
)


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ChatSession
        fields = [
            "id", "user", "title", "is_active", "is_pinned",
            "created_at", "updated_at", "message_count",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


class MessageSerializer(serializers.ModelSerializer):
    citations = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id", "session", "role", "content", "token_count",
            "model_used", "response_time_ms", "retrieval_count",
            "confidence_score", "confidence_label", "needs_human_review",
            "retrieval_mode", "retrieval_latency_ms",
            "created_at", "citations",
        ]
        read_only_fields = ["id", "created_at"]

    def get_citations(self, obj):
        citations = obj.citations.all()
        return [
            {
                "id": str(c.id),
                "document_id": str(c.document.id),
                "document_title": c.document.title,
                "page_number": c.page_number,
                "relevance_score": c.relevance_score,
                "quoted_text": c.quoted_text,
            }
            for c in citations
        ]


class ChatMessageRequestSerializer(serializers.Serializer):
    """Serializer for sending a chat message."""
    content = serializers.CharField(max_length=4000, min_length=1)
    client_request_id = serializers.UUIDField(default=uuid.uuid4, required=False)
    answer_mode = serializers.ChoiceField(
        choices=[choice[0] for choice in ChatTurn.ANSWER_MODE_CHOICES],
        default=ChatTurn.ANSWER_MODE_FAST,
        required=False,
    )
    protocol_version = serializers.ChoiceField(
        choices=[1, 2],
        default=1,
        required=False,
    )

    def validate_content(self, value):
        """Strip whitespace and reject empty/whitespace-only messages."""
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Message cannot be empty or whitespace-only.")
        return stripped


class ChatTurnStatusSerializer(serializers.ModelSerializer):
    """Owner-visible Turn state; raw prompts and operational exceptions stay private."""

    answer = serializers.SerializerMethodField()

    class Meta:
        model = ChatTurn
        fields = [
            "id",
            "client_request_id",
            "session",
            "status",
            "answer_mode",
            "model_id",
            "attempt_count",
            "last_event_seq",
            "error_code",
            "started_at",
            "updated_at",
            "completed_at",
            "answer",
        ]
        read_only_fields = fields

    def get_answer(self, obj):
        if obj.status != ChatTurn.STATUS_COMPLETED or obj.assistant_message is None:
            return None
        return MessageSerializer(obj.assistant_message, context=self.context).data


class FeedbackSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(
        choices=[choice[0] for choice in Feedback.FEEDBACK_TYPE_CHOICES],
        source="feedback_type",
        required=False,
    )

    class Meta:
        model = Feedback
        fields = [
            "id",
            "space",
            "message",
            "user",
            "type",
            "feedback_type",
            "rating",
            "reason",
            "comment",
            "suggested_source",
            "flag_for_review",
            "status",
            "reviewer",
            "resolution_code",
            "resolution_notes",
            "resolved_at",
            "review_context",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "space",
            "user",
            "feedback_type",
            "status",
            "reviewer",
            "resolution_code",
            "resolution_notes",
            "resolved_at",
            "review_context",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        rating = attrs.get("rating")
        reason = attrs.get("reason")
        feedback_type = attrs.get("feedback_type")
        if feedback_type is None and rating is not None:
            attrs["feedback_type"] = self._legacy_type_from_rating(rating, reason)
        if attrs.get("feedback_type") is None:
            raise serializers.ValidationError({"type": "This field is required."})
        return attrs

    @staticmethod
    def _legacy_type_from_rating(rating, reason):
        if rating == 2:
            return Feedback.FEEDBACK_TYPE_HELPFUL
        if reason == "outdated":
            return Feedback.FEEDBACK_TYPE_OUTDATED
        if reason == "inaccurate":
            return Feedback.FEEDBACK_TYPE_INCORRECT
        return Feedback.FEEDBACK_TYPE_UNHELPFUL


class FeedbackReviewEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)
    reviewer_email = serializers.EmailField(source="reviewer.email", read_only=True)

    class Meta:
        model = FeedbackReviewEvent
        fields = [
            "id",
            "feedback",
            "space",
            "actor",
            "actor_email",
            "reviewer",
            "reviewer_email",
            "event_type",
            "from_status",
            "to_status",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class FeedbackReviewSerializer(FeedbackSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    reviewer_email = serializers.EmailField(source="reviewer.email", read_only=True)
    events = FeedbackReviewEventSerializer(source="review_events", many=True, read_only=True)

    class Meta(FeedbackSerializer.Meta):
        fields = FeedbackSerializer.Meta.fields + [
            "user_email",
            "reviewer_email",
            "events",
        ]


class KnowledgeGapTicketSerializer(serializers.ModelSerializer):
    assignee_email = serializers.EmailField(source="assignee.email", read_only=True)
    feedback_type = serializers.CharField(source="feedback.feedback_type", read_only=True)
    question = serializers.CharField(source="question_snapshot", read_only=True)

    class Meta:
        model = KnowledgeGapTicket
        fields = [
            "id",
            "space",
            "feedback",
            "feedback_type",
            "question",
            "question_snapshot",
            "status",
            "priority",
            "assignee",
            "assignee_email",
            "suggested_source",
            "resolution_notes",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "feedback_type",
            "question",
            "normalized_question_hash",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
