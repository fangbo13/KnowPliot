# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat views."""

import json
import logging
import time
from contextlib import suppress
from datetime import datetime, timedelta
from html import escape

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.rag.language import resolve_reply_language
from apps.rbac.capabilities import resolve_capabilities
from apps.spaces.generation_policy import (
    ANSWER_MODE_DEEP,
    GenerationPolicyNotReady,
    resolve_generation_policy,
)

# V6.0: space isolation helpers.
from apps.spaces.permissions import (
    CHAT_ASK,
    CHAT_EXPORT,
    CHAT_SHARE,
    CHAT_VIEW_HISTORY,
    DOCUMENT_DOWNLOAD,
    effective_space_role,
    ensure_workspace_writable,
    has_space_permission,
    resolve_request_space,
    spaces_with_permission,
)

from .coordination import (
    CoordinationUnavailableError,
    RedisSessionLease,
    create_redis_client,
    lease_exists,
)
from .generation import NeverCancelled, iter_chat_turn
from .metrics import ChatStreamMetrics, merge_turn_metrics
from .models import ChatSession, ChatTurn, Citation, ConversationShare, Feedback, Message
from .serializers import (
    BranchMessageRequestSerializer,
    ChatMessageRequestSerializer,
    ChatSessionSerializer,
    ChatTurnStatusSerializer,
    ConversationShareRequestSerializer,
    ConversationShareSerializer,
    FeedbackSerializer,
    MessageSerializer,
)
from .services import (
    ACTIVE_TURN_STATUSES,
    BeginTurnDisposition,
    ChatTurnScopeError,
    InvalidTurnTransitionError,
    SessionResolutionDisposition,
    begin_chat_turn,
    resolve_chat_session,
    transition_chat_turn,
)
from .stream_events import (
    EventStoreUnavailableError,
    ManagedStream,
    RedisTurnEventStore,
    converge_stale_turn,
)
from .v3_views import accept_chat_turn_v3

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
    ordering = ('-is_pinned', '-updated_at', '-id')
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
    ordering = ('-is_pinned', '-updated_at', '-id')

    TIME_FILTERS = {"all", "today", "this_week", "this_month", "older"}
    STATUS_FILTERS = {
        "all", "partial", "recovering", "recovered", "failed", "terminal"
    }

    def get_queryset(self):
        qs = ChatSession.objects.filter(user=self.request.user, is_active=True)
        # When a space is active, show only that space's permitted history.
        # Legacy clients without a header still see only currently permitted
        # spaces plus their pre-space sessions.
        space = resolve_request_space(
            self.request,
            require_perm=CHAT_VIEW_HISTORY,
            required=False,
        )
        if space is not None:
            qs = qs.filter(space=space)
        else:
            qs = qs.filter(
                Q(space__isnull=True)
                | Q(space__in=spaces_with_permission(self.request.user, CHAT_VIEW_HISTORY))
            )

        query = self.request.query_params.get("q", "").strip()
        time_filter = self.request.query_params.get("time", "all").strip().lower()
        status_filter = self.request.query_params.get("status", "all").strip().lower()
        if time_filter not in self.TIME_FILTERS:
            raise ValidationError({"time": "Unsupported history time filter."})
        if status_filter not in self.STATUS_FILTERS:
            raise ValidationError({"status": "Unsupported recovery status filter."})
        if query:
            matching_message = Message.objects.filter(
                session_id=OuterRef("pk"),
                content__icontains=query,
            )
            qs = qs.annotate(matches_message=Exists(matching_message)).filter(
                Q(title__icontains=query) | Q(matches_message=True)
            )

        now = timezone.localtime()
        day_start = timezone.make_aware(datetime.combine(now.date(), datetime.min.time()))
        if time_filter == "today":
            qs = qs.filter(updated_at__gte=day_start)
        elif time_filter == "this_week":
            qs = qs.filter(updated_at__gte=day_start - timedelta(days=now.weekday()))
        elif time_filter == "this_month":
            month_start = day_start.replace(day=1)
            qs = qs.filter(updated_at__gte=month_start)
        elif time_filter == "older":
            qs = qs.filter(updated_at__lt=day_start - timedelta(days=30))

        latest_turn = ChatTurn.objects.filter(session=OuterRef("pk")).order_by("-started_at")
        qs = qs.annotate(
            latest_turn_status=Subquery(latest_turn.values("status")[:1]),
            latest_turn_attempt_count=Subquery(latest_turn.values("attempt_count")[:1]),
            latest_turn_assistant_id=Subquery(latest_turn.values("assistant_message_id")[:1]),
        )
        active_statuses = [
            ChatTurn.STATUS_ACCEPTED,
            ChatTurn.STATUS_RETRIEVING,
            ChatTurn.STATUS_REASONING,
            ChatTurn.STATUS_ANSWERING,
            ChatTurn.STATUS_SAVING,
        ]
        if status_filter == "recovering":
            qs = qs.filter(latest_turn_status__in=active_statuses)
        elif status_filter == "recovered":
            qs = qs.filter(
                latest_turn_status=ChatTurn.STATUS_COMPLETED,
                latest_turn_attempt_count__gt=1,
            )
        elif status_filter == "partial":
            qs = qs.filter(
                latest_turn_status__in=[ChatTurn.STATUS_FAILED, ChatTurn.STATUS_CANCELLED],
                latest_turn_assistant_id__isnull=False,
            )
        elif status_filter == "failed":
            qs = qs.filter(
                latest_turn_status__in=[ChatTurn.STATUS_FAILED, ChatTurn.STATUS_CANCELLED],
                latest_turn_assistant_id__isnull=True,
            )
        elif status_filter == "terminal":
            qs = qs.filter(
                Q(latest_turn_status__isnull=True)
                | Q(
                    latest_turn_status=ChatTurn.STATUS_COMPLETED,
                    latest_turn_attempt_count__lte=1,
                )
            )
        return qs.order_by('-is_pinned', '-updated_at', '-id')

    def perform_create(self, serializer):
        space = resolve_request_space(self.request, require_perm=CHAT_ASK, required=False) \
            or _default_space_for(self.request.user)
        ensure_workspace_writable(space)
        serializer.save(user=self.request.user, space=space)


class ChatSessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update (rename), and delete a chat session."""

    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user).filter(
            Q(space__isnull=True)
            | Q(space__in=spaces_with_permission(self.request.user, CHAT_VIEW_HISTORY))
        )

    def perform_update(self, serializer):
        """Only update title field — preserve updated_at so session stays in
        its original position in the sidebar list instead of jumping to the top."""
        serializer.save(update_fields=list(serializer.validated_data))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def export_session(request, session_id):
    """Export one owned, currently accessible session as Markdown or safe HTML."""
    try:
        session = ChatSession.objects.select_related("space").get(
            id=session_id,
            user=request.user,
            is_active=True,
        )
    except ChatSession.DoesNotExist:
        from rest_framework.exceptions import NotFound
        raise NotFound("Session not found.") from None
    if session.space_id and not has_space_permission(
        request.user,
        session.space,
        CHAT_EXPORT,
    ):
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


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def branch_from_message(request, message_id):
    """Create an idempotent conversation branch through one owned message."""
    source_message = get_object_or_404(
        Message.objects.select_related("session", "space"),
        pk=message_id,
        session__user=request.user,
        session__is_active=True,
    )
    source_session = source_message.session
    space = source_session.space
    if space is not None:
        ensure_workspace_writable(space)
    if (
        space is None
        or effective_space_role(request.user, space) is None
        or not has_space_permission(request.user, space, CHAT_ASK)
        or not has_space_permission(request.user, space, CHAT_VIEW_HISTORY)
    ):
        return Response({"code": "space_access_denied"}, status=status.HTTP_403_FORBIDDEN)

    payload = BranchMessageRequestSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    request_id = payload.validated_data["client_request_id"]
    existing = ChatSession.objects.filter(
        user=request.user,
        branch_request_id=request_id,
    ).first()
    if existing is not None:
        return Response(ChatSessionSerializer(existing).data, status=status.HTTP_200_OK)

    with transaction.atomic():
        title = payload.validated_data.get("title", "").strip()
        branch, created = ChatSession.objects.get_or_create(
            user=request.user,
            branch_request_id=request_id,
            defaults={
                "space": space,
                "title": title or f"Branch · {source_session.title or 'Conversation'}",
                "branched_from_message": source_message,
            },
        )
        if not created:
            return Response(ChatSessionSerializer(branch).data, status=status.HTTP_200_OK)
        copied = []
        source_messages = list(
            source_session.messages.filter(created_at__lte=source_message.created_at)
            .filter(
                Q(role__in=["user", "system"])
                | Q(is_current_version=True)
                | Q(pk=source_message.pk)
            )
            .prefetch_related("citations")
        )
        source_messages.sort(
            key=lambda item: (
                item.created_at,
                {"user": 0, "assistant": 1, "system": 2}.get(item.role, 3),
                str(item.id),
            )
        )
        for message in source_messages:
            copied.append(Message(
                session=branch,
                space=space,
                role=message.role,
                content=message.content,
                token_count=message.token_count,
                model_used=message.model_used,
                response_time_ms=message.response_time_ms,
                retrieval_count=message.retrieval_count,
                confidence_score=message.confidence_score,
                confidence_label=message.confidence_label,
                needs_human_review=message.needs_human_review,
                retrieval_mode=message.retrieval_mode,
                retrieval_latency_ms=message.retrieval_latency_ms,
                version_number=1,
                is_current_version=True,
            ))
            if message.pk == source_message.pk:
                break
        Message.objects.bulk_create(copied)
        citation_copies = []
        for source, destination in zip(source_messages, copied, strict=False):
            for citation in source.citations.all():
                citation_copies.append(Citation(
                    space=space,
                    message=destination,
                    document_id=citation.document_id,
                    chunk_id=citation.chunk_id,
                    relevance_score=citation.relevance_score,
                    page_number=citation.page_number,
                    quoted_text=citation.quoted_text,
                ))
            if source.pk == source_message.pk:
                break
        Citation.objects.bulk_create(citation_copies)

    try:
        from apps.audit.views import create_audit_log
        create_audit_log(
            request.user,
            "chat_session_branch",
            "ChatSession",
            branch.id,
            details={
                "source_session_id": str(source_session.id),
                "source_message_id": str(source_message.id),
            },
            request=request,
            space_id=space.id,
            result="success",
        )
    except Exception:
        logger.warning("Could not write conversation branch audit", exc_info=True)
    return Response(ChatSessionSerializer(branch).data, status=status.HTTP_201_CREATED)


class ChatSessionMessagesView(generics.ListAPIView):
    """List messages in a session."""

    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    # V3.5 HIGH-004: Enable cursor pagination for messages + N+1 fix via prefetch_related
    pagination_class = MessageCursorPagination

    def get_queryset(self):
        session = get_object_or_404(
            ChatSession.objects.select_related("space"),
            id=self.kwargs["session_id"],
            user=self.request.user,
            is_active=True,
        )
        if session.space_id and not has_space_permission(
            self.request.user,
            session.space,
            CHAT_VIEW_HISTORY,
        ):
            raise PermissionDenied("You no longer have access to this space.")
        # V3.5 HIGH-004: prefetch_related eliminates N+1 citation queries
        queryset = Message.objects.filter(
            session=session,
        )
        if self.request.query_params.get("include_versions") != "true":
            queryset = queryset.exclude(role="assistant", is_current_version=False)
        return queryset.select_related("assistant_turn").order_by("created_at").prefetch_related(
            "citations__document",
            "citations__space__organization",
            "citations__space__business_line",
        )


def _safe_shared_text(value, limit=12000):
    return " ".join(strip_tags(value or "").split())[:limit]


def _audit_chat_action(request, action, target_type, target_id, *, space, details=None):
    try:
        from apps.audit.views import create_audit_log
        create_audit_log(
            request.user,
            action,
            target_type,
            target_id,
            details=details or {},
            request=request,
            space_id=space.id if space else None,
            result="success",
        )
    except Exception:
        logger.warning("Could not write %s audit", action, exc_info=True)


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def conversation_share_collection(request, session_id):
    session = get_object_or_404(
        ChatSession.objects.select_related("space__organization"),
        pk=session_id,
        user=request.user,
        is_active=True,
    )
    space = session.space
    if (
        space is None
        or effective_space_role(request.user, space) is None
        or not has_space_permission(request.user, space, CHAT_SHARE)
    ):
        return Response({"code": "share_not_allowed"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        shares = session.shares.filter(owner=request.user)
        return Response(ConversationShareSerializer(shares, many=True).data)

    ensure_workspace_writable(space)
    payload = ConversationShareRequestSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    request_id = payload.validated_data["client_request_id"]
    share, created = ConversationShare.objects.get_or_create(
        owner=request.user,
        client_request_id=request_id,
        defaults={
            "session": session,
            "organization": space.organization,
        },
    )
    if share.session_id != session.id:
        return Response(
            {"code": "client_request_conflict"},
            status=status.HTTP_409_CONFLICT,
        )
    if created:
        _audit_chat_action(
            request,
            "chat_share_create",
            "ConversationShare",
            share.id,
            space=space,
            details={"session_id": str(session.id)},
        )
    return Response(
        ConversationShareSerializer(share).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def revoke_conversation_share(request, share_id):
    share = get_object_or_404(
        ConversationShare.objects.select_related("session__space"),
        pk=share_id,
        owner=request.user,
    )
    space = share.session.space
    if share.revoked_at is None:
        share.revoked_at = timezone.now()
        share.save(update_fields=["revoked_at", "updated_at"])
        _audit_chat_action(
            request,
            "chat_share_revoke",
            "ConversationShare",
            share.id,
            space=space,
        )
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def view_conversation_share(request, token):
    share = get_object_or_404(
        ConversationShare.objects.select_related("session__space__organization"),
        token=token,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
        session__is_active=True,
    )
    session = share.session
    space = session.space
    if (
        space is None
        or share.organization_id != space.organization_id
        or effective_space_role(request.user, space) is None
        or not has_space_permission(request.user, space, CHAT_ASK)
    ):
        raise Http404

    messages = (
        session.messages.exclude(role="assistant", is_current_version=False)
        .order_by("created_at")
        .prefetch_related("citations__document", "citations__space")
    )
    serialized = MessageSerializer(messages, many=True, context={"request": request}).data
    safe_messages = []
    for message in serialized:
        safe_message = dict(message)
        safe_message["content"] = _safe_shared_text(message.get("content"))
        safe_messages.append(safe_message)
    return Response({
        "id": str(share.id),
        "token": str(share.token),
        "title": _safe_shared_text(session.title, 255),
        "expires_at": share.expires_at,
        "read_only": True,
        "messages": safe_messages,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def citation_source(request, citation_id):
    citation = get_object_or_404(
        Citation.objects.select_related("space__organization", "document"),
        pk=citation_id,
        message__session__is_active=True,
    )
    space = citation.space
    if space is None or effective_space_role(request.user, space) is None:
        raise Http404
    if not has_space_permission(request.user, space, DOCUMENT_DOWNLOAD):
        return Response({"code": "source_access_denied"}, status=status.HTTP_403_FORBIDDEN)
    return Response({
        "source_id": str(citation.id),
        "document_id": str(citation.document_id),
        "title": citation.document.title,
        "page_number": citation.page_number,
        "snippet": _safe_shared_text(citation.quoted_text, 280),
    })


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
        except Exception:
            logger.warning(
                "citation_save_failed message_id=%s code=persistence_error",
                assistant_message.id,
            )


# V4.0 DEFECT-001: SSE endpoint must be throttled — @api_view bypasses DEFAULT_THROTTLE_CLASSES
# Without this, authenticated users can call the RAG+LLM pipeline at unlimited rate,
# causing DashScope cost explosion (¥0.004/call × 1000/min = ¥4+/min per attacker).
class SendMessageRateThrottle(UserRateThrottle):
    rate = '10/minute'  # Normal users: 5-10 msg/hr; Active: 1-2 msg/min; Blocks cost explosion


def _stream_v2_enabled(protocol_version):
    """Negotiate v2 only when both the server flag and client opt-in agree."""

    return bool(getattr(settings, "CHAT_STREAM_V2", False)) and protocol_version == 2


def _request_generation_policy(
    space,
    requested_mode,
    requested_thinking_enabled=False,
):
    """Resolve governed fast policy even while the deep rollout stays off."""

    return resolve_generation_policy(
        space,
        requested_mode,
        requested_thinking_enabled,
    )


def _turn_execution_snapshot(turn):
    """One safe snapshot shared by live meta, replay, status, and history."""

    return {
        "requested_answer_mode": turn.requested_answer_mode,
        "answer_mode": turn.answer_mode,
        "requested_thinking_enabled": turn.requested_thinking_enabled,
        "thinking_enabled": turn.thinking_enabled,
        "thinking_snapshot_known": turn.thinking_snapshot_known,
        "thinking_budget": turn.thinking_budget,
        "model_id": turn.model_id,
        "policy_fallback_code": turn.policy_fallback_code,
    }


def _streaming_response(events, *, turn=None):
    response = StreamingHttpResponse(events, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    if turn is not None:
        response["X-Chat-Turn-Id"] = str(turn.id)
        response["X-Chat-Client-Request-Id"] = str(turn.client_request_id)
    return response


def _turn_response(data, *, response_status, turn):
    return Response(
        data,
        status=response_status,
        headers={
            "X-Chat-Turn-Id": str(turn.id),
            "X-Chat-Client-Request-Id": str(turn.client_request_id),
        },
    )


def _mark_turn_failed(turn, error_code):
    """Best-effort safe failure convergence for an already accepted Turn."""

    try:
        transition_chat_turn(
            turn,
            ChatTurn.STATUS_FAILED,
            error_code=error_code,
        )
    except InvalidTurnTransitionError:
        logger.info("Turn %s was already terminal", turn.id)
    except Exception:
        logger.error(
            "turn_failure_state_persist_failed turn_id=%s code=persistence_error",
            turn.id,
        )


def _checkpoint_turn_sequence(turn_id, sequence):
    ChatTurn.objects.filter(
        pk=turn_id,
        last_event_seq__lt=sequence,
    ).update(last_event_seq=sequence)


def _record_turn_metrics(turn, *, increments=(), **values):
    """Best-effort safe telemetry must never change Turn control flow."""

    try:
        merge_turn_metrics(turn, increments=increments, **values)
    except Exception:
        logger.warning(
            "turn_metrics_persist_failed turn_id=%s code=persistence_error",
            turn.id,
        )


def _owned_recovery_turn(request, turn_id):
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
    required_permission = (
        CHAT_ASK if turn.status in ACTIVE_TURN_STATUSES else CHAT_VIEW_HISTORY
    )
    if turn.space_id and not has_space_permission(
        request.user,
        turn.space,
        required_permission,
    ):
        from rest_framework.exceptions import NotFound

        raise NotFound("Turn not found.")

    try:
        client = create_redis_client()
    except CoordinationUnavailableError:
        _record_turn_metrics(
            turn,
            increments=("recovery_count",),
            recovery_count=1,
        )
        return turn, None
    converge_stale_turn(
        turn,
        lease_exists=lambda session_id: lease_exists(client, session_id),
        now=timezone.now(),
    )
    _record_turn_metrics(
        turn,
        increments=("recovery_count",),
        recovery_count=1,
    )
    return turn, client


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


def _completed_turn_events_v2(turn, store):
    """Replay or safely reconstruct a completed Turn in the v2 envelope."""

    replay = store.replay(after=0)
    if replay and replay[-1].name == "done":
        return replay

    message = turn.assistant_message
    if not replay:
        events = [
            store.append(
                "meta",
                {
                    "turn_id": str(turn.id),
                    "session_id": str(turn.session_id),
                    "client_request_id": str(turn.client_request_id),
                    "protocol_version": 2,
                    **_turn_execution_snapshot(turn),
                },
            )
        ]
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
            events.append(store.append("citations", citations))
        quality = {
            "score": message.confidence_score,
            "confidence": message.confidence_label,
            "needs_human_review": message.needs_human_review,
            "retrieval_mode": message.retrieval_mode,
            "retrieval_latency_ms": message.retrieval_latency_ms,
        }
        if any(value not in (None, "", False) for value in quality.values()):
            events.append(store.append("quality", quality))
        events.append(store.append("answer_delta", {"text": message.content}))
    else:
        events = replay
    events.append(
        store.append(
            "usage",
            {
                "output_tokens": message.token_count,
                "latency_ms": message.response_time_ms,
            },
        )
    )
    events.append(
        store.append(
            "done",
            {
                "message_id": str(message.id),
                "session_id": str(turn.session_id),
                "model": turn.model_id or message.model_used or "",
                "turn_id": str(turn.id),
                "client_request_id": str(turn.client_request_id),
            },
            terminal=True,
        )
    )
    return events


def _conversation_history(session, question_message, window_rounds=10):
    history = list(
        Message.objects.filter(session=session)
        .exclude(pk=question_message.pk)
        .order_by("-created_at")[: window_rounds * 2]
        .values_list("role", "content")
    )
    history.reverse()
    return history


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def chat_turn_status(request, turn_id):
    """Return an owned Turn's safe recovery state without revealing other users."""

    turn, _client = _owned_recovery_turn(request, turn_id)
    return Response(ChatTurnStatusSerializer(turn, context={"request": request}).data)


def _replay_cursor(request):
    value = request.query_params.get("after")
    if value in (None, ""):
        value = request.headers.get("Last-Event-ID", "0")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def chat_turn_events(request, turn_id):
    """Replay safe v2 events for an owned, currently accessible Turn."""

    turn, client = _owned_recovery_turn(request, turn_id)
    if client is None:
        return Response(
            {"code": "event_store_unavailable", "turn_id": str(turn.id)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    store = RedisTurnEventStore(client, turn.id)
    try:
        events = store.replay(after=_replay_cursor(request))
    except EventStoreUnavailableError:
        return Response(
            {"code": "event_store_unavailable", "turn_id": str(turn.id)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    response = _streaming_response(
        (event.to_sse() for event in events),
        turn=turn,
    )
    response["X-Chat-Turn-Status"] = turn.status
    return response


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([SendMessageRateThrottle])
def send_message(request, session_id=None, message_id=None):
    """Send a message and get streaming response (SSE).

    ChatTurn identity/idempotency, the renewable Redis session lease, and the
    replayable SSE v2 envelope are coordinated by this endpoint.
    """
    request_started_at = time.monotonic()
    regenerate_source = None
    question_message_override = None
    serializer_data = request.data
    if message_id is not None:
        regenerate_source = get_object_or_404(
            Message.objects.select_related("session", "space"),
            pk=message_id,
            role="assistant",
            session__user=request.user,
            session__is_active=True,
        )
        regenerate_space = regenerate_source.space or regenerate_source.session.space
        if (
            regenerate_space is None
            or not has_space_permission(request.user, regenerate_space, CHAT_ASK)
            or not has_space_permission(
                request.user,
                regenerate_space,
                CHAT_VIEW_HISTORY,
            )
        ):
            return Response(
                {"code": "space_access_denied"},
                status=status.HTTP_403_FORBIDDEN,
            )
        source_turn = getattr(regenerate_source, "assistant_turn", None)
        question_message_override = source_turn.question_message if source_turn else (
            Message.objects.filter(
                session=regenerate_source.session,
                role="user",
                created_at__lte=regenerate_source.created_at,
            ).order_by("-created_at").first()
        )
        if question_message_override is None:
            return Response(
                {"code": "question_unavailable"},
                status=status.HTTP_409_CONFLICT,
            )
        session_id = regenerate_source.session_id
        serializer_data = request.data.copy()
        serializer_data["content"] = question_message_override.content

    serializer = ChatMessageRequestSerializer(data=serializer_data)
    serializer.is_valid(raise_exception=True)

    content = serializer.validated_data["content"]
    client_request_id = serializer.validated_data["client_request_id"]
    requested_answer_mode = serializer.validated_data["answer_mode"]
    requested_thinking_enabled = serializer.validated_data["thinking_enabled"]
    protocol_version = serializer.validated_data["protocol_version"]
    if protocol_version == 3 and not settings.CHAT_STREAM_V3:
        return Response(
            {"code": "stream_protocol_unavailable"},
            status=status.HTTP_409_CONFLICT,
        )
    use_v2 = _stream_v2_enabled(protocol_version)
    user = request.user
    # Post-V3 Part 4: the AI reply language is resolved after the session's
    # space is known (so the space default_language fallback can apply), via
    # apps.rag.language.resolve_reply_language(content, user, space).

    # V6.0: resolve the active space from the X-Space-Id header (if any). A new
    # session is created in this space; an existing session keeps its own space
    # (authoritative for isolation — you cannot move a session between spaces).
    request_space = resolve_request_space(request, require_perm=CHAT_ASK, required=False)

    session_result = resolve_chat_session(
        user=user,
        session_id=session_id,
        title=content[:50],
        request_space=request_space,
        fallback_space_factory=lambda: _default_space_for(user),
    )
    if session_result.disposition == SessionResolutionDisposition.ACCESS_DENIED:
        return Response(
            {"error": "Session not found or access denied"},
            status=403,
        )
    if session_result.disposition == SessionResolutionDisposition.SCOPE_UNAVAILABLE:
        return Response(
            {"code": "session_scope_unavailable"},
            status=status.HTTP_409_CONFLICT,
        )

    session = session_result.session
    if session is None or session.user_id != user.pk:
        return Response(
            {"error": "Session not found or access denied"},
            status=403,
        )
    created = session_result.disposition == SessionResolutionDisposition.CREATED
    space = session.space
    # Post-V3 Part 4: resolve AI reply language — query-language detection
    # (primary) -> user.language_preference override -> space.default_language
    # fallback. KB content language never drives the reply language.
    language = resolve_reply_language(content, user, space)
    if space is not None and (
        effective_space_role(user, space) is None
        or not has_space_permission(user, space, CHAT_ASK)
    ):
        return Response(
            {"error": "You no longer have access to this space."},
            status=403,
        )

    capability_payload = None
    if requested_answer_mode == ANSWER_MODE_DEEP or requested_thinking_enabled:
        capability_payload = resolve_capabilities(user, space_id=space.id)
    if requested_answer_mode == ANSWER_MODE_DEEP:
        if "chat.deep" not in capability_payload["capabilities"]:
            return Response(
                {"code": "answer_mode_not_allowed"},
                status=status.HTTP_403_FORBIDDEN,
            )
    if requested_thinking_enabled:
        if "chat.thinking" not in capability_payload["capabilities"]:
            return Response(
                {"code": "thinking_not_allowed"},
                status=status.HTTP_403_FORBIDDEN,
            )

    try:
        generation_policy = _request_generation_policy(
            space,
            requested_answer_mode,
            requested_thinking_enabled,
        )
    except GenerationPolicyNotReady:
        return Response(
            {"code": "model_policy_not_ready"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Update title if new or empty
    if created or not session.title:
        session.title = content[:50]
        session.save(update_fields=["title"])

    try:
        begin_result = begin_chat_turn(
            session=session,
            client_request_id=client_request_id,
            content=content,
            requested_answer_mode=requested_answer_mode,
            answer_mode=generation_policy.answer_mode,
            requested_thinking_enabled=requested_thinking_enabled,
            thinking_enabled=generation_policy.thinking_enabled,
            thinking_budget=generation_policy.thinking_budget,
            policy_fallback_code=generation_policy.fallback_code,
            model_id=generation_policy.model_id,
            protocol_version=protocol_version,
            question_message=question_message_override,
        )
    except ChatTurnScopeError:
        return Response(
            {"code": "session_scope_unavailable"},
            status=status.HTTP_409_CONFLICT,
        )
    turn = begin_result.turn
    _record_turn_metrics(
        turn,
        idempotency_disposition=begin_result.disposition.value,
        idempotency_rollout_enabled=bool(settings.CHAT_TURN_IDEMPOTENCY),
        effective_answer_mode=turn.answer_mode,
        thinking_enabled=turn.thinking_enabled,
        policy_fallback_code=turn.policy_fallback_code,
    )

    if begin_result.disposition == BeginTurnDisposition.CONFLICT:
        return _turn_response(
            {
                "code": "client_request_conflict",
                "turn_id": str(turn.id),
            },
            response_status=status.HTTP_409_CONFLICT,
            turn=turn,
        )
    if protocol_version == 3 and begin_result.disposition in {
        BeginTurnDisposition.CREATED,
        BeginTurnDisposition.RETRY,
        BeginTurnDisposition.IN_PROGRESS,
        BeginTurnDisposition.COMPLETED,
    }:
        return accept_chat_turn_v3(
            turn,
            disposition=begin_result.disposition,
        )
    if begin_result.disposition == BeginTurnDisposition.IN_PROGRESS:
        return _turn_response(
            {"code": "turn_in_progress", "turn_id": str(turn.id)},
            response_status=status.HTTP_409_CONFLICT,
            turn=turn,
        )
    if begin_result.disposition == BeginTurnDisposition.TERMINAL:
        return _turn_response(
            {
                "code": "turn_not_retryable",
                "turn_id": str(turn.id),
                "turn_status": turn.status,
            },
            response_status=status.HTTP_409_CONFLICT,
            turn=turn,
        )
    if begin_result.disposition == BeginTurnDisposition.COMPLETED:
        if turn.assistant_message is None:
            return _turn_response(
                {"code": "turn_result_unavailable", "turn_id": str(turn.id)},
                response_status=status.HTTP_409_CONFLICT,
                turn=turn,
            )
        if use_v2:
            try:
                client = create_redis_client()
                store = RedisTurnEventStore(
                    client,
                    turn.id,
                    initial_sequence=turn.last_event_seq,
                    checkpoint=lambda sequence: _checkpoint_turn_sequence(
                        turn.id,
                        sequence,
                    ),
                )
                events = _completed_turn_events_v2(turn, store)
            except (EventStoreUnavailableError, CoordinationUnavailableError):
                return _turn_response(
                    {
                        "code": "event_store_unavailable",
                        "turn_id": str(turn.id),
                        "retryable": True,
                    },
                    response_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    turn=turn,
                )
            return _streaming_response(
                (event.to_sse() for event in events),
                turn=turn,
            )
        return _streaming_response(_completed_turn_events(turn), turn=turn)

    question_message = turn.question_message

    try:
        client = create_redis_client()
        lease = RedisSessionLease(client, session.id)
        acquired = lease.acquire()
    except CoordinationUnavailableError:
        _mark_turn_failed(turn, "coordination_unavailable")
        return _turn_response(
            {
                "code": "coordination_unavailable",
                "turn_id": str(turn.id),
                "retryable": True,
            },
            response_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            turn=turn,
        )
    if not acquired:
        _mark_turn_failed(turn, "session_busy")
        return _turn_response(
            {
                "code": "session_busy",
                "turn_id": str(turn.id),
                "retryable": True,
            },
            response_status=status.HTTP_409_CONFLICT,
            turn=turn,
        )

    if begin_result.disposition == BeginTurnDisposition.RETRY:
        try:
            RedisTurnEventStore(client, turn.id).clear_events()
        except EventStoreUnavailableError:
            _mark_turn_failed(turn, "coordination_unavailable")
            with suppress(CoordinationUnavailableError):
                lease.release()
            return _turn_response(
                {
                    "code": "coordination_unavailable",
                    "turn_id": str(turn.id),
                    "retryable": True,
                },
                response_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                turn=turn,
            )

    event_store = None
    meta_event = None
    if use_v2:
        event_store = RedisTurnEventStore(
            client,
            turn.id,
            initial_sequence=turn.last_event_seq,
            checkpoint=lambda sequence: _checkpoint_turn_sequence(turn.id, sequence),
        )
        try:
            meta_event = event_store.append(
                "meta",
                {
                    "turn_id": str(turn.id),
                    "session_id": str(session.id),
                    "client_request_id": str(turn.client_request_id),
                    "protocol_version": 2,
                    **_turn_execution_snapshot(turn),
                },
            )
        except EventStoreUnavailableError:
            _mark_turn_failed(turn, "coordination_unavailable")
            with suppress(CoordinationUnavailableError):
                lease.release()
            return _turn_response(
                {
                    "code": "coordination_unavailable",
                    "turn_id": str(turn.id),
                    "retryable": True,
                },
                response_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                turn=turn,
            )
    try:
        lease.start_renewal()
    except CoordinationUnavailableError:
        _mark_turn_failed(turn, "coordination_unavailable")
        with suppress(CoordinationUnavailableError):
            lease.release()
        return _turn_response(
            {
                "code": "coordination_unavailable",
                "turn_id": str(turn.id),
                "retryable": True,
            },
            response_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            turn=turn,
        )

    def v2_event(name, data, *, terminal=False):
        return event_store.append(name, data, terminal=terminal).to_sse()

    def terminal_error(code):
        if use_v2:
            return event_store.append_error(code).to_sse()
        return (
            "event: error\n"
            f"data: {json.dumps({'error': code}, ensure_ascii=False)}\n\n"
        )

    def persist_terminal_event(code):
        if event_store is None:
            return
        try:
            event_store.append_error(code)
        except Exception:
            logger.warning("Could not persist terminal event for Turn %s", turn.id)

    stream_metrics = ChatStreamMetrics(started_at=request_started_at)

    def event_stream():
        start_time = time.time()
        # V4.2 SYS-V4.2-014: SSE timeout limit — abort stream if total time exceeds 60s
        # Prevents runserver from being blocked indefinitely by DashScope failures.
        sse_timeout_seconds = 60
        if meta_event is not None:
            # First application event: history/RAG/model work has not started.
            stream_metrics.mark_first_event(time.monotonic())
            yield meta_event.to_sse()

        shared_events = iter_chat_turn(
            turn.id,
            cancellation_probe=NeverCancelled(),
            _turn=turn,
            _lease=lease,
            _lease_preacquired=True,
            _lease_started=True,
            _release_lease=False,
            _history_loader=_conversation_history,
            _citation_saver=_save_citations,
            _token_counter=_estimate_token_count,
            _regenerate_source=regenerate_source,
            _started_at=start_time,
            _stream_metrics=stream_metrics,
            _deadline_seconds=sse_timeout_seconds,
            _emit_transport_events=True,
            _query=content,
            _language=language,
        )
        try:
            for domain_event in shared_events:
                if domain_event.name == "error":
                    code = domain_event.data.get("code", "stream_error")
                    if code in {"stream_error", "answer_save_error"}:
                        logger.error(
                            "chat_stream_failed session_id=%s turn_id=%s code=%s",
                            session_id,
                            turn.id,
                            code,
                        )
                    if use_v2:
                        yield v2_event(
                            "error",
                            domain_event.data,
                            terminal=True,
                        )
                    else:
                        yield terminal_error(code)
                    return
                if use_v2:
                    yield v2_event(
                        domain_event.name,
                        domain_event.data,
                        terminal=domain_event.terminal,
                    )
                    continue
                if domain_event.name == "citations":
                    yield "event: citations\n"
                    yield (
                        f"data: {json.dumps(domain_event.data, ensure_ascii=False)}\n\n"
                    )
                elif domain_event.name == "quality":
                    yield "event: quality\n"
                    yield (
                        f"data: {json.dumps(domain_event.data, ensure_ascii=False)}\n\n"
                    )
                elif domain_event.name == "answer_delta":
                    yield "event: token\n"
                    yield (
                        "data: "
                        f"{json.dumps({'token': domain_event.data['text']}, ensure_ascii=False)}"
                        "\n\n"
                    )
                elif domain_event.name == "done":
                    yield "event: done\n"
                    yield (
                        f"data: {json.dumps(domain_event.data, ensure_ascii=False)}\n\n"
                    )
        except EventStoreUnavailableError:
            _mark_turn_failed(turn, "coordination_unavailable")
            return
        return

    def close_stream_resources():
        try:
            if turn.status in {
                ChatTurn.STATUS_ACCEPTED,
                ChatTurn.STATUS_RETRIEVING,
                ChatTurn.STATUS_REASONING,
                ChatTurn.STATUS_ANSWERING,
                ChatTurn.STATUS_SAVING,
            }:
                _mark_turn_failed(turn, "client_disconnected")
                persist_terminal_event("client_disconnected")
                _record_turn_metrics(
                    turn,
                    increments=("disconnect_count",),
                    **stream_metrics.snapshot(now=time.monotonic()),
                    disconnect_count=1,
                )
        except Exception:
            logger.warning("Could not persist stream-close event for Turn %s", turn.id)
        finally:
            try:
                lease.release()
            except CoordinationUnavailableError:
                logger.warning("Could not confirm lease release for Turn %s", turn.id)

    managed_stream = ManagedStream(event_stream(), close_stream_resources)
    return _streaming_response(managed_stream, turn=turn)


def _feedback_question_for(message):
    turn = getattr(message, "assistant_turn", None)
    if turn is not None:
        return turn.question_message
    return (
        Message.objects.filter(
            session=message.session,
            role="user",
            created_at__lte=message.created_at,
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
        logger.error(
            "feedback_audit_persist_failed action=%s code=persistence_error",
            action,
        )


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
