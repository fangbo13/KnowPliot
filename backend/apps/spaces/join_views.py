"""Shape-strict HTTP adapters for workspace join-v2 workflows."""

from __future__ import annotations

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.rbac.capabilities import resolve_capabilities

from .discovery import authorized_discovery_queryset
from .governed import GovernedWorkflowError, require_idempotency_key
from .join_services import (
    _access_code_body,
    _invitation_body,
    _request_body,
    cancel_access_request,
    create_discovery_request,
    create_invitation,
    decide_access_request,
    generate_join_code,
    global_join,
    issue_access_code,
    join_by_code,
    redeem_access_code,
    redeem_invitation,
    regenerate_join_code,
    revoke_access_code,
    revoke_invitation,
    switch_join_policy,
)
from .models import (
    KnowledgeSpace,
    SpaceAccessCode,
    SpaceAccessRequest,
    SpaceInvitation,
    SpaceMembership,
)


def _enabled():
    if not bool(getattr(settings, "WORKSPACE_JOIN_V2", False)):
        raise GovernedWorkflowError(
            "workspace_join_disabled", "Workspace join v2 is disabled.", status_code=503
        )


def _strict(data, allowed):
    if not isinstance(data, dict):
        raise ValidationError({"detail": "A JSON object is required."})
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ValidationError({"unknown_fields": unknown})


def _int(data, field):
    try:
        return int(data.get(field))
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: "Must be an integer."}) from exc


def _owner_space(user, space_id, capability):
    try:
        capabilities = resolve_capabilities(user, space_id=space_id)["capabilities"]
    except NotFound as exc:
        raise NotFound("Workspace not found.") from exc
    try:
        space = KnowledgeSpace.objects.select_related("owner").get(pk=space_id)
    except KnowledgeSpace.DoesNotExist as exc:
        raise NotFound("Workspace not found.") from exc
    if space.owner_id != user.id:
        raise NotFound("Workspace not found.")
    owner_mirror = SpaceMembership.objects.filter(
        space=space,
        user=user,
        role=SpaceMembership.ROLE_OWNER,
        status="active",
        expires_at__isnull=True,
    ).exists()
    if not owner_mirror:
        raise NotFound("Workspace not found.")
    archived_reduction = (
        space.status == "archived"
        and capability
        in {"workspace.access_requests.manage", "workspace.invites.manage"}
    )
    if capability not in capabilities and not archived_reduction:
        raise NotFound("Workspace not found.")
    if space.status not in {"active", "archived"}:
        raise NotFound("Workspace not found.")
    return space


def _active_member_space(user, space_id):
    """Resolve a space where *user* is an active member (any role)."""

    try:
        space = KnowledgeSpace.objects.select_related("owner").get(pk=space_id)
    except KnowledgeSpace.DoesNotExist as exc:
        raise NotFound("Workspace not found.") from exc
    member = SpaceMembership.objects.filter(
        space=space,
        user=user,
        status="active",
        expires_at__isnull=True,
    ).exists()
    if not member:
        raise NotFound("Workspace not found.")
    if space.status not in {"active", "archived"}:
        raise NotFound("Workspace not found.")
    return space


def _manage_space(user, space_id):
    """Resolve a space where *user* is owner or knowledge_admin."""

    try:
        space = KnowledgeSpace.objects.select_related("owner").get(pk=space_id)
    except KnowledgeSpace.DoesNotExist as exc:
        raise NotFound("Workspace not found.") from exc
    admin = SpaceMembership.objects.filter(
        space=space,
        user=user,
        role__in=[
            SpaceMembership.ROLE_OWNER,
            SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
        ],
        status="active",
        expires_at__isnull=True,
    ).exists()
    if not admin and not user.is_superuser:
        raise NotFound("Workspace not found.")
    if space.status != "active":
        raise NotFound("Workspace not found.")
    return space


def _inviter_space(user, space_id):
    """Resolve a space for invitation management.

    When ``allow_member_invite`` is True, any active member can manage
    invitations; otherwise only the owner can (spec §2.3).
    """

    try:
        space = KnowledgeSpace.objects.select_related("owner").get(pk=space_id)
    except KnowledgeSpace.DoesNotExist as exc:
        raise NotFound("Workspace not found.") from exc
    if space.allow_member_invite:
        member = SpaceMembership.objects.filter(
            space=space,
            user=user,
            status="active",
            expires_at__isnull=True,
        ).exists()
        if not member:
            raise NotFound("Workspace not found.")
    else:
        owner_mirror = SpaceMembership.objects.filter(
            space=space,
            user=user,
            role=SpaceMembership.ROLE_OWNER,
            status="active",
            expires_at__isnull=True,
        ).exists()
        if not owner_mirror:
            raise NotFound("Workspace not found.")
    if space.status not in {"active", "archived"}:
        raise NotFound("Workspace not found.")
    return space


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def access_code_request_submit(request):
    _enabled()
    _strict(request.data, {"code", "reason"})
    if not isinstance(request.data.get("code"), str) or not request.data["code"].strip():
        raise ValidationError({"code": "This field is required."})
    body = redeem_access_code(
        actor=request.user,
        raw_code=request.data.get("code"),
        reason=request.data.get("reason", ""),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def access_request_mine(request):
    _enabled()
    rows = SpaceAccessRequest.objects.filter(user=request.user).select_related("space").order_by("-created_at")[:100]
    return Response({"results": [_request_body(row) for row in rows], "next_cursor": None})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def access_request_cancel(request, request_id):
    _enabled()
    _strict(request.data, {"expected_request_version"})
    body = cancel_access_request(
        actor=request.user,
        request_id=request_id,
        expected_version=_int(request.data, "expected_request_version"),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def access_code_collection(request, space_id):
    _enabled()
    space = _owner_space(request.user, space_id, "workspace.invites.manage")
    if request.method == "GET":
        rows = SpaceAccessCode.objects.filter(space=space).order_by("-created_at")[:100]
        return Response({"results": [_access_code_body(row) for row in rows], "next_cursor": None})
    body = issue_access_code(
        actor=request.user,
        space=space,
        payload=dict(request.data),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def access_code_revoke(request, space_id, code_id):
    _enabled()
    space = _owner_space(request.user, space_id, "workspace.invites.manage")
    _strict(request.data, {"expected_code_version", "reason_code"})
    if not request.data.get("reason_code"):
        raise ValidationError({"reason_code": "This field is required."})
    body = revoke_access_code(
        actor=request.user,
        space=space,
        code_id=code_id,
        expected_version=_int(request.data, "expected_code_version"),
        reason_code=request.data.get("reason_code", ""),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def invitation_collection(request, space_id):
    _enabled()
    space = _inviter_space(request.user, space_id)
    if request.method == "GET":
        rows = SpaceInvitation.objects.filter(space=space).order_by("-created_at")[:100]
        return Response({"results": [_invitation_body(row) for row in rows], "next_cursor": None})
    body = create_invitation(
        actor=request.user,
        space=space,
        payload=dict(request.data),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invitation_revoke(request, space_id, invitation_id):
    _enabled()
    space = _owner_space(request.user, space_id, "workspace.invites.manage")
    _strict(request.data, {"expected_invitation_version", "reason_code"})
    if not request.data.get("reason_code"):
        raise ValidationError({"reason_code": "This field is required."})
    body = revoke_invitation(
        actor=request.user,
        space=space,
        invitation_id=invitation_id,
        expected_version=_int(request.data, "expected_invitation_version"),
        reason_code=request.data.get("reason_code", ""),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invitation_redeem(request):
    _enabled()
    _strict(request.data, {"token", "action"})
    if not isinstance(request.data.get("token"), str) or not request.data["token"].strip():
        raise ValidationError({"token": "This field is required."})
    body = redeem_invitation(
        actor=request.user,
        raw_token=request.data.get("token"),
        action=request.data.get("action"),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def access_request_collection(request, space_id):
    _enabled()
    if request.method == "GET":
        space = _owner_space(
            request.user,
            space_id,
            "workspace.access_requests.manage",
        )
        rows = SpaceAccessRequest.objects.filter(space=space).select_related("user").order_by("-created_at")[:100]
        return Response({"results": [_request_body(row) for row in rows], "next_cursor": None})
    _strict(request.data, {"reason"})
    space = authorized_discovery_queryset(request.user).filter(pk=space_id).first()
    if space is None:
        raise NotFound("Workspace not found.")
    body = create_discovery_request(
        actor=request.user,
        space=space,
        reason=request.data.get("reason", ""),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body, status=202)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def access_request_decision(request, space_id, request_id, action):
    _enabled()
    if action == "approve":
        _strict(request.data, {"expected_request_version", "role"})
        if not request.data.get("role"):
            raise ValidationError({"role": "This field is required."})
    elif action == "reject":
        _strict(request.data, {"expected_request_version", "reason_code", "reason_text"})
    else:
        raise NotFound("Access-request action not found.")
    space = _owner_space(
        request.user,
        space_id,
        "workspace.access_requests.manage",
    )
    body = decide_access_request(
        actor=request.user,
        space=space,
        request_id=request_id,
        expected_version=_int(request.data, "expected_request_version"),
        action=action,
        role=request.data.get("role"),
        reason_code=request.data.get("reason_code", ""),
        reason_text=request.data.get("reason_text", ""),
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def join_by_code_view(request):
    """Join a workspace by its join code (simplified access_code mode)."""
    _enabled()
    _strict(request.data, {"join_code"})
    code = request.data.get("join_code")
    if not isinstance(code, str) or not code.strip():
        raise ValidationError({"join_code": "This field is required."})
    body = join_by_code(
        actor=request.user,
        join_code=code,
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def join_code_view(request, space_id):
    """View the join code for a workspace (active members only)."""
    _enabled()
    space = _active_member_space(request.user, space_id)
    return Response({
        "space_id": str(space.id),
        "join_policy": space.join_policy,
        "join_code": space.join_code,
        "allow_member_invite": space.allow_member_invite,
        "join_code_updated_at": (
            space.join_code_updated_at.isoformat()
            if space.join_code_updated_at
            else None
        ),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def join_code_regenerate_view(request, space_id):
    """Regenerate the join code for a workspace (owner/admin only)."""
    _enabled()
    _strict(request.data, {"custom_code"})
    custom_code = request.data.get("custom_code")
    body = regenerate_join_code(
        actor=request.user,
        space_id=space_id,
        custom_code=custom_code,
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def global_join_view(request, space_id):
    """Join a globally-visible workspace directly."""
    _enabled()
    body = global_join(
        actor=request.user,
        space_id=space_id,
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def discoverable_spaces_view(request):
    """List workspaces visible via global join policy."""
    _enabled()
    queryset = authorized_discovery_queryset(request.user).filter(
        join_policy=KnowledgeSpace.JOIN_POLICY_GLOBAL,
    )
    rows = list(
        queryset.values(
            "id",
            "name",
            "code",
            "description",
            "join_policy",
            "status",
        )[:100]
    )
    return Response({"results": rows, "next_cursor": None})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def join_policy_switch_view(request, space_id):
    """Switch the join policy of a workspace (owner/admin only)."""
    _enabled()
    _strict(request.data, {"join_policy"})
    new_policy = request.data.get("join_policy")
    if new_policy not in (
        KnowledgeSpace.JOIN_POLICY_ACCESS_CODE,
        KnowledgeSpace.JOIN_POLICY_GLOBAL,
    ):
        raise ValidationError({"join_policy": "Must be 'access_code' or 'global'."})
    body = switch_join_policy(
        actor=request.user,
        space_id=space_id,
        new_policy=new_policy,
        idempotency_key=require_idempotency_key(request),
    )
    if isinstance(body, Response):
        return body
    return Response(body)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def allow_member_invite_toggle_view(request, space_id):
    """Toggle allow_member_invite for a workspace (owner/admin only)."""
    _enabled()
    _strict(request.data, {"allow_member_invite"})
    space = _manage_space(request.user, space_id)
    value = request.data.get("allow_member_invite")
    if not isinstance(value, bool):
        raise ValidationError({"allow_member_invite": "Must be a boolean."})
    space.allow_member_invite = value
    space.save(update_fields=["allow_member_invite", "updated_at"])
    return Response({
        "space_id": str(space.id),
        "allow_member_invite": space.allow_member_invite,
    })


__all__ = [
    "access_code_request_submit",
    "access_request_mine",
    "access_request_cancel",
    "access_code_collection",
    "access_code_revoke",
    "invitation_collection",
    "invitation_revoke",
    "invitation_redeem",
    "access_request_collection",
    "access_request_decision",
    "join_by_code_view",
    "join_code_view",
    "join_code_regenerate_view",
    "global_join_view",
    "discoverable_spaces_view",
    "join_policy_switch_view",
    "allow_member_invite_toggle_view",
]
