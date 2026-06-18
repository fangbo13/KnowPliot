"""Chat views."""

import json
import time

from django.http import StreamingHttpResponse
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ChatSession, Message, Citation, Feedback
from .serializers import (
    ChatSessionSerializer,
    ChatMessageRequestSerializer,
    FeedbackSerializer,
    MessageSerializer,
)


class ChatSessionListCreateView(generics.ListCreateAPIView):
    """List and create chat sessions."""

    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatSession.objects.filter(
            user=self.request.user, is_active=True
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ChatSessionDetailView(generics.RetrieveDestroyAPIView):
    """Get and delete a chat session."""

    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)


class ChatSessionMessagesView(generics.ListAPIView):
    """List messages in a session."""

    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Message.objects.filter(
            session_id=self.kwargs["session_id"]
        ).order_by("created_at")


def _save_citations(assistant_message, citations_data):
    """Save citation records for an assistant message."""
    from apps.knowledge.models import Document, DocumentChunk

    for cit in citations_data:
        try:
            doc = Document.objects.get(id=cit.get("document_id"))
            chunk = None
            if cit.get("chunk_id"):
                chunk = DocumentChunk.objects.filter(id=cit["chunk_id"]).first()

            Citation.objects.create(
                message=assistant_message,
                document=doc,
                chunk=chunk,
                relevance_score=cit.get("score", 0),
                page_number=cit.get("page_number"),
                quoted_text=cit.get("quoted_text", ""),
            )
        except Exception:
            pass


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def send_message(request, session_id):
    """Send a message and get streaming response (SSE)."""
    serializer = ChatMessageRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    content = serializer.validated_data["content"]
    user = request.user
    language = getattr(user, "language_preference", "en")

    # Get or create session
    session, created = ChatSession.objects.get_or_create(
        id=session_id,
        defaults={"user": user, "title": content[:50]},
    )

    # Update title if new or empty
    if created or not session.title:
        session.title = content[:50]
        session.save(update_fields=["title"])

    # Save user message
    Message.objects.create(session=session, role="user", content=content)

    # Get conversation history (last 8 turns)
    history = list(
        Message.objects.filter(session=session)
        .exclude(role="user", content=content)  # exclude the one we just saved
        .order_by("-created_at")[:16]
        .values_list("role", "content")
    )
    history.reverse()

    from apps.rag.pipeline import RAGPipeline

    pipeline = RAGPipeline()

    def event_stream():
        start_time = time.time()
        response_tokens = []
        citations_data = []

        try:
            for event in pipeline.retrieve_and_generate(
                query=content,
                user_profile=user,
                conversation_history=history,
                language=language,
            ):
                event_type = event.get("event")
                data = event.get("data", {})

                if event_type == "citations":
                    citations_data = data
                    yield "event: citations\n"
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                elif event_type == "token":
                    token = data.get("token", "")
                    response_tokens.append(token)
                    yield "event: token\n"
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield "event: error\n"
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            return

        # Save assistant message
        elapsed_ms = int((time.time() - start_time) * 1000)
        assistant_content = "".join(response_tokens)
        assistant_message = Message.objects.create(
            session=session,
            role="assistant",
            content=assistant_content,
            token_count=len(response_tokens),
            model_used=pipeline.model_name,
            response_time_ms=elapsed_ms,
            retrieval_count=len(citations_data),
        )

        # Save citations
        _save_citations(assistant_message, citations_data)

        yield "event: done\n"
        yield f"data: {json.dumps({'message_id': str(assistant_message.id), 'session_id': str(session.id), 'model': pipeline.model_name}, ensure_ascii=False)}\n\n"

    response = StreamingHttpResponse(
        event_stream(), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def submit_feedback(request, message_id):
    """Submit feedback on a message."""
    message = Message.objects.get(id=message_id, session__user=request.user)
    serializer = FeedbackSerializer(
        data={**request.data, "message": str(message.id)}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def quick_actions(request):
    """Get quick action questions."""
    language = getattr(request.user, "language_preference", "en")

    if language == "zh":
        actions = [
            {"id": "1", "question": "如何设置我的公司邮箱和电脑？", "category": "it"},
            {"id": "2", "question": "报销流程是什么？", "category": "hr"},
            {"id": "3", "question": "我的年假有多少天？", "category": "benefits"},
            {"id": "4", "question": "入职培训有哪些课程？", "category": "training"},
            {"id": "5", "question": "办公室在哪里？怎么去？", "category": "office"},
            {"id": "6", "question": "我的导师/Buddy是谁？", "category": "team"},
        ]
    else:
        actions = [
            {"id": "1", "question": "How do I set up my company email and laptop?", "category": "it"},
            {"id": "2", "question": "What is the expense reimbursement process?", "category": "hr"},
            {"id": "3", "question": "How many annual leave days do I have?", "category": "benefits"},
            {"id": "4", "question": "What training courses are included in onboarding?", "category": "training"},
            {"id": "5", "question": "Where is the office and how do I get there?", "category": "office"},
            {"id": "6", "question": "Who is my mentor/buddy?", "category": "team"},
        ]

    return Response({"actions": actions})
