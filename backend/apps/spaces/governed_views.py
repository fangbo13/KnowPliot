# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""HTTP adapters for governed workspace creation."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .creation_services import (
    approve_creation_request,
    cancel_creation_request,
    get_creation_request,
    refresh_creation_impact,
    reject_creation_request,
    submit_creation_request,
)
from .governed import GovernedWorkflowError, normalize_text, parse_idempotency_key, require_idempotency_key
from .models import GovernedActionRequest
from .permissions import is_platform_admin


def _flag_enabled(name: str) -> bool:
    return bool(getattr(settings, name, False))


def _reviewer(user) -> bool:
    if is_platform_admin(user) or bool(getattr(user, "is_staff", False)):
        return True
    try:
        from apps.rbac.models import UserRole

        return UserRole.objects.filter(
            user=user,
            is_active=True,
            role__name="admin",
            role__is_active=True,
        ).exists()
    except Exception:
        return False


def _require_reviewer(user):
    if not _reviewer(user):
        raise PermissionDenied("The platform workspace-creation review capability is required.")


def _strict_body(data, allowed: set[str]):
    if not isinstance(data, dict):
        raise ValidationError({"detail": "A JSON object is required."})
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValidationError({"unknown_fields": unknown})


def _resolve_work_group_name(work_group_id):
    from .models import WorkGroup

    wg = WorkGroup.objects.filter(pk=work_group_id).first()
    return wg.display_name if wg else None


def _resolve_office_location_names(office_location_ids):
    from .models import OfficeLocation

    if not office_location_ids:
        return []
    locs = OfficeLocation.objects.filter(pk__in=office_location_ids).order_by("sort_order", "display_name")
    return [loc.display_name for loc in locs]


def _request_payload(row):
    body = {
        "request_id": str(row.id),
        "status": row.status,
        "request_version": row.request_version,
        "impact_revision": row.impact_revision,
        "impact_version": row.impact_version,
        "impact_expires_at": row.impact_expires_at.isoformat() if row.impact_expires_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "requester_uuid": str(row.requester_uuid),
        "scope_type": row.scope_type,
    }
    detail = getattr(row, "create_detail", None)
    if detail:
        body["submitted"] = {
            "name": detail.normalized_name,
            "code": detail.normalized_code,
            "purpose": detail.purpose,
            "visibility": detail.requested_visibility,
            "business_line_id": str(detail.business_line_id),
            "business_line_name": detail.business_line.name if detail.business_line_id else None,
            "work_group_id": str(detail.work_group_id),
            "work_group_name": _resolve_work_group_name(detail.work_group_id),
            "office_location_ids": [str(value) for value in detail.office_location_ids],
            "office_location_names": _resolve_office_location_names(detail.office_location_ids),
            "template_version_id": str(detail.template_version_id) if detail.template_version_id else None,
        }
    if row.result_uuid:
        body["result_uuid"] = str(row.result_uuid)
    if row.failure_code:
        body["failure_code"] = row.failure_code
    return body


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def creation_request_submit(request):
    if not _flag_enabled("WORKSPACE_CREATION_APPROVAL"):
        raise GovernedWorkflowError("workspace_creation_disabled", "Workspace creation is disabled.", status_code=503)
    key = require_idempotency_key(request)
    body = submit_creation_request(actor=request.user, payload=dict(request.data), idempotency_key=key)
    if isinstance(body, Response):
        return body
    return Response(body, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def creation_request_mine(request):
    rows = (
        GovernedActionRequest.objects.filter(
            requester_uuid=request.user.id,
            action_type=GovernedActionRequest.ACTION_WORKSPACE_CREATE,
        )
        .select_related("create_detail", "create_detail__business_line")
        .order_by("-created_at")
    )
    limit = min(max(int(request.query_params.get("limit", "50")), 1), 100)
    return Response({"results": [_request_payload(row) for row in rows[:limit]], "next_cursor": None})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def creation_request_detail(request, request_id):
    if request.method == "GET":
        row = get_creation_request(actor=request.user, request_id=request_id)
        return Response(_request_payload(row))
    _strict_body(request.data, {"expected_request_version"})
    try:
        expected = int(request.data.get("expected_request_version"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_request_version": "Must be an integer."}) from exc
    key = require_idempotency_key(request)
    body = cancel_creation_request(actor=request.user, request_id=request_id, expected_version=expected, idempotency_key=key)
    if isinstance(body, Response):
        return body
    return Response(body, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_governed_requests(request):
    _require_reviewer(request.user)
    action = request.query_params.get("action", GovernedActionRequest.ACTION_WORKSPACE_CREATE)
    statuses = request.query_params.get("status")
    if action not in {choice[0] for choice in GovernedActionRequest.ACTION_CHOICES}:
        raise ValidationError({"action": "Unsupported action."})
    rows = GovernedActionRequest.objects.filter(action_type=action).select_related(
        "create_detail", "create_detail__business_line",
    ).order_by("created_at")
    if statuses:
        values = {value.strip() for value in statuses.split(",") if value.strip()}
        allowed = {choice[0] for choice in GovernedActionRequest.STATUS_CHOICES}
        if not values <= allowed:
            raise ValidationError({"status": "Unsupported status filter."})
        rows = rows.filter(status__in=values)
    return Response({"results": [_request_payload(row) for row in rows[:100]], "next_cursor": None})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_governed_request_impact(request, request_id):
    _require_reviewer(request.user)
    row = get_creation_request(actor=request.user, request_id=request_id, reviewer=True)
    if row.status != GovernedActionRequest.STATUS_PENDING:
        raise GovernedWorkflowError("request_not_pending")
    # Refresh the impact snapshot when it has expired so the reviewer
    # always sees a current snapshot before approving.
    if not row.impact_expires_at or row.impact_expires_at <= timezone.now():
        row = refresh_creation_impact(actor=request.user, request_id=request_id, reviewer=True)
    return Response({
        "request_id": str(row.id),
        "impact_version": row.impact_version,
        "impact_revision": row.impact_revision,
        "impact_expires_at": row.impact_expires_at.isoformat() if row.impact_expires_at else None,
        "impact": row.impact_snapshot,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_governed_request_approve(request, request_id):
    _require_reviewer(request.user)
    _strict_body(request.data, {"expected_request_version", "impact_version", "acknowledge_requester_becomes_owner", "bypass_separation"})
    try:
        expected = int(request.data.get("expected_request_version"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_request_version": "Must be an integer."}) from exc
    if request.data.get("acknowledge_requester_becomes_owner") is not True:
        raise ValidationError({"acknowledge_requester_becomes_owner": "Must be true."})
    key = require_idempotency_key(request)
    body = approve_creation_request(
        reviewer=request.user,
        request_id=request_id,
        expected_version=expected,
        impact_version=request.data.get("impact_version", ""),
        acknowledge_requester_becomes_owner=True,
        idempotency_key=key,
        bypass_separation=bool(request.data.get("bypass_separation", False)),
    )
    if isinstance(body, Response):
        return body
    return Response(body, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_governed_request_reject(request, request_id):
    _require_reviewer(request.user)
    _strict_body(request.data, {"expected_request_version", "reason_code", "reason_text"})
    try:
        expected = int(request.data.get("expected_request_version"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_request_version": "Must be an integer."}) from exc
    key = require_idempotency_key(request)
    body = reject_creation_request(
        reviewer=request.user,
        request_id=request_id,
        expected_version=expected,
        reason_code=request.data.get("reason_code", ""),
        reason_text=request.data.get("reason_text", ""),
        idempotency_key=key,
    )
    if isinstance(body, Response):
        return body
    return Response(body, status=status.HTTP_200_OK)


__all__ = [
    "creation_request_submit",
    "creation_request_mine",
    "creation_request_detail",
    "admin_governed_requests",
    "admin_governed_request_impact",
    "admin_governed_request_approve",
    "admin_governed_request_reject",
]
