# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Notification views — V7.0.

User feed + read-state endpoints, plus an admin endpoint to publish
announcements (version updates). Announcement publishing is restricted to
platform admins and organization admins; the audited action is
``notification_broadcast``.
"""

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from . import services
from .models import Announcement, Notification
from .serializers import AnnouncementCreateSerializer, AnnouncementSerializer

logger = logging.getLogger(__name__)


def _can_publish_announcement(user) -> bool:
    """Platform admins and organization admins may publish announcements."""
    try:
        from apps.spaces.permissions import is_platform_admin, admin_scope
        if is_platform_admin(user):
            return True
        org_ids, _ = admin_scope(user)
        return bool(org_ids)
    except Exception:  # pragma: no cover
        return False


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notifications_feed(request):
    """Merged feed: targeted notifications + matching announcements."""
    return Response({"results": services.user_feed(request.user)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unread_count(request):
    return Response({"count": services.unread_count(request.user)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_read(request, item_id):
    ok = services.mark_read(request.user, item_id)
    if not ok:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response({"read": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    n = services.mark_all_read(request.user)
    return Response({"marked": n})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_action(request, item_id, action):
    """Delegate one actionable item to its canonical resource service."""

    from apps.spaces.governed import GovernedWorkflowError, require_idempotency_key
    from apps.spaces.join_services import decide_access_request, respond_invitation
    from apps.spaces.models import SpaceAccessRequest

    try:
        notification = Notification.objects.get(pk=item_id, recipient=request.user)
    except Notification.DoesNotExist as exc:
        raise NotFound("Notification not found.") from exc
    resource_actions = {
        "space_invitation": {"accept", "decline"},
        "space_access_request": {"approve", "reject"},
    }
    known_actions = resource_actions.get(notification.resource_type, set())
    if (
        notification.action_state == Notification.ACTION_NONE
        or notification.action_kind == Notification.ACTION_KIND_RESOURCE_DELETED
        or action not in known_actions
        or not notification.resource_uuid
        or (
            notification.action_state == Notification.ACTION_AVAILABLE
            and action not in (notification.allowed_actions or [])
        )
    ):
        raise GovernedWorkflowError(
            "notification_action_not_available",
            details={"action_state": notification.action_state},
        )
    if not isinstance(request.data, dict):
        raise ValidationError({"detail": "A JSON object is required."})
    key = require_idempotency_key(request)
    try:
        expected = int(request.data.get("expected_resource_version"))
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            {"expected_resource_version": "Must be an integer."}
        ) from exc

    if notification.resource_type == "space_invitation":
        unknown = sorted(set(request.data) - {"expected_resource_version"})
        if unknown:
            raise ValidationError({"unknown_fields": unknown})
        body = respond_invitation(
            actor=request.user,
            invitation_id=notification.resource_uuid,
            expected_version=expected,
            action=action,
            idempotency_key=key,
        )
    elif notification.resource_type == "space_access_request":
        try:
            resource = SpaceAccessRequest.objects.select_related("space").get(
                pk=notification.resource_uuid
            )
        except SpaceAccessRequest.DoesNotExist as exc:
            raise NotFound("Notification resource not found.") from exc
        allowed = {"expected_resource_version", "role"}
        if action == "reject":
            allowed |= {"reason_code", "reason_text"}
        unknown = sorted(set(request.data) - allowed)
        if unknown:
            raise ValidationError({"unknown_fields": unknown})
        if action == "approve" and not request.data.get("role"):
            raise ValidationError({"role": "This field is required."})
        if action == "reject" and not request.data.get("reason_code"):
            raise ValidationError({"reason_code": "This field is required."})
        body = decide_access_request(
            actor=request.user,
            space=resource.space,
            request_id=resource.id,
            expected_version=expected,
            action=action,
            role=request.data.get("role"),
            reason_code=request.data.get("reason_code", ""),
            reason_text=request.data.get("reason_text", ""),
            idempotency_key=key,
        )
    else:
        raise GovernedWorkflowError("notification_action_not_available")

    if isinstance(body, Response):
        return body
    return Response(body)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def announcements(request):
    """GET: list announcements the user can manage. POST: publish a new one."""
    if request.method == "GET":
        if not _can_publish_announcement(request.user):
            raise PermissionDenied("You cannot manage announcements.")
        qs = Announcement.objects.all()[:100]
        return Response({"results": AnnouncementSerializer(qs, many=True).data})

    # POST — publish
    if not _can_publish_announcement(request.user):
        raise PermissionDenied("You cannot publish announcements.")

    serializer = AnnouncementCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    ann = serializer.save(created_by=request.user, published_at=timezone.now())

    # Audit — best-effort.
    try:
        from apps.audit.views import create_audit_log
        create_audit_log(
            user=request.user,
            action="notification_broadcast",
            target_type="Announcement",
            target_id=ann.id,
            details={"audience": ann.audience, "audience_ref": ann.audience_ref, "version": ann.version},
            request=request,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("announcement audit failed: %s", exc)

    return Response(AnnouncementSerializer(ann).data, status=status.HTTP_201_CREATED)
