"""HTTP adapters for the ownership transfer service.

These views intentionally perform capability checks only to select the
permitted operation; the domain service rechecks the canonical owner and
scope-sensitive invariants while holding rows locked.
"""

import uuid

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone

from apps.rbac.capabilities import resolve_capabilities

from .models import KnowledgeSpace, OwnershipTransfer, SpaceMembership
from .ownership_services import OwnershipConflict, OwnershipTransferService


def _has_capability(user, space_id, capability):
    return capability in resolve_capabilities(user, space_id=space_id)["capabilities"]


def _transfer_data(transfer):
    return {
        "id": str(transfer.id),
        "space_id": str(transfer.space_id),
        "from_owner_id": str(transfer.from_owner_id),
        "to_owner_id": str(transfer.to_owner_id),
        "mode": transfer.mode,
        "status": transfer.status,
        "expected_ownership_version": transfer.expected_ownership_version,
        "expires_at": transfer.expires_at,
        "completed_at": transfer.completed_at,
    }


def _conflict_response(error):
    return Response({"error_code": str(error)}, status=status.HTTP_409_CONFLICT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_pending_ownership_transfers(request):
    """List only transfers that the authenticated user may accept or decline."""

    rows = OwnershipTransfer.objects.filter(
        to_owner=request.user,
        status=OwnershipTransfer.STATUS_PENDING,
        space__status__in=("active", "archived"),
    ).select_related("space").order_by("expires_at", "created_at")
    return Response({
        "results": [
            {
                **_transfer_data(transfer),
                "space": {
                    "id": str(transfer.space_id),
                    "display_name": transfer.space.name,
                    "status": transfer.space.status,
                },
            }
            for transfer in rows
        ],
        "next": None,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ownership_detail(request, pk):
    if not _has_capability(request.user, pk, "workspace.ownership.read"):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        space = KnowledgeSpace.objects.select_related("owner").get(pk=pk)
    except KnowledgeSpace.DoesNotExist:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    pending = OwnershipTransfer.objects.filter(
        space=space, status=OwnershipTransfer.STATUS_PENDING
    ).order_by("created_at").first()
    owner = space.owner
    return Response(
        {
            "owner": None if owner is None else {"id": str(owner.id), "display_name": owner.get_full_name() or owner.username, "is_active": owner.is_active},
            "ownership_version": space.ownership_version,
            "pending_transfer": None if pending is None else _transfer_data(pending),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ownership_candidates(request, pk):
    purpose = request.query_params.get("purpose", "voluntary")
    capability = "workspace.ownership.transfer.request" if purpose == "voluntary" else "workspace.ownership.transfer.force"
    if purpose not in {"voluntary", "forced"} or not _has_capability(request.user, pk, capability):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        space = KnowledgeSpace.objects.get(pk=pk)
    except KnowledgeSpace.DoesNotExist:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    search = request.query_params.get("q", "").strip()
    try:
        offset = max(0, int(request.query_params.get("offset", "0")))
        limit = min(50, max(1, int(request.query_params.get("limit", "20"))))
    except ValueError:
        return Response({"error_code": "invalid_pagination"}, status=status.HTTP_400_BAD_REQUEST)
    if purpose == "voluntary":
        rows = SpaceMembership.objects.select_related("user").filter(
            space=space,
            status="active",
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).exclude(
            user_id=space.owner_id
        ).exclude(role=SpaceMembership.ROLE_GUEST)
        if search:
            rows = rows.filter(Q(user__username__icontains=search) | Q(user__email__icontains=search))
        page = list(rows.filter(user__is_active=True).order_by("user__username")[offset:offset + limit + 1])
        result = [
            {"id": str(row.user_id), "display_name": row.user.get_full_name() or row.user.username, "role": row.role, "requires_membership": False}
            for row in page[:limit]
        ]
    else:
        users = type(request.user).objects.filter(is_active=True).filter(
            space_memberships__space__organization=space.organization,
            space_memberships__status="active",
        ).exclude(pk=space.owner_id).distinct()
        if search:
            users = users.filter(Q(username__icontains=search) | Q(email__icontains=search))
        page = list(users.order_by("username")[offset:offset + limit + 1])
        result = [
            {"id": str(user.id), "display_name": user.get_full_name() or user.username, "requires_membership": not SpaceMembership.objects.filter(space=space, user=user).exists()}
            for user in page[:limit]
        ]
    return Response({"results": result, "next": offset + limit if len(page) > limit else None})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ownership_transfer_request(request, pk):
    if not _has_capability(request.user, pk, "workspace.ownership.transfer.request"):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        idempotency_key = uuid.UUID(request.headers.get("Idempotency-Key", ""))
        transfer = OwnershipTransferService.request(
            actor=request.user,
            space_id=pk,
            to_owner_id=request.data["to_user_id"],
            expected_ownership_version=request.data["expected_ownership_version"],
            idempotency_key=idempotency_key,
            reason_code=request.data.get("reason_code", "voluntary"),
        )
    except (KeyError, TypeError, ValueError):
        return Response({"error_code": "invalid_successor"}, status=status.HTTP_400_BAD_REQUEST)
    except KnowledgeSpace.DoesNotExist:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    except OwnershipConflict as error:
        return _conflict_response(error)
    return Response(_transfer_data(transfer), status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ownership_transfer_force(request, pk):
    if not _has_capability(request.user, pk, "workspace.ownership.transfer.force"):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        idempotency_key = uuid.UUID(request.headers.get("Idempotency-Key", ""))
        transfer = OwnershipTransferService.force(
            actor=request.user,
            space_id=pk,
            to_owner_id=request.data["to_user_id"],
            expected_ownership_version=request.data["expected_ownership_version"],
            idempotency_key=idempotency_key,
            reason_code=request.data["reason_code"],
        )
    except (KeyError, TypeError, ValueError):
        return Response({"error_code": "invalid_successor"}, status=status.HTTP_400_BAD_REQUEST)
    except KnowledgeSpace.DoesNotExist:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    except OwnershipConflict as error:
        return _conflict_response(error)
    return Response(_transfer_data(transfer))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def legacy_transfer_owner(request, pk):
    """Compatibility adapter for the retired direct-owner mutation endpoint.

    It never changes memberships directly: an owner creates a voluntary request,
    while an authorized scoped administrator performs a reasoned forced handoff.
    """

    try:
        space = KnowledgeSpace.objects.only("id", "owner_id", "ownership_version").get(pk=pk)
    except KnowledgeSpace.DoesNotExist:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    try:
        target_id = request.data.get("to_user_id") or request.data["user"]
        expected_version = request.data.get("expected_ownership_version", space.ownership_version)
        idempotency_key = uuid.UUID(request.headers.get("Idempotency-Key", ""))
    except (KeyError, TypeError, ValueError):
        return Response({"error_code": "idempotency_key_required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if request.user.id == space.owner_id:
            if not _has_capability(request.user, pk, "workspace.ownership.transfer.request"):
                return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
            transfer = OwnershipTransferService.request(
                actor=request.user,
                space_id=pk,
                to_owner_id=target_id,
                expected_ownership_version=expected_version,
                idempotency_key=idempotency_key,
                reason_code="legacy_voluntary",
            )
            response_status = status.HTTP_202_ACCEPTED
        else:
            if not _has_capability(request.user, pk, "workspace.ownership.transfer.force"):
                return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
            transfer = OwnershipTransferService.force(
                actor=request.user,
                space_id=pk,
                to_owner_id=target_id,
                expected_ownership_version=expected_version,
                idempotency_key=idempotency_key,
                reason_code=request.data["reason_code"],
            )
            response_status = status.HTTP_200_OK
    except (KeyError, TypeError, ValueError):
        return Response({"error_code": "invalid_successor"}, status=status.HTTP_400_BAD_REQUEST)
    except OwnershipConflict as error:
        return _conflict_response(error)

    response = Response(_transfer_data(transfer), status=response_status)
    response["Deprecation"] = "true"
    response["Link"] = f'</api/v1/spaces/{pk}/ownership-transfers/>; rel="successor-version"'
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ownership_transfer_accept(request, pk, transfer_id):
    if not _has_capability(request.user, pk, "workspace.ownership.transfer.accept"):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        transfer = OwnershipTransferService.accept(actor=request.user, transfer_id=transfer_id)
    except OwnershipTransfer.DoesNotExist:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    except OwnershipConflict as error:
        return _conflict_response(error)
    if transfer.space_id != pk:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(_transfer_data(transfer))


def _terminal_transfer(request, pk, transfer_id, operation):
    transfer = OwnershipTransfer.objects.filter(pk=transfer_id, space_id=pk).first()
    if transfer is None:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    capability = "workspace.ownership.transfer.accept" if operation == "decline" else "workspace.ownership.transfer.request"
    if not _has_capability(request.user, pk, capability):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        result = getattr(OwnershipTransferService, operation)(actor=request.user, transfer_id=transfer_id)
    except OwnershipConflict as error:
        return _conflict_response(error)
    return Response(_transfer_data(result))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ownership_transfer_decline(request, pk, transfer_id):
    return _terminal_transfer(request, pk, transfer_id, "decline")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ownership_transfer_cancel(request, pk, transfer_id):
    return _terminal_transfer(request, pk, transfer_id, "cancel")
