# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat views."""

import json
import logging
import time
from html import escape

from django.db import transaction
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

# V6.0: space isolation helpers.
from apps.spaces.permissions import (
    CHAT_ASK,
    effective_space_role,
    resolve_request_space,
)

from .models import ChatSession, ChatTurn, Citation, Feedback, Message
from .serializers import (
    ChatMessageRequestSerializer,
    ChatSessionSerializer,
    ChatTurnStatusSerializer,
    FeedbackSerializer,
    MessageSerializer,
)
from .services import (
    BeginTurnDisposition,
    InvalidTurnTransitionError,
    begin_chat_turn,
    transition_chat_turn,
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
    ordering = ('-is_pinned', '-updated_at')
    page_size = 20


# V3.5 HIGH-004: Cursor pagination for messages
class MessageCursorPagination(CursorPagination):
    ordering = '-created_at'
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
    ordering = ('-is_pinned', '-updated_at')

    def get_queryset(self):
        qs = ChatSession.objects.filter(user=self.request.user, is_active=True)
        # V6.0: when a space is active, the sidebar only shows that space's
        # sessions. Without a header (legacy client) all sessions are returned.
        space = resolve_request_space(self.request, required=False)
        if space is not None:
            qs = qs.filter(space=space)
        return qs.order_by('-is_pinned', '-updated_at')

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
        serializer.save(update_fields=list(serializer.validated_data))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def export_session(request, session_id):
    """Export one owned, currently accessible session as Markdown or safe HTML."""
    try:
        session = ChatSession.objects.prefetch_related("messages").get(
            id=session_id,
            user=request.user,
            is_active=True,
        )
    except ChatSession.DoesNotExist:
        from rest_framework.exceptions import NotFound
        raise NotFound("Session not found.") from None
    if session.space_id and effective_space_role(request.user, session.space) is None:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("You no longer have access to this space.")
    export_format = request.query_params.get("format", "markdown")
    if export_format not in {"markdown", "html"}:
        return Response({"detail": "format must be markdown or html"}, status=400)
    messages = list(session.messages.order_by("created_at"))
    if export_format == "markdown":
        lines = [f"# {session.title or 'Conversation'}", ""]
        for message in messages:
            lines.extend([f"## {message.role.title()}", "", message.content, ""])
        response = HttpResponse(
            "\n".join(lines),
            content_type="text/markdown; charset=utf-8",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="session-{session.id}.md"'
        )
        return response
    sections = "".join(
        f'<section class="message"><h2>{escape(message.role.title())}</h2>'
        f"<p>{escape(message.content).replace(chr(10), '<br>')}</p></section>"
        for message in messages
    )
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{escape(session.title or 'Conversation')}</title>"
        "<style>body{font:16px/1.5 system-ui;max-width:800px;margin:auto;padding:2rem}"
        "@media print{body{max-width:none;padding:0}}.message{break-inside:avoid}</style>"
        "</head><body>"
        f"<h1>{escape(session.title or 'Conversation')}</h1>{sections}</body></html>"
    )
    return HttpResponse(document, content_type="text/html; charset=utf-8")


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


def _streaming_response(events):
    response = StreamingHttpResponse(events, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _completed_turn_events(turn):
    """Replay one completed result in the legacy SSE protocol without running RAG."""

    message = turn.assistant_message
    citations = [
        {
            "document_id": str(citation.document_id),
            "document_title": citation.document.title,
            "page_number": citation.page_number,
            "score": citation.relevance_score,
            "quoted_text": citation.quoted_text,
        }
        for citation in message.citations.select_related("document").all()
    ]
    if citations:
        yield "event: citations\n"
        yield f"data: {json.dumps(citations, ensure_ascii=False)}\n\n"

    quality = {
        "score": message.confidence_score,
        "confidence": message.confidence_label,
        "needs_human_review": message.needs_human_review,
        "retrieval_mode": message.retrieval_mode,
        "retrieval_latency_ms": message.retrieval_latency_ms,
    }
    if any(value not in (None, "", False) for value in quality.values()):
        yield "event: quality\n"
        yield f"data: {json.dumps(quality, ensure_ascii=False)}\n\n"

    yield "event: token\n"
    yield f"data: {json.dumps({'token': message.content}, ensure_ascii=False)}\n\n"
    done_data = {
        "message_id": str(message.id),
        "session_id": str(turn.session_id),
        "model": turn.model_id or message.model_used or "",
        "turn_id": str(turn.id),
        "client_request_id": str(turn.client_request_id),
    }
    yield "event: done\n"
    yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def chat_turn_status(request, turn_id):
    """Return an owned Turn's safe recovery state without revealing other users."""

    turn = get_object_or_404(
        ChatTurn.objects.select_related(
            "space",
            "space__organization",
            "space__business_line",
            "assistant_message",
        ).prefetch_related("assistant_message__citations__document"),
        id=turn_id,
        user=request.user,
    )
    if turn.space_id and effective_space_role(request.user, turn.space) is None:
        from rest_framework.exceptions import NotFound

        raise NotFound("Turn not found.")
    return Response(ChatTurnStatusSerializer(turn, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([SendMessageRateThrottle])
def send_message(request, session_id):
    """Send a message and get streaming response (SSE).

    ChatTurn identity/idempotency is durable here. The Redis session lock and
    replayable SSE v2 envelope are intentionally deferred to Task 3B.
    """
    serializer = ChatMessageRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    content = serializer.validated_data["content"]
    client_request_id = serializer.validated_data["client_request_id"]
    answer_mode = serializer.validated_data["answer_mode"]
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

    begin_result = begin_chat_turn(
        user=user,
        session=session,
        space=space,
        client_request_id=client_request_id,
        content=content,
        answer_mode=answer_mode,
    )
    turn = begin_result.turn

    if begin_result.disposition == BeginTurnDisposition.CONFLICT:
        return Response(
            {
                "code": "client_request_conflict",
                "turn_id": str(turn.id),
            },
            status=status.HTTP_409_CONFLICT,
        )
    if begin_result.disposition == BeginTurnDisposition.IN_PROGRESS:
        return Response(
            {"code": "turn_in_progress", "turn_id": str(turn.id)},
            status=status.HTTP_409_CONFLICT,
        )
    if begin_result.disposition == BeginTurnDisposition.TERMINAL:
        return Response(
            {
                "code": "turn_not_retryable",
                "turn_id": str(turn.id),
                "turn_status": turn.status,
            },
            status=status.HTTP_409_CONFLICT,
        )
    if begin_result.disposition == BeginTurnDisposition.COMPLETED:
        if turn.assistant_message is None:
            return Response(
                {"code": "turn_result_unavailable", "turn_id": str(turn.id)},
                status=status.HTTP_409_CONFLICT,
            )
        return _streaming_response(_completed_turn_events(turn))

    question_message = turn.question_message

    # V3.5 HIGH-006: Sliding window aligned with frontend — 10 rounds (20 messages)
    # (was fixed 16 messages = 8 rounds, misaligned with frontend's 10-round default)
    window_rounds = 10
    history = list(
        Message.objects.filter(session=session)
        .exclude(pk=question_message.pk)
        .order_by("-created_at")[:window_rounds * 2]
        .values_list("role", "content")
    )
    history.reverse()

    def event_stream():
        start_time = time.time()
        # V4.2 SYS-V4.2-014: SSE timeout limit — abort stream if total time exceeds 60s
        # Prevents runserver from being blocked indefinitely by DashScope failures.
        sse_timeout_seconds = 60
        response_tokens = []
        citations_data = []
        quality_data = {}
        client_disconnected = False
        pipeline = None

        def record_invocation(
            invocation_status,
            *,
            error_code="",
            message=None,
            token_count=None,
        ):
            """Persist safe operational telemetry without breaking the stream."""
            try:
                from apps.chat.models import ModelInvocation

                ModelInvocation.objects.create(
                    session=session,
                    message=message,
                    question_message=question_message,
                    space=space,
                    model=getattr(pipeline, "model_name", turn.model_id),
                    status=invocation_status,
                    token_count=token_count,
                    latency_ms=int((time.time() - start_time) * 1000),
                    error_code=error_code,
                )
            except Exception:
                logger.exception(
                    "Could not persist model invocation telemetry for session %s",
                    session_id,
                )

        try:
            from apps.rag.pipeline import RAGPipeline

            pipeline = RAGPipeline()
            transition_chat_turn(
                turn,
                ChatTurn.STATUS_RETRIEVING,
                model_id=pipeline.model_name,
            )
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

                elif event_type == "quality":
                    quality_data = data
                    yield "event: quality\n"
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                elif event_type == "token":
                    # V4.2 SYS-V4.2-014: Check SSE timeout — abort if stream exceeds limit
                    if time.time() - start_time > sse_timeout_seconds:
                        logger.warning(
                            "SSE timeout for session %s — stream exceeded %ds",
                            session_id, sse_timeout_seconds,
                        )
                        record_invocation("timeout", error_code="stream_timeout")
                        transition_chat_turn(
                            turn,
                            ChatTurn.STATUS_FAILED,
                            error_code="stream_timeout",
                        )
                        yield "event: error\n"
                        yield f"data: {json.dumps({'error': 'stream_timeout'}, ensure_ascii=False)}\n\n"
                        return

                    token = data.get("token", "")
                    if turn.status != ChatTurn.STATUS_ANSWERING:
                        transition_chat_turn(
                            turn,
                            ChatTurn.STATUS_ANSWERING,
                            model_id=pipeline.model_name,
                        )
                    response_tokens.append(token)
                    yield "event: token\n"
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

        except GeneratorExit:
            # H-04: Client disconnected during streaming
            client_disconnected = True
            logger.info("Client disconnected during stream for session %s", session_id)
            record_invocation("cancelled", error_code="client_disconnected")
            try:
                transition_chat_turn(
                    turn,
                    ChatTurn.STATUS_FAILED,
                    error_code="client_disconnected",
                )
            except InvalidTurnTransitionError:
                logger.info("Turn %s was already terminal on disconnect", turn.id)
            return
        except Exception as e:
            # V4.0 DEFECT-013: SSE error event must NOT leak str(e) to frontend
            logger.error("Stream error for session %s: %s", session_id, e, exc_info=True)
            record_invocation("failure", error_code="stream_error")
            try:
                transition_chat_turn(
                    turn,
                    ChatTurn.STATUS_FAILED,
                    error_code="stream_error",
                )
            except InvalidTurnTransitionError:
                logger.exception("Could not mark Turn %s failed", turn.id)
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'stream_error'}, ensure_ascii=False)}\n\n"
            return

        # H-04: Don't save message if client disconnected before streaming completed
        if client_disconnected:
            logger.info("Skipping message save — client disconnected for session %s", session_id)
            return

        pre_save_status = turn.status
        try:
            # Persist the answer before declaring the Turn complete. Save failures
            # remain recoverable under the same client_request_id.
            with transaction.atomic():
                transition_chat_turn(turn, ChatTurn.STATUS_SAVING)
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
                    confidence_score=quality_data.get("score"),
                    confidence_label=quality_data.get("confidence", ""),
                    needs_human_review=quality_data.get("needs_human_review", False),
                    retrieval_mode=quality_data.get("retrieval_mode", ""),
                    retrieval_latency_ms=quality_data.get("retrieval_latency_ms"),
                    space=space,  # V6.0 space isolation
                )

                # Save citations
                _save_citations(assistant_message, citations_data, space)
                record_invocation(
                    "success",
                    message=assistant_message,
                    token_count=token_count,
                )
                ChatSession.objects.filter(pk=session.pk).update(updated_at=timezone.now())
                transition_chat_turn(
                    turn,
                    ChatTurn.STATUS_COMPLETED,
                    assistant_message=assistant_message,
                    model_id=pipeline.model_name,
                )
        except GeneratorExit:
            record_invocation("cancelled", error_code="client_disconnected")
            try:
                transition_chat_turn(
                    turn,
                    ChatTurn.STATUS_FAILED,
                    error_code="client_disconnected",
                )
            except InvalidTurnTransitionError:
                logger.info("Turn %s was already terminal on disconnect", turn.id)
            return
        except Exception:
            logger.exception("Answer persistence failed for Turn %s", turn.id)
            record_invocation("failure", error_code="answer_save_error")
            try:
                # The atomic save rolled the database back to this lifecycle
                # state; mirror it in memory before applying the failure state.
                turn.status = pre_save_status
                turn.assistant_message = None
                turn.completed_at = None
                transition_chat_turn(
                    turn,
                    ChatTurn.STATUS_FAILED,
                    error_code="answer_save_error",
                )
            except Exception:
                logger.exception("Could not mark Turn %s failed", turn.id)
            yield "event: error\n"
            yield f"data: {json.dumps({'error': 'answer_save_error'}, ensure_ascii=False)}\n\n"
            return

        done_data = {
            "message_id": str(assistant_message.id),
            "session_id": str(session.id),
            "model": pipeline.model_name,
            "turn_id": str(turn.id),
            "client_request_id": str(turn.client_request_id),
        }
        yield "event: done\n"
        yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"

    return _streaming_response(event_stream())


def _feedback_question_for(message):
    return (
        Message.objects.filter(
            session=message.session,
            role="user",
            created_at__lt=message.created_at,
        )
        .order_by("-created_at")
        .first()
    )


def _feedback_review_context(message):
    citations = [
        {
            "document_id": str(c.document_id),
            "document_title": c.document.title,
            "page_number": c.page_number,
            "relevance_score": c.relevance_score,
            "quoted_text": c.quoted_text,
        }
        for c in message.citations.select_related("document").all()
    ]
    question = _feedback_question_for(message)
    return {
        "question_message_id": str(question.id) if question else "",
        "question": question.content if question else "",
        "answer_message_id": str(message.id),
        "answer": message.content,
        "citations": citations,
        "retrieval_count": message.retrieval_count,
        "model": message.model_used or "",
        "answered_at": message.created_at.isoformat(),
    }


def _audit_feedback(request, feedback, action, *, result="success", reason=""):
    try:
        from apps.audit.views import create_audit_log

        create_audit_log(
            user=request.user,
            action=action,
            target_type="Feedback",
            target_id=feedback.id,
            request=request,
            organization_id=feedback.space.organization_id if feedback.space_id else None,
            business_line_id=feedback.space.business_line_id if feedback.space_id else None,
            space_id=feedback.space_id,
            result=result,
            details={
                "message_id": str(feedback.message_id),
                "feedback_type": feedback.feedback_type,
                "status": feedback.status,
                "flag_for_review": feedback.flag_for_review,
                "reason": reason,
            },
        )
    except Exception:
        logger.exception("Could not persist feedback audit event %s", action)


@api_view(["GET", "POST", "PUT", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def submit_feedback(request, message_id):
    """Create, read, update, or withdraw feedback on an assistant message."""
    message = get_object_or_404(Message, id=message_id, session__user=request.user)
    if message.role != "assistant":
        return Response(
            {"detail": "Feedback can only be submitted for assistant messages."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.method == "GET":
        feedback = Feedback.objects.filter(message=message, user=request.user).first()
        return Response(
            {"feedback": FeedbackSerializer(feedback).data if feedback else None}
        )

    if request.method == "DELETE":
        feedback = get_object_or_404(Feedback, message=message, user=request.user)
        if feedback.status not in {
            Feedback.STATUS_SUBMITTED,
            Feedback.STATUS_PENDING_REVIEW,
            Feedback.STATUS_WITHDRAWN,
        }:
            return Response(
                {"detail": "Feedback cannot be withdrawn after review has started."},
                status=status.HTTP_409_CONFLICT,
            )
        feedback.status = Feedback.STATUS_WITHDRAWN
        feedback.save(update_fields=["status", "updated_at"])
        _audit_feedback(request, feedback, "feedback_withdraw")
        return Response(FeedbackSerializer(feedback).data)

    serializer = FeedbackSerializer(data={**request.data, "message": str(message.id)})
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    data.pop("message", None)
    feedback_type = data.pop("feedback_type")
    flag_for_review = data.get("flag_for_review", False)
    status_value = (
        Feedback.STATUS_PENDING_REVIEW if flag_for_review else Feedback.STATUS_SUBMITTED
    )
    feedback, created = Feedback.objects.update_or_create(
        message=message,
        user=request.user,
        defaults={
            **data,
            "feedback_type": feedback_type,
            "status": status_value,
            "space_id": message.space_id,
            "review_context": _feedback_review_context(message),
        },
    )
    action = "feedback_submit" if created else "feedback_update"
    _audit_feedback(request, feedback, action)
    return Response(FeedbackSerializer(feedback).data)


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
