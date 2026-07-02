# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat serializers."""

from rest_framework import serializers
from .models import ChatSession, Message, Citation, Feedback


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ChatSession
        fields = ["id", "user", "title", "is_active", "created_at", "updated_at", "message_count"]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


class MessageSerializer(serializers.ModelSerializer):
    citations = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id", "session", "role", "content", "token_count",
            "model_used", "response_time_ms", "retrieval_count",
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

    def validate_content(self, value):
        """Strip whitespace and reject empty/whitespace-only messages."""
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Message cannot be empty or whitespace-only.")
        return stripped


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
