"""Chat views."""

import json
import logging
import time

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .models import ChatSession, Message, Citation, Feedback
from .serializers import (
    ChatSessionSerializer,
    ChatMessageRequestSerializer,
    FeedbackSerializer,
    MessageSerializer,
)
# V6.0: space isolation helpers.
from apps.spaces.permissions import (
    CHAT_ASK,
    effective_space_role,
    resolve_request_space,
)

logger = logging.getLogger(__name__)


def _default_space_for(user):
    """Backward-compatible fallback space when no X-Space-Id header is sent.

    Returns the user's most-recently-accessed active space, or the default
    'general' space. Lazily provisions membership so pre-V6.0 clients keep
    working during the frontend rollout.
    """
    from apps.spaces.models import SpaceMembership
    from apps.spaces.views import ensure_default_membership

    ensure_default_membership(user)
    membership = (
        SpaceMembership.objects.filter(user=user, status="active")
        .select_related("space")
        .first()
    )
    return membership.space if membership else None


# V3.5 HIGH-004: Cursor pagination for sessions
class SessionCursorPagination(CursorPagination):
    ordering = '-updated_at'
    page_size = 20


# V3.5 HIGH-004: Cursor pagination for messages
class MessageCursorPagination(CursorPagination):
    ordering = 'created_at'
    page_size = 40  # ~20 rounds


def _estimate_token_count(text: str) -> int:
    """Estimate token count for the assistant response.

    Uses tiktoken if available (for OpenAI-compatible models),
    otherwise falls back to a character-based estimate.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Fallback: rough estimate (~4 chars per token for English)
        return max(1, len(text) // 4)
    except Exception:
        # Fallback for any tiktoken error
        return max(1, len(text) // 4)


class ChatSessionListCreateView(generics.ListCreateAPIView):
    """List and create chat sessions."""

    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    # V3.5 HIGH-004: Enable cursor pagination for sessions (was None)
    pagination_class = SessionCursorPagination
    ordering = '-updated_at'  # Most recent first

    def get_queryset(self):
        qs = ChatSession.objects.filter(user=self.request.user, is_active=True)
        # V6.0: when a space is active, the sidebar only shows that space's
        # sessions. Without a header (legacy client) all sessions are returned.
        space = resolve_request_space(self.request, required=False)
        if space is not None:
            qs = qs.filter(space=space)
        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        space = resolve_request_space(self.request, require_perm=CHAT_ASK, required=False) \
            or _default_space_for(self.request.user)
        serializer.save(user=self.request.user, space=space)


class ChatSessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update (rename), and delete a chat session."""

    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        """Only update title field — preserve updated_at so session stays in
        its original position in the sidebar list instead of jumping to the top."""
        serializer.save(update_fields=["title"])


class ChatSessionMessagesView(generics.ListAPIView):
    """List messages in a session."""

    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    # V3.5 HIGH-004: Enable cursor pagination for messages + N+1 fix via prefetch_related
    pagination_class = MessageCursorPagination

    def get_queryset(self):
        # V3.5 HIGH-004: prefetch_related eliminates N+1 citation queries
        return Message.objects.filter(
            session_id=self.kwargs["session_id"],
            session__user=self.request.user,
            session__is_active=True,
        ).order_by("created_at").prefetch_related("citations__document")


def _save_citations(assistant_message, citations_data, space=None):
    """Save citation records for an assistant message.

    V6.0: citations carry the message's space, and we defensively skip any
    document that is not in the active space — retrieval is already space-scoped,
    so this is a second line of defense against cross-space citation leakage.
    """
    from apps.knowledge.models import Document, DocumentChunk

    for cit in citations_data:
        try:
            doc = Document.objects.get(id=cit.get("document_id"))
            if space is not None and doc.space_id is not None and doc.space_id != space.id:
                logger.warning(
                    "Skipping cross-space citation: doc %s (space %s) != session space %s",
                    doc.id, doc.space_id, space.id,
                )
                continue
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
                space=space,
            )
        except Exception as e:
            logger.warning("Citation save failed for message %s: %s", assistant_message.id, e)


# V4.0 DEFECT-001: SSE endpoint must be throttled — @api_view bypasses DEFAULT_THROTTLE_CLASSES
# Without this, authenticated users can call the RAG+LLM pipeline at unlimited rate,
# causing DashScope cost explosion (¥0.004/call × 1000/min = ¥4+/min per attacker).
class SendMessageRateThrottle(UserRateThrottle):
    rate = '10/minute'  # Normal users: 5-10 msg/hr; Active: 1-2 msg/min; Blocks cost explosion


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([SendMessageRateThrottle])
def send_message(request, session_id):
    """Send a message and get streaming response (SSE).

    TODO (SYS-V4.1-007): Add Redis session-level lock when migrating to
    gunicorn multi-worker deployment. Current runserver is single-threaded
    so concurrent SSE requests cannot race. Future: acquire Redis lock
    with key "chat:session_lock:{session_id}" before streaming, release
    in GeneratorExit/finally block.
    """
    serializer = ChatMessageRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    content = serializer.validated_data["content"]
    user = request.user
    language = getattr(user, "language_preference", "en")

    # V6.0: resolve the active space from the X-Space-Id header (if any). A new
    # session is created in this space; an existing session keeps its own space
    # (authoritative for isolation — you cannot move a session between spaces).
    request_space = resolve_request_space(request, require_perm=CHAT_ASK, required=False)

    # Get or create session with ownership verification
    try:
        session = ChatSession.objects.get(id=session_id, user=user)
        created = False
    except ChatSession.DoesNotExist:
        # Check if session exists under another user
        if ChatSession.objects.filter(id=session_id).exists():
            return Response(
                {"error": "Session not found or access denied"},
                status=403,
            )
        # Session doesn't exist at all; create it
        session = ChatSession.objects.create(
            id=session_id, user=user, title=content[:50],
            space=request_space or _default_space_for(user),
        )
        created = True

    # V6.0: a session is bound to one space. Backfill legacy null space, then
    # verify the user still has access to that space (e.g. membership revoked).
    space = session.space or request_space or _default_space_for(user)
    if session.space_id is None and space is not None:
        session.space = space
        session.save(update_fields=["space"])
    if space is not None and effective_space_role(user, space) is None:
        return Response(
            {"error": "You no longer have access to this space."},
            status=403,
        )

    # Update title if new or empty
    if created or not session.title:
        session.title = content[:50]
        session.save(update_fields=["title"])

    # Save user message
    Message.objects.create(session=session, role="user", content=content, space=space)

    # V3.5 HIGH-006: Sliding window aligned with frontend — 10 rounds (20 messages)
    # (was fixed 16 messages = 8 rounds, misaligned with frontend's 10-round default)
    WINDOW_ROUNDS = 10
    history = list(
        Message.objects.filter(session=session)
        .exclude(role="user", content=content)  # exclude the one we just saved
        .order_by("-created_at")[:WINDOW_ROUNDS * 2]
        .values_list("role", "content")
    )
    history.reverse()

    from apps.rag.pipeline import RAGPipeline

    pipeline = RAGPipeline()

    def event_stream():
        start_time = time.time()
        # V4.2 SYS-V4.2-014: SSE timeout limit — abort stream if total time exceeds 60s
        # Prevents runserver from being blocked indefinitely by DashScope failures.
        SSE_TIMEOUT_SECONDS = 60
        response_tokens = []
        citations_data = []
        client_disconnected = False

        try:
            for event in pipeline.retrieve_and_generate(
                query=content,
                user_profile=user,
                conversation_history=history,
                language=language,
                space_id=str(space.id) if space else None,  # V6.0 space isolation
            ):
                # H-04: Check if client disconnected
                # Django's StreamingHttpResponse will raise GeneratorExit
                # when the client closes the connection
                event_type = event.get("event")
                data = event.get("data", {})

                if event_type == "citations":
                    citations_data = data
                    yield "event: citations\n"
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                elif event_type == "token":
                    # V4.2 SYS-V4.2-014: Check SSE timeout — abort if stream exceeds limit
                    if time.time() - start_time > SSE_TIMEOUT_SECONDS:
                        logger.warning(
                            "SSE timeout for session %s — stream exceeded %ds",
                            session_id, SSE_TIMEOUT_SECONDS,
                        )
                        yield "event: error\n"
                        yield f"data: {json.dumps({'error': 'stream_timeout'}, ensure_ascii=False)}\n\n"
                        return

                    token = data.get("token", "")
                    response_tokens.append(token)
                    yield "event: token\n"
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

        except GeneratorExit:
            # H-04: Client disconnected during streaming
            client_disconnected = True
            logger.info("Client disconnected during stream for session %s", session_id)
            return
        except Exception as e:
            # V4.0 DEFECT-013: SSE error event must NOT leak str(e) to frontend
            logger.error("Stream error for session %s: %s", session_id, e, exc_info=True)
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'stream_error'}, ensure_ascii=False)}\n\n"
            return

        # H-04: Don't save message if client disconnected before streaming completed
        if client_disconnected:
            logger.info("Skipping message save — client disconnected for session %s", session_id)
            return

        # Save assistant message
        elapsed_ms = int((time.time() - start_time) * 1000)
        assistant_content = "".join(response_tokens)

        # H-03: Use tiktoken for accurate token count
        token_count = _estimate_token_count(assistant_content)

        assistant_message = Message.objects.create(
            session=session,
            role="assistant",
            content=assistant_content,
            token_count=token_count,
            model_used=pipeline.model_name,
            response_time_ms=elapsed_ms,
            retrieval_count=len(citations_data),
            space=space,  # V6.0 space isolation
        )

        # Save citations
        _save_citations(assistant_message, citations_data, space)

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
    message = get_object_or_404(Message, id=message_id, session__user=request.user)
    serializer = FeedbackSerializer(
        data={**request.data, "message": str(message.id)}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(space_id=message.space_id)  # V6.0: inherit message's space
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
