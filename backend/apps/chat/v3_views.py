"""Protocol-v3 acceptance, asynchronous SSE delivery, and cancellation."""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from functools import lru_cache

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import transaction
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.urls import reverse
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.spaces.permissions import CHAT_ASK, CHAT_VIEW_HISTORY, has_space_permission

from .capacity import GenerationCapacityUnavailable
from .models import ChatTurn
from .services import (
    ACTIVE_TURN_STATUSES,
    BeginTurnDisposition,
    InvalidTurnTransitionError,
    transition_chat_turn,
)
from .stream_events import EventStoreUnavailableError
from .stream_events_v3 import _decode_stream_rows
from .tasks import (
    cancel_probe,
    enqueue_chat_turn_v3,
    generation_capacity_controller,
    v3_event_store,
)

logger = logging.getLogger(__name__)


def _turn_urls(turn):
    return {
        "events_url": reverse("chat-turn-events", kwargs={"turn_id": turn.id}),
        "status_url": reverse("chat-turn-status", kwargs={"turn_id": turn.id}),
        "cancel_url": reverse("chat-turn-cancel", kwargs={"turn_id": turn.id}),
    }


def _accepted_response(turn):
    urls = _turn_urls(turn)
    public_status = (
        "completed"
        if turn.status == ChatTurn.STATUS_COMPLETED
        else "accepted"
    )
    payload = {
        "turn_id": str(turn.id),
        "session_id": str(turn.session_id),
        "client_request_id": str(turn.client_request_id),
        "status": public_status,
        **urls,
    }
    return Response(
        payload,
        status=status.HTTP_202_ACCEPTED,
        headers={
            "Location": urls["status_url"],
            "X-Chat-Turn-Id": str(turn.id),
            "X-Chat-Client-Request-Id": str(turn.client_request_id),
        },
    )


def _v3_meta(turn):
    return {
        "turn_id": str(turn.id),
        "session_id": str(turn.session_id),
        "client_request_id": str(turn.client_request_id),
        "protocol_version": 3,
        "requested_answer_mode": turn.requested_answer_mode,
        "answer_mode": turn.answer_mode,
        "requested_thinking_enabled": turn.requested_thinking_enabled,
        "thinking_enabled": turn.thinking_enabled,
        "thinking_snapshot_known": turn.thinking_snapshot_known,
        "thinking_budget": turn.thinking_budget,
        "model_id": turn.model_id,
        "policy_fallback_code": turn.policy_fallback_code,
    }


def _fail_active_turn(turn, code):
    try:
        transition_chat_turn(turn, ChatTurn.STATUS_FAILED, error_code=code)
    except InvalidTurnTransitionError:
        return
    except Exception:
        logger.error(
            "v3_accept_failure_persist_failed turn_id=%s code=persistence_error",
            turn.id,
        )


def accept_chat_turn_v3(
    turn,
    *,
    disposition,
    capacity=None,
    event_store=None,
    enqueue=None,
):
    """Reserve capacity, publish identity, and enqueue only after commit."""

    if disposition in {
        BeginTurnDisposition.IN_PROGRESS,
        BeginTurnDisposition.COMPLETED,
    }:
        return _accepted_response(turn)

    capacity = capacity or generation_capacity_controller()
    event_store = event_store or v3_event_store(turn.id)
    enqueue = enqueue or enqueue_chat_turn_v3
    try:
        reservation = capacity.reserve(turn.id)
    except GenerationCapacityUnavailable:
        _fail_active_turn(turn, "coordination_unavailable")
        return Response(
            {"code": "coordination_unavailable", "retryable": True},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if not reservation.accepted:
        _fail_active_turn(turn, "capacity_reached")
        response = Response(
            {
                "code": "generation_capacity_reached",
                "retryable": True,
                "retry_after_seconds": reservation.retry_after_seconds,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        response["Retry-After"] = str(reservation.retry_after_seconds)
        return response

    cleanup_done = False
    enqueue_failed = False

    def cleanup_failure(*, persist_event=False):
        nonlocal cleanup_done
        if cleanup_done:
            return
        cleanup_done = True
        if persist_event:
            with suppress(Exception):
                event_store.append(
                    "error",
                    {"code": "coordination_unavailable", "retryable": True},
                    terminal=True,
                )
        with suppress(Exception):
            capacity.release(turn.id)
        _fail_active_turn(turn, "coordination_unavailable")

    try:
        event_store.append("meta", _v3_meta(turn))
        event_store.append("phase", {"phase": "queued"})

        def enqueue_after_commit():
            nonlocal enqueue_failed
            try:
                return enqueue(turn.id)
            except Exception:
                enqueue_failed = True
                cleanup_failure(persist_event=True)
                return None

        transaction.on_commit(enqueue_after_commit)
        if enqueue_failed:
            return Response(
                {"code": "coordination_unavailable", "retryable": True},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
    except Exception:
        cleanup_failure()
        return Response(
            {"code": "coordination_unavailable", "retryable": True},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return _accepted_response(turn)


def _owned_turn_for_control(user, turn_id):
    try:
        turn = ChatTurn.objects.select_related("space").get(pk=turn_id, user=user)
    except ChatTurn.DoesNotExist:
        raise Http404 from None
    if turn.space_id and not has_space_permission(user, turn.space, CHAT_ASK):
        raise Http404
    return turn


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def cancel_chat_turn_v3(request, turn_id):
    turn = _owned_turn_for_control(request.user, turn_id)
    if turn.protocol_version != 3:
        return Response(
            {"code": "turn_not_cancellable"},
            status=status.HTTP_409_CONFLICT,
        )
    if turn.status == ChatTurn.STATUS_CANCELLED:
        return Response({"status": "cancelling"}, status=status.HTTP_202_ACCEPTED)
    if turn.status not in ACTIVE_TURN_STATUSES:
        return Response(
            {"code": "turn_not_cancellable"},
            status=status.HTTP_409_CONFLICT,
        )
    try:
        cancel_probe(turn.id).request()
    except Exception:
        return Response(
            {"code": "coordination_unavailable", "retryable": True},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"status": "cancelling"}, status=status.HTTP_202_ACCEPTED)


def _authenticate_request(request):
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    from apps.users.authentication import BlacklistCheckingJWTAuthentication

    result = BlacklistCheckingJWTAuthentication().authenticate(request)
    if result is None:
        return None
    request.user = result[0]
    request.auth = result[1]
    return result[0]


def _load_owned_turn(user, turn_id):
    try:
        turn = ChatTurn.objects.select_related("space").get(pk=turn_id, user=user)
    except ChatTurn.DoesNotExist:
        raise Http404 from None
    required_permission = (
        CHAT_ASK if turn.status in ACTIVE_TURN_STATUSES else CHAT_VIEW_HISTORY
    )
    if turn.space_id and not has_space_permission(
        user,
        turn.space,
        required_permission,
    ):
        raise Http404
    return turn


def _still_authorized(user_id, turn_id):
    try:
        turn = ChatTurn.objects.select_related("space", "user").get(
            pk=turn_id,
            user_id=user_id,
        )
    except ChatTurn.DoesNotExist:
        return False
    required_permission = (
        CHAT_ASK if turn.status in ACTIVE_TURN_STATUSES else CHAT_VIEW_HISTORY
    )
    return not turn.space_id or has_space_permission(
        turn.user,
        turn.space,
        required_permission,
    )


@lru_cache(maxsize=2)
def _async_redis_from_url(url):
    from redis.asyncio import Redis

    return Redis.from_url(
        url,
        decode_responses=False,
        socket_connect_timeout=2,
        socket_timeout=20,
        health_check_interval=30,
    )


def _async_events_client():
    return _async_redis_from_url(settings.CHAT_EVENTS_REDIS_URL)


def _event_cursor(request):
    value = request.GET.get("after")
    if value in (None, ""):
        value = request.headers.get("Last-Event-ID", "0")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


async def _v3_event_iterator(request, turn, client):
    cursor = _event_cursor(request)
    events_key = f"chat:v3:turn:{turn.id}:events"
    last_authorization_check = time.monotonic()
    try:
        rows = await client.xrange(events_key, min=f"({cursor}-0", max="+")
        for event in _decode_stream_rows(rows):
            cursor = event.sequence
            yield event.to_sse()
            if event.name in {"done", "error"}:
                return

        while True:
            now = time.monotonic()
            if now - last_authorization_check >= 30:
                allowed = await sync_to_async(
                    _still_authorized,
                    thread_sensitive=True,
                )(turn.user_id, turn.id)
                if not allowed:
                    return
                last_authorization_check = now
            result = await client.xread(
                {events_key: f"{cursor}-0"},
                block=15_000,
                count=256,
            )
            if not result:
                yield ": heartbeat\n\n"
                continue
            rows = []
            for _key, stream_rows in result:
                rows.extend(stream_rows)
            for event in _decode_stream_rows(rows):
                cursor = event.sequence
                yield event.to_sse()
                if event.name in {"done", "error"}:
                    return
    except Exception:
        logger.warning(
            "v3_event_stream_failed turn_id=%s code=coordination_unavailable",
            turn.id,
        )
        return


async def chat_turn_events_dispatch(request, turn_id):
    try:
        user = await sync_to_async(_authenticate_request, thread_sensitive=True)(
            request
        )
    except Exception:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    if user is None:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    try:
        turn = await sync_to_async(_load_owned_turn, thread_sensitive=True)(
            user,
            turn_id,
        )
    except Http404:
        return JsonResponse({"detail": "Not found."}, status=404)

    if turn.protocol_version != 3:
        from .views import chat_turn_events

        return await sync_to_async(chat_turn_events, thread_sensitive=True)(
            request,
            turn_id,
        )

    response = StreamingHttpResponse(
        _v3_event_iterator(request, turn, _async_events_client()),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["X-Chat-Turn-Id"] = str(turn.id)
    response["X-Chat-Client-Request-Id"] = str(turn.client_request_id)
    return response
