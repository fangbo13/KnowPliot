"""HTTP adapters for owner-only permanent workspace deletion."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .deletion_services import (
    cancel_deletion_request,
    confirm_deletion_request,
    get_deletion_impact,
    get_deletion_request_status,
    submit_deletion_request,
)
from .governed import require_idempotency_key


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workspace_deletion_impact(request, pk):
    return Response(get_deletion_impact(actor=request.user, space_id=pk))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def workspace_deletion_request_submit(request, pk):
    result = submit_deletion_request(
        actor=request.user,
        space_id=pk,
        payload=dict(request.data),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(result, Response):
        return result
    return Response(result, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def workspace_deletion_request_confirm(request, pk, request_id):
    result = confirm_deletion_request(
        actor=request.user,
        space_id=pk,
        request_id=request_id,
        payload=dict(request.data),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(result, Response):
        return result
    return Response(result, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def workspace_deletion_request_cancel(request, pk, request_id):
    result = cancel_deletion_request(
        actor=request.user,
        space_id=pk,
        request_id=request_id,
        payload=dict(request.data),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(result, Response):
        return result
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workspace_deletion_request_status(request, request_id):
    return Response(
        get_deletion_request_status(actor=request.user, request_id=request_id)
    )


__all__ = [
    "workspace_deletion_impact",
    "workspace_deletion_request_submit",
    "workspace_deletion_request_confirm",
    "workspace_deletion_request_cancel",
    "workspace_deletion_request_status",
]
