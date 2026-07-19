"""Platform-wide Knowledge metadata boundary (never content authority)."""

from __future__ import annotations

import hashlib
import json
import uuid

from django.core import signing
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.rbac.capabilities import resolve_capabilities

from .models import Document


PAGE_SIZE = 50
CURSOR_SALT = "knowpilot.platform-knowledge.v2"
ALLOWED_QUERY_FIELDS = {
    "q",
    "organization_id",
    "business_line_id",
    "work_group_id",
    "space_id",
    "status",
    "cursor",
}


def _uuid(value, field):
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Must be a UUID."}) from exc


def _query_signature(values):
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _decode_cursor(raw_cursor, signature):
    if not raw_cursor:
        return None
    try:
        payload = signing.loads(raw_cursor, salt=CURSOR_SALT, max_age=3600)
        if payload.get("signature") != signature:
            raise ValueError("cursor scope changed")
        from django.utils.dateparse import parse_datetime

        created_at = parse_datetime(payload["created_at"])
        document_id = uuid.UUID(payload["id"])
        if created_at is None:
            raise ValueError("invalid cursor timestamp")
        return created_at, document_id
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise ValidationError({"cursor": "Invalid or expired cursor."}) from exc


def _encode_cursor(document, signature):
    return signing.dumps(
        {
            "created_at": document.created_at.isoformat(),
            "id": str(document.id),
            "signature": signature,
        },
        salt=CURSOR_SALT,
        compress=True,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def platform_document_metadata(request):
    if "platform.knowledge.read" not in resolve_capabilities(request.user).get(
        "capabilities", []
    ):
        raise PermissionDenied("platform.knowledge.read is required.")
    unknown_query_fields = sorted(set(request.query_params) - ALLOWED_QUERY_FIELDS)
    if unknown_query_fields:
        raise ValidationError({"unknown_query_fields": unknown_query_fields})
    query = (request.query_params.get("q") or "").strip()
    if len(query) > 100:
        raise ValidationError({"q": "Must be at most 100 characters."})
    organization_id = _uuid(request.query_params.get("organization_id"), "organization_id")
    business_line_id = _uuid(request.query_params.get("business_line_id"), "business_line_id")
    work_group_id = _uuid(request.query_params.get("work_group_id"), "work_group_id")
    space_id = _uuid(request.query_params.get("space_id"), "space_id")
    status_filter = request.query_params.get("status") or ""
    allowed_status = {choice[0] for choice in Document.STATUS_CHOICES}
    if status_filter and status_filter not in allowed_status:
        raise ValidationError({"status": "Unsupported document status."})
    filter_values = {
        "q": query,
        "organization_id": str(organization_id or ""),
        "business_line_id": str(business_line_id or ""),
        "work_group_id": str(work_group_id or ""),
        "space_id": str(space_id or ""),
        "status": status_filter,
    }
    signature = _query_signature(filter_values)
    cursor = _decode_cursor(request.query_params.get("cursor"), signature)
    rows = (
        Document.objects.all()
        .select_related(
            "space",
            "space__organization",
            "space__business_line",
            "space__work_group",
        )
        .order_by("-created_at", "-id")
    )
    if query:
        rows = rows.filter(Q(title__icontains=query) | Q(space__name__icontains=query) | Q(space__code__icontains=query))
    if organization_id:
        rows = rows.filter(space__organization_id=organization_id)
    if business_line_id:
        rows = rows.filter(space__business_line_id=business_line_id)
    if work_group_id:
        rows = rows.filter(space__work_group_id=work_group_id)
    if space_id:
        rows = rows.filter(space_id=space_id)
    if status_filter:
        rows = rows.filter(status=status_filter)
    if cursor:
        created_at, document_id = cursor
        rows = rows.filter(
            Q(created_at__lt=created_at)
            | Q(created_at=created_at, id__lt=document_id)
        )

    results = []
    page = list(rows[: PAGE_SIZE + 1])
    for document in page[:PAGE_SIZE]:
        space = document.space
        if space is None:
            organization = None
            business_line = None
            work_group = None
            space_identity = {
                "id": None,
                "code": None,
                "name": "Unassigned",
            }
        else:
            organization = {
                "id": str(space.organization_id),
                "slug": space.organization.slug,
                "name": space.organization.name,
            }
            business_line = (
                {
                    "id": str(space.business_line_id),
                    "code": space.business_line.code,
                    "name": space.business_line.name,
                }
                if space.business_line_id
                else None
            )
            work_group = (
                {
                    "id": str(space.work_group_id),
                    "code": space.work_group.normalized_code,
                    "name": space.work_group.display_name,
                }
                if space.work_group_id
                else None
            )
            space_identity = {
                "id": str(space.id),
                "code": space.code,
                "name": space.name,
            }
        results.append(
            {
                "id": str(document.id),
                "title": document.title,
                "status": document.status,
                "version": document.version,
                "organization": organization,
                "business_line": business_line,
                "work_group": work_group,
                "space": space_identity,
                "created_at": document.created_at.isoformat(),
                "updated_at": document.updated_at.isoformat(),
            }
        )
    next_cursor = (
        _encode_cursor(page[PAGE_SIZE - 1], signature)
        if len(page) > PAGE_SIZE
        else None
    )
    return Response({"results": results, "next_cursor": next_cursor})


__all__ = ["platform_document_metadata"]
