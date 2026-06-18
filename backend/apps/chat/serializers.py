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
    content = serializers.CharField(max_length=4000)


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ["id", "message", "rating", "reason", "comment", "created_at"]
        read_only_fields = ["id", "created_at"]
