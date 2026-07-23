# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license information.

"""SSE (Server-Sent Events) endpoint for real-time notification push.

Since ``EventSource`` cannot set custom Authorization headers, the JWT access
token is passed as a ``token`` query parameter. The view validates the token
manually via ``rest_framework_simplejwt``.

The stream polls the database every 5 s for new notifications and sends them
as SSE ``data`` events. A heartbeat comment is sent every 15 s to keep the
connection alive through proxies. The connection has a max lifetime of 5 min
to prevent resource leaks; the client reconnects automatically.
"""

import json
import logging
import time

from django.contrib.auth import get_user_model
from django.http import HttpResponse, StreamingHttpResponse
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

logger = logging.getLogger(__name__)

User = get_user_model()

# Tunables
POLL_INTERVAL = 5          # seconds between DB checks
HEARTBEAT_EVERY = 3        # send heartbeat every N polls (5*3 = 15 s)
MAX_LIFETIME = 300         # 5 min – client auto-reconnects


def _resolve_user(token_str):
    """Validate the JWT access token and return the user, or None."""
    try:
        access = AccessToken(token_str)
        user_id = access["user_id"]
        return User.objects.get(pk=user_id)
    except (TokenError, User.DoesNotExist, KeyError, ValueError) as exc:
        logger.debug("SSE token validation failed: %s", exc)
        return None


def notification_stream(request):
    """SSE endpoint: ``GET /api/v1/notifications/stream/?token=<JWT>``.

    Emits two event types:
    * ``notification`` – a new notification object (id, title, body, …)
    * ``unread_count`` – the current unread count (for badge sync)

    The connection closes after ``MAX_LIFETIME`` seconds; the browser
    ``EventSource`` will automatically reconnect.
    """
    token = request.GET.get("token", "").strip()
    if not token:
        return HttpResponse("Missing token", status=401)

    user = _resolve_user(token)
    if user is None:
        return HttpResponse("Invalid token", status=401)

    def event_stream():
        from apps.notifications.models import Notification

        from django.utils import timezone

        start = time.time()
        poll_count = 0
        # Track the timestamp of the most recent notification we have already
        # pushed so we only send truly new items.
        last_check = timezone.now()

        while True:
            elapsed = time.time() - start
            if elapsed > MAX_LIFETIME:
                yield "event: close\ndata: max_lifetime\n\n"
                break

            # Query new notifications created since our last check.
            new_items = Notification.objects.filter(
                recipient=user, created_at__gt=last_check,
            ).order_by("created_at")[:20]

            for notif in new_items:
                last_check = notif.created_at
                payload = {
                    "type": "notification",
                    "data": {
                        "id": str(notif.id),
                        "title": notif.title,
                        "body": notif.body or "",
                        "category": notif.type,
                        "level": notif.level,
                        "created_at": notif.created_at.isoformat() if notif.created_at else None,
                        "read": notif.is_read,
                        "deep_link": notif.deep_link or "",
                    },
                }
                yield f"data: {json.dumps(payload)}\n\n"

            # Sync unread count so the badge stays accurate even if
            # notifications were created server-side (e.g. by admin broadcast).
            unread = Notification.objects.filter(
                recipient=user, is_read=False
            ).count()
            count_payload = {"type": "unread_count", "data": {"count": unread}}
            yield f"data: {json.dumps(count_payload)}\n\n"

            # Heartbeat
            poll_count += 1
            if poll_count % HEARTBEAT_EVERY == 0:
                yield ": heartbeat\n\n"

            try:
                time.sleep(POLL_INTERVAL)
            except GeneratorExit:
                break

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # disable nginx buffering
    response["Connection"] = "keep-alive"
    return response
