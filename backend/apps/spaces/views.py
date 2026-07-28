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

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    InviteCode,
    KnowledgeSpace,
    Organization,
    SpaceAccessRequest,
    SpaceEmailInvite,
    SpaceMembership,
)
from .permissions import (
    SPACE_ARCHIVE,
    SPACE_INVITE,
    SPACE_MANAGE_MEMBERS,
    SPACE_UPDATE,
    SPACE_VIEW,
    accessible_spaces,
    admin_scope,
    can_create_space,
    can_restore_space,
    effective_space_role,
    get_space_or_404,
    has_space_permission,
    is_platform_admin,
)
from .serializers import (
    AddMemberByEmailSerializer,
    InviteCodeCreateSerializer,
    InviteCodeSerializer,
    JoinByCodeSerializer,
    KnowledgeSpaceSerializer,
    SpaceAccessRequestCreateSerializer,
    SpaceAccessRequestSerializer,
    SpaceCloneSerializer,
    SpaceCreateSerializer,
    SpaceMembershipSerializer,
    SpaceTransferSerializer,
    UpdateMemberRoleSerializer,
)
from .deletion_services import archive_workspace, restore_workspace

logger = logging.getLogger(__name__)

DEFAULT_SPACE_CODE = "general"


def _audit(user, action, target_id=None, details=None, request=None, role_used=None):
    """Best-effort audit log — never blocks the request on failure."""
    try:
        from apps.audit.views import create_audit_log
        create_audit_log(
            user=user,
            action=action,
            target_type=(
                "ScenarioTemplate"
                if action.startswith("template_")
                else "KnowledgeSpace"
            ),
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
    """GET accessible spaces; POST is the one-window governed adapter."""

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
        # The compatibility route must never restore direct creation.  It
        # delegates to the exact same typed service as
        # POST /spaces/creation-requests/ and therefore returns 202.
        from django.conf import settings

        from .creation_services import submit_creation_request
        from .governed import GovernedWorkflowError, require_idempotency_key

        if not bool(getattr(settings, "WORKSPACE_CREATION_APPROVAL", False)):
            raise GovernedWorkflowError(
                "workspace_creation_disabled",
                "Workspace creation is disabled.",
                status_code=503,
            )
        body = submit_creation_request(
            actor=request.user,
            payload=dict(request.data),
            idempotency_key=require_idempotency_key(request),
        )
        if isinstance(body, Response):
            return body
        return Response(body, status=status.HTTP_202_ACCEPTED)


class SpaceDetailView(generics.RetrieveUpdateAPIView):
    """GET: space detail (requires access). PATCH: update (space.update)."""

    serializer_class = KnowledgeSpaceSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_object(self):
        space = get_space_or_404(self.kwargs["pk"])
        archived_owner_read = (
            self.request.method == "GET"
            and space.status == "archived"
            and can_restore_space(self.request.user, space)
        )
        if effective_space_role(self.request.user, space) is None and not archived_owner_read:
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
    # The compatibility route keeps its empty-body shape, while the service
    # rechecks the canonical owner and lifecycle version under the global lock
    # order. Platform/governance authority never substitutes for ownership.
    space = archive_workspace(actor=request.user, space_id=pk)
    return Response(KnowledgeSpaceSerializer(space, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_restore(request, pk):
    space = restore_workspace(actor=request.user, space_id=pk)
    return Response(KnowledgeSpaceSerializer(space, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_transfer(request, pk):
    space = get_space_or_404(pk)
    role = effective_space_role(request.user, space)
    if role not in {"owner", "super_admin", "org_admin", "business_admin"}:
        raise PermissionDenied("You cannot transfer this space.")
    serializer = SpaceTransferSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if "organization" in serializer.validated_data:
        if serializer.validated_data["organization"].id != space.organization_id:
            raise PermissionDenied("Cross-organization transfer is not supported.")
    business_line = serializer.validated_data.get("business_line")
    if business_line is None:
        raise ValidationError({"business_line": "A target business line is required."})
    if business_line.organization_id != space.organization_id:
        raise PermissionDenied("Target business line must be in the same organization.")
    if role == "business_admin":
        _, line_ids = admin_scope(request.user)
        if space.business_line_id not in line_ids or business_line.id not in line_ids:
            raise PermissionDenied("Business administrators may only transfer inside their line.")
    space.business_line = business_line
    space.save(update_fields=["business_line", "updated_at"])
    _audit(request.user, "space_transfer", target_id=space.id, details={"business_line": str(business_line.id)}, request=request)
    return Response(KnowledgeSpaceSerializer(space, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_clone(request, pk):
    space = get_space_or_404(pk)
    if effective_space_role(request.user, space) not in {"owner", "super_admin", "org_admin", "business_admin"}:
        raise PermissionDenied("You cannot clone this space.")
    serializer = SpaceCloneSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    from .ownership import create_space_with_owner

    with transaction.atomic():
        clone = create_space_with_owner(
            organization=space.organization,
            owner=request.user,
            business_line=space.business_line,
            name=serializer.validated_data["name"],
            code=serializer.validated_data["code"],
            description=space.description,
            icon=space.icon,
            language=space.language,
            visibility=space.visibility,
            settings=space.settings,
        )
    copied = []
    if serializer.validated_data["copy_documents"]:
        from apps.knowledge.ingestion import enqueue_document_ingestion
        from apps.knowledge.models import Document
        for source in space.documents.filter(status="active").select_related("category"):
            try:
                with source.file.open("rb") as source_file:
                    copied_file = ContentFile(source_file.read(), name=source.file.name.rsplit("/", 1)[-1])
                document = Document.objects.create(
                    space=clone, title=source.title, file=copied_file,
                    file_type=source.file_type, file_size=source.file_size,
                    category=source.category, tags=source.tags, status="processing",
                    version=source.version, effective_from=source.effective_from,
                    effective_to=source.effective_to, uploaded_by=request.user,
                    parent_document=source, content_hash=source.content_hash,
                )
                job = enqueue_document_ingestion(document, requested_by=request.user, trigger="upload")
                copied.append({"document_id": str(document.id), "job_id": str(job.id)})
            except Exception as exc:
                _audit(request.user, "space_clone_document_failure", target_id=clone.id, details={"source_document": str(source.id), "error": exc.__class__.__name__}, request=request)
    _audit(request.user, "space_clone", target_id=clone.id, details={"source_space": str(space.id), "copied_documents": len(copied)}, request=request)
    data = KnowledgeSpaceSerializer(clone, context={"request": request}).data
    data["copied_documents"] = copied
    return Response(data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_access_request(request, pk):
    space = get_space_or_404(pk)
    if space.visibility == "private" or space.status != "active":
        raise PermissionDenied("This space does not accept access requests.")
    if effective_space_role(request.user, space) is not None:
        raise ValidationError({"detail": "You already have access to this space."})
    serializer = SpaceAccessRequestCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    access_request, created = SpaceAccessRequest.objects.get_or_create(
        space=space,
        user=request.user,
        status=SpaceAccessRequest.STATUS_PENDING,
        defaults=serializer.validated_data,
    )
    _audit(request.user, "space_access_request", target_id=space.id, request=request)
    return Response(
        SpaceAccessRequestSerializer(access_request).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def discoverable_spaces(request):
    """List requestable spaces inside organizations the user already belongs to.

    Membership in any space establishes tenant membership; private spaces and
    spaces already joined are never exposed as join candidates.
    """
    if request.query_params.get("contract_version") == "2":
        from .discovery import discover

        params = {
            key: request.query_params.get(key)
            for key in (
                "q",
                "business_line_id",
                "work_group_id",
                "access_state",
                "sort",
                "cursor",
            )
            if request.query_params.get(key) is not None
        }
        office_ids = request.query_params.getlist("office_location_id")
        if office_ids:
            params["office_location_ids"] = office_ids
        return Response(discover(request.user, params))

    memberships = SpaceMembership.objects.filter(user=request.user, status="active")
    organization_ids = memberships.values_list("space__organization_id", flat=True)
    business_line_ids = set(
        memberships.exclude(space__business_line_id=None).values_list(
            "space__business_line_id", flat=True
        )
    )
    # Spec §1: the registered business line also unlocks that line's spaces.
    if getattr(request.user, "business_line_id", None):
        business_line_ids.add(request.user.business_line_id)
    joined_ids = memberships.values_list("space_id", flat=True)
    spaces = KnowledgeSpace.objects.filter(
        status="active",
        organization__status="active",
    ).filter(
        Q(visibility="organization", organization_id__in=organization_ids)
        | Q(visibility="business_line", business_line_id__in=business_line_ids)
    ).exclude(id__in=joined_ids).select_related("organization", "business_line").order_by("name")
    return Response(KnowledgeSpaceSerializer(spaces, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def discovery_highlights(request):
    from .discovery import highlights

    return Response(highlights(request.user))


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
    # Persist the switched space as the user's default so subsequent
    # page loads and the frontend ProtectedRoute know the user has a space.
    if request.user.default_space_id != space.id:
        request.user.default_space = space
        request.user.save(update_fields=["default_space"])
    from .discovery import record_authorized_usage

    record_authorized_usage(user=request.user, space=space)
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
        # Bug fix: first joined space becomes the user's default so the
        # frontend no longer treats the new member as spaceless.
        from .services import ensure_default_space

        ensure_default_space(request.user, space)

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


class SpaceMembersView(generics.ListCreateAPIView):
    """GET: list members (space.view). POST: add a member by email (space.manage_members).

    V7.0: adding by email is the admin path that lets a teammate maintain the
    knowledge base. If the email already has an account, an active membership is
    created and the user is notified; otherwise a pending SpaceEmailInvite is
    created and redeemed automatically when that email registers.
    """

    serializer_class = SpaceMembershipSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        from django.conf import settings

        if bool(getattr(settings, "WORKSPACE_JOIN_V2", False)):
            from .member_services import list_members

            space = get_space_or_404(self.kwargs["pk"])
            return Response(list_members(actor=request.user, space=space))
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        space = get_space_or_404(self.kwargs["pk"])
        if not has_space_permission(self.request.user, space, SPACE_VIEW):
            from rest_framework.exceptions import NotFound
            raise NotFound("Space not found.")
        return SpaceMembership.objects.filter(space=space).select_related("user")

    def create(self, request, *args, **kwargs):
        from django.conf import settings

        if bool(getattr(settings, "WORKSPACE_JOIN_V2", False)):
            from rest_framework.exceptions import MethodNotAllowed

            raise MethodNotAllowed(
                "POST",
                detail="Use the targeted invitations or access-request workflow.",
            )
        space = get_space_or_404(self.kwargs["pk"])
        if not has_space_permission(request.user, space, SPACE_MANAGE_MEMBERS):
            _audit(request.user, "permission_denied", target_id=space.id,
                   details={"action": SPACE_MANAGE_MEMBERS}, request=request)
            raise PermissionDenied("You cannot manage members of this space.")

        if request.data.get("role") == SpaceMembership.ROLE_OWNER:
            return Response(
                {"error_code": "ownership_workflow_required"},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = AddMemberByEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        role = serializer.validated_data["role"]

        from django.contrib.auth import get_user_model
        User = get_user_model()
        target = User.objects.filter(email__iexact=email).first()

        if target is not None:
            membership, created = SpaceMembership.objects.get_or_create(
                space=space, user=target,
                defaults={"role": role, "status": "active",
                          "invited_by": request.user, "last_accessed_at": timezone.now()},
            )
            if not created:
                membership.role = role
                membership.status = "active"
                membership.save(update_fields=["role", "status", "updated_at"])
            _audit(request.user, "space_member_add", target_id=space.id,
                   details={"member": email, "role": role, "pending": False}, request=request)
            try:
                from apps.notifications.services import notify
                notify(target, "space_invite",
                       title=f"You were added to {space.name}",
                       body=f"Your role: {role}.", link="/chat",
                       metadata={"space_id": str(space.id), "role": role})
            except Exception:
                pass
            return Response(
                {"pending": False, "member": SpaceMembershipSerializer(membership).data},
                status=status.HTTP_201_CREATED,
            )

        # No account yet — create/refresh a pending email invite.
        invite, _ = SpaceEmailInvite.objects.update_or_create(
            space=space, email=email,
            defaults={"role": role, "status": "pending", "invited_by": request.user},
        )
        _audit(request.user, "space_email_invite", target_id=space.id,
               details={"member": email, "role": role, "pending": True}, request=request)
        return Response(
            {"pending": True, "email": email, "role": role},
            status=status.HTTP_201_CREATED,
        )


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def space_member_detail(request, pk, user_id):
    """PATCH: change a member's role. DELETE: remove (revoke) a member.

    Both require space.manage_members. A space must always keep at least one
    active owner, so the last owner cannot be downgraded or removed.
    """
    from django.conf import settings

    if bool(getattr(settings, "WORKSPACE_JOIN_V2", False)):
        from .governed import require_idempotency_key
        from .member_services import remove_member, update_member

        if not isinstance(request.data, dict):
            raise ValidationError({"detail": "A JSON object is required."})
        if request.method == "PATCH":
            allowed = {
                "expected_membership_version",
                "role",
                "status",
                "expires_at",
                "reason_code",
                "reason_text",
            }
            unknown = sorted(set(request.data) - allowed)
            if unknown:
                raise ValidationError({"unknown_fields": unknown})
            try:
                expected = int(request.data.get("expected_membership_version"))
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    {"expected_membership_version": "Must be an integer."}
                ) from exc
            fields = {
                field: request.data[field]
                for field in ("role", "status", "expires_at")
                if field in request.data
            }
            body = update_member(
                actor=request.user,
                space_id=pk,
                membership_id=user_id,
                expected_version=expected,
                fields=fields,
                reason_code=request.data.get("reason_code", ""),
                reason_text=request.data.get("reason_text", ""),
                idempotency_key=require_idempotency_key(request),
            )
        else:
            unknown = sorted(set(request.data) - {"reason_code", "reason_text"})
            if unknown:
                raise ValidationError({"unknown_fields": unknown})
            etag = (request.headers.get("If-Match") or "").strip()
            prefix = '"membership-v'
            if not (etag.startswith(prefix) and etag.endswith('"')):
                raise ValidationError({"If-Match": 'Expected "membership-vN".'})
            try:
                expected = int(etag[len(prefix) : -1])
            except ValueError as exc:
                raise ValidationError({"If-Match": 'Expected "membership-vN".'}) from exc
            body = remove_member(
                actor=request.user,
                space_id=pk,
                membership_id=user_id,
                expected_version=expected,
                reason_code=request.data.get("reason_code", ""),
                reason_text=request.data.get("reason_text", ""),
                idempotency_key=require_idempotency_key(request),
            )
        if isinstance(body, Response):
            return body
        return Response(body)

    space = get_space_or_404(pk)
    if not has_space_permission(request.user, space, SPACE_MANAGE_MEMBERS):
        _audit(request.user, "permission_denied", target_id=space.id,
               details={"action": SPACE_MANAGE_MEMBERS}, request=request)
        raise PermissionDenied("You cannot manage members of this space.")

    membership = SpaceMembership.objects.filter(space=space, user_id=user_id).first()
    if membership is None:
        from rest_framework.exceptions import NotFound
        raise NotFound("Member not found.")

    def _is_last_owner() -> bool:
        # The canonical owner FK is authoritative during and after the
        # compatibility period. A corrupt legacy owner mirror must never make
        # the canonical owner removable through member-management endpoints.
        if membership.user_id == space.owner_id:
            return True
        if membership.role != SpaceMembership.ROLE_OWNER:
            return False
        owners = SpaceMembership.objects.filter(
            space=space, role=SpaceMembership.ROLE_OWNER, status="active"
        ).exclude(pk=membership.pk).exists()
        return not owners

    if request.method == "DELETE":
        if _is_last_owner():
            raise ValidationError({"detail": "Cannot remove the last owner of a space."})
        membership.status = "revoked"
        membership.save(update_fields=["status", "updated_at"])
        _audit(request.user, "space_member_remove", target_id=space.id,
               details={"member_user_id": str(user_id)}, request=request)
        return Response({"removed": True})

    # PATCH — change role
    if request.data.get("role") == SpaceMembership.ROLE_OWNER:
        return Response(
            {"error_code": "ownership_workflow_required"},
            status=status.HTTP_409_CONFLICT,
        )
    serializer = UpdateMemberRoleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    new_role = serializer.validated_data["role"]
    if _is_last_owner() and new_role != SpaceMembership.ROLE_OWNER:
        raise ValidationError({"detail": "Cannot downgrade the last owner of a space."})
    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])
    _audit(request.user, "space_member_update", target_id=space.id,
           details={"member_user_id": str(user_id), "role": new_role}, request=request)
    return Response(SpaceMembershipSerializer(membership).data)


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
