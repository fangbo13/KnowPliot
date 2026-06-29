# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Space platform views — V6.0 (SPEC.MD §6.1).

All endpoints are server-side permission-checked. Listing returns only spaces
the user may access; create/update/archive/invite require the matching space
permission; joining by code creates a membership but never bypasses RBAC.
"""

import hashlib
import logging
import secrets

from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import InviteCode, KnowledgeSpace, Organization, SpaceMembership
from .permissions import (
    SPACE_ARCHIVE,
    SPACE_INVITE,
    SPACE_MANAGE_MEMBERS,
    SPACE_UPDATE,
    SPACE_VIEW,
    accessible_spaces,
    can_create_space,
    effective_space_role,
    get_space_or_404,
    has_space_permission,
    is_platform_admin,
)
from .serializers import (
    InviteCodeCreateSerializer,
    InviteCodeSerializer,
    JoinByCodeSerializer,
    KnowledgeSpaceSerializer,
    SpaceCreateSerializer,
    SpaceMembershipSerializer,
)

logger = logging.getLogger(__name__)

DEFAULT_SPACE_CODE = "general"


def _audit(user, action, target_id=None, details=None, request=None, role_used=None):
    """Best-effort audit log — never blocks the request on failure."""
    try:
        from apps.audit.views import create_audit_log
        create_audit_log(
            user=user,
            action=action,
            target_type="KnowledgeSpace",
            target_id=target_id,
            details=details or {},
            role_used=role_used or "",
            request=request,
        )
    except Exception as exc:  # pragma: no cover - logging must not break flow
        logger.warning("Audit log failed for %s: %s", action, exc)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def ensure_default_membership(user):
    """Lazily attach a user with no spaces to the default 'general' space.

    Preserves the pre-V6.0 single-knowledge-base UX: everyone always lands in
    at least one space. Platform admins implicitly see all spaces, so they are
    skipped.
    """
    if is_platform_admin(user):
        return
    if SpaceMembership.objects.filter(user=user, status="active").exists():
        return
    space = KnowledgeSpace.objects.filter(code=DEFAULT_SPACE_CODE).first()
    if space:
        SpaceMembership.objects.get_or_create(
            space=space, user=user,
            defaults={"role": SpaceMembership.ROLE_MEMBER, "status": "active"},
        )


class SpaceListCreateView(generics.ListCreateAPIView):
    """GET: list accessible spaces. POST: create a space (platform admins)."""

    permission_classes = [IsAuthenticated]
    pagination_class = None  # space lists are small; return all for the switcher

    def get_serializer_class(self):
        return SpaceCreateSerializer if self.request.method == "POST" else KnowledgeSpaceSerializer

    def get_queryset(self):
        ensure_default_membership(self.request.user)
        return accessible_spaces(self.request.user).select_related(
            "organization", "business_line"
        )

    def create(self, request, *args, **kwargs):
        if not can_create_space(request.user):
            _audit(request.user, "permission_denied",
                   details={"action": "space.create"}, request=request)
            raise PermissionDenied("You are not allowed to create spaces.")

        serializer = SpaceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = serializer.validated_data.get("organization")
        if organization is None:
            organization = (
                Organization.objects.filter(slug="default").first()
                or Organization.objects.first()
            )
            if organization is None:
                organization = Organization.objects.create(name="Default Organization", slug="default")

        with transaction.atomic():
            space = serializer.save(organization=organization, created_by=request.user)
            # Creator becomes the space owner.
            SpaceMembership.objects.create(
                space=space, user=request.user,
                role=SpaceMembership.ROLE_OWNER, status="active",
                last_accessed_at=timezone.now(),
            )
        _audit(request.user, "space_create", target_id=space.id,
               details={"code": space.code, "name": space.name}, request=request)
        out = KnowledgeSpaceSerializer(space, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class SpaceDetailView(generics.RetrieveUpdateAPIView):
    """GET: space detail (requires access). PATCH: update (space.update)."""

    serializer_class = KnowledgeSpaceSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_object(self):
        space = get_space_or_404(self.kwargs["pk"])
        if effective_space_role(self.request.user, space) is None:
            from rest_framework.exceptions import NotFound
            raise NotFound("Space not found.")
        if self.request.method in ("PATCH", "PUT"):
            if not has_space_permission(self.request.user, space, SPACE_UPDATE):
                _audit(self.request.user, "permission_denied", target_id=space.id,
                       details={"action": SPACE_UPDATE}, request=self.request)
                raise PermissionDenied("You cannot update this space.")
        return space

    def perform_update(self, serializer):
        space = serializer.save()
        _audit(self.request.user, "space_update", target_id=space.id,
               details={"fields": list(self.request.data.keys())}, request=self.request)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_archive(request, pk):
    space = get_space_or_404(pk)
    if not has_space_permission(request.user, space, SPACE_ARCHIVE):
        _audit(request.user, "permission_denied", target_id=space.id,
               details={"action": SPACE_ARCHIVE}, request=request)
        raise PermissionDenied("You cannot archive this space.")
    space.status = "archived"
    space.save(update_fields=["status", "updated_at"])
    _audit(request.user, "space_archive", target_id=space.id, request=request)
    return Response(KnowledgeSpaceSerializer(space, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_switch(request, pk):
    """Set the active/default space — records last access for default routing."""
    space = get_space_or_404(pk)
    role = effective_space_role(request.user, space)
    if role is None:
        from rest_framework.exceptions import NotFound
        raise NotFound("Space not found.")
    SpaceMembership.objects.filter(space=space, user=request.user).update(
        last_accessed_at=timezone.now()
    )
    _audit(request.user, "space_switch", target_id=space.id,
           details={"code": space.code}, request=request, role_used=role)
    return Response(KnowledgeSpaceSerializer(space, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_join(request):
    """Join a space by access/invite code (SPEC.MD §3.3).

    The code creates or re-activates a membership with the code's role. It is an
    *entry* mechanism: the granted role still flows through normal RBAC checks.
    """
    serializer = JoinByCodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    code = serializer.validated_data["code"]

    invite = InviteCode.objects.filter(code_hash=_hash_code(code)).select_related("space").first()
    if invite is None or not invite.is_valid():
        _audit(request.user, "permission_denied",
               details={"action": "space.join", "reason": "invalid_or_expired_code"},
               request=request)
        raise ValidationError({"code": "Invalid or expired access code."})

    space = invite.space
    with transaction.atomic():
        membership, created = SpaceMembership.objects.get_or_create(
            space=space, user=request.user,
            defaults={"role": invite.role, "status": "active",
                      "invited_by": invite.created_by, "last_accessed_at": timezone.now()},
        )
        if not created:
            # Re-activate a revoked/pending membership; never downgrade an
            # existing higher role granted by an admin.
            if membership.status != "active":
                membership.status = "active"
            membership.last_accessed_at = timezone.now()
            membership.save(update_fields=["status", "last_accessed_at", "updated_at"])
        # Count the use.
        InviteCode.objects.filter(pk=invite.pk).update(used_count=invite.used_count + 1)

    _audit(request.user, "space_join", target_id=space.id,
           details={"code_prefix": invite.code_prefix, "role": invite.role, "new_member": created},
           request=request, role_used=invite.role)
    return Response(
        {
            "joined": True,
            "space": KnowledgeSpaceSerializer(space, context={"request": request}).data,
        },
        status=status.HTTP_200_OK,
    )


class SpaceMembersView(generics.ListAPIView):
    """List members of a space (requires space.view)."""

    serializer_class = SpaceMembershipSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        space = get_space_or_404(self.kwargs["pk"])
        if not has_space_permission(self.request.user, space, SPACE_VIEW):
            from rest_framework.exceptions import NotFound
            raise NotFound("Space not found.")
        return SpaceMembership.objects.filter(space=space).select_related("user")


class InviteCodeListCreateView(generics.ListCreateAPIView):
    """List / create invite codes for a space (requires space.invite)."""

    permission_classes = [IsAuthenticated]
    pagination_class = None

    def _space(self):
        return get_space_or_404(self.kwargs["pk"])

    def get_queryset(self):
        space = self._space()
        if not has_space_permission(self.request.user, space, SPACE_INVITE):
            from rest_framework.exceptions import NotFound
            raise NotFound("Space not found.")
        return InviteCode.objects.filter(space=space)

    def get_serializer_class(self):
        return InviteCodeCreateSerializer if self.request.method == "POST" else InviteCodeSerializer

    def create(self, request, *args, **kwargs):
        space = self._space()
        if not has_space_permission(request.user, space, SPACE_INVITE):
            _audit(request.user, "permission_denied", target_id=space.id,
                   details={"action": SPACE_INVITE}, request=request)
            raise PermissionDenied("You cannot create invite codes for this space.")

        serializer = InviteCodeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Generate a human-friendly code: "<SPACECODE>-<random>".
        raw = f"{space.code[:6].upper()}-{secrets.token_urlsafe(8)}"
        invite = InviteCode.objects.create(
            space=space,
            code_hash=_hash_code(raw),
            code_prefix=raw[:8],
            role=serializer.validated_data["role"],
            expires_at=serializer.validated_data.get("expires_at"),
            max_uses=serializer.validated_data.get("max_uses", 0),
            created_by=request.user,
        )
        _audit(request.user, "space_invite_create", target_id=space.id,
               details={"role": invite.role, "code_prefix": invite.code_prefix}, request=request)
        data = InviteCodeSerializer(invite).data
        # Plaintext code is returned exactly once, on creation.
        data["code"] = raw
        return Response(data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invite_revoke(request, pk, invite_id):
    space = get_space_or_404(pk)
    if not has_space_permission(request.user, space, SPACE_INVITE):
        _audit(request.user, "permission_denied", target_id=space.id,
               details={"action": SPACE_INVITE}, request=request)
        raise PermissionDenied("You cannot manage invite codes for this space.")
    invite = InviteCode.objects.filter(pk=invite_id, space=space).first()
    if invite is None:
        from rest_framework.exceptions import NotFound
        raise NotFound("Invite code not found.")
    invite.status = "revoked"
    invite.save(update_fields=["status"])
    _audit(request.user, "space_invite_revoke", target_id=space.id,
           details={"code_prefix": invite.code_prefix}, request=request)
    return Response({"revoked": True})
