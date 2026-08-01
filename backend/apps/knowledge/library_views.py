# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""KB optimization spec §3.2 — platform-official reference libraries API.

Endpoints:
    GET/POST  /api/v1/documents/libraries/            (platform admin)
    PATCH     /api/v1/documents/libraries/{id}/        (platform admin)
    GET       /api/v1/documents/libraries/catalog/     (any authenticated)
    GET/POST  /api/v1/documents/library-references/    (space-scoped)
    DELETE    /api/v1/documents/library-references/{id}/

A reference library is a KnowledgeSpace certified by a platform admin. Other
spaces opt in via SpaceLibraryReference; the RAG pipeline then reads across the
isolation boundary for those libraries only (retrieval path, read-only).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.audit.views import create_audit_log
from apps.spaces.models import KnowledgeSpace, SpaceMembership
from apps.spaces.permissions import (
    effective_space_role,
    is_platform_admin,
    resolve_request_space,
)

from .models import ReferenceLibrary, SpaceLibraryReference, UserReferenceLibraryFavorite

LIBRARY_ADMIN_ROLES = {"owner", "space_admin"}


# ── Serializers ──────────────────────────────────────────────────────


class ReferenceLibrarySerializer(serializers.ModelSerializer):
    space_name = serializers.CharField(source="space.name", read_only=True)
    space_code = serializers.CharField(source="space.code", read_only=True)
    is_favorite = serializers.SerializerMethodField()
    favorite_position = serializers.SerializerMethodField()

    def _favorite(self, obj):
        return self.context.get("favorites", {}).get(str(obj.id))

    def get_is_favorite(self, obj):
        return self._favorite(obj) is not None

    def get_favorite_position(self, obj):
        favorite = self._favorite(obj)
        return favorite.position if favorite else None

    class Meta:
        model = ReferenceLibrary
        fields = [
            "id", "space", "space_name", "space_code", "name", "description",
            "category", "status", "is_official", "is_favorite",
            "favorite_position", "published_at", "created_at",
        ]
        read_only_fields = ["id", "space_name", "space_code", "published_at", "created_at"]


class SpaceLibraryReferenceSerializer(serializers.ModelSerializer):
    library_name = serializers.CharField(source="library.name", read_only=True)
    library_category = serializers.CharField(source="library.category", read_only=True)
    library_status = serializers.CharField(source="library.status", read_only=True)

    class Meta:
        model = SpaceLibraryReference
        fields = [
            "id", "space", "library", "library_name", "library_category",
            "library_status", "enabled", "created_at",
        ]
        read_only_fields = ["id", "space", "created_at"]


def _require_platform_admin(request):
    if not is_platform_admin(request.user):
        raise PermissionDenied("Reference library management requires a platform admin.")


def _require_space_library_admin(request, space):
    if is_platform_admin(request.user):
        return
    if effective_space_role(request.user, space) not in LIBRARY_ADMIN_ROLES:
        raise PermissionDenied("Managing references requires knowledge admin rights.")


def _require_reference_library_user(request):
    if is_platform_admin(request.user):
        return
    allowed_roles = {
            SpaceMembership.ROLE_MEMBER,
            SpaceMembership.ROLE_SPACE_ADMIN,
            SpaceMembership.ROLE_OWNER,
    }
    requested_space_id = request.headers.get("X-Space-Id")
    if requested_space_id:
        space = resolve_request_space(request)
        allowed = effective_space_role(request.user, space) in allowed_roles
    else:
        allowed = SpaceMembership.objects.filter(
            user=request.user,
            status="active",
            role__in=allowed_roles,
        ).exists()
    if not allowed:
        raise PermissionDenied("Complete space onboarding to use reference libraries.")


# ── Platform-admin library management ────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def libraries(request):
    """List all reference libraries / certify a space as one (platform admin)."""
    _require_platform_admin(request)
    if request.method == "GET":
        qs = ReferenceLibrary.objects.select_related("space").order_by("name")
        return Response(ReferenceLibrarySerializer(qs, many=True).data)

    space_id = request.data.get("space")
    if not space_id:
        raise ValidationError({"space": "A space id is required."})
    try:
        space = KnowledgeSpace.objects.get(pk=space_id)
    except (KnowledgeSpace.DoesNotExist, ValueError, TypeError):
        raise ValidationError({"space": "Unknown space."}) from None
    if ReferenceLibrary.objects.filter(space=space).exists():
        raise ValidationError({"space": "This space is already a reference library."})
    serializer = ReferenceLibrarySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    requested_status = serializer.validated_data.get(
        "status", ReferenceLibrary.STATUS_UNPUBLISHED
    )
    is_official = serializer.validated_data.get(
        "is_official", requested_status == ReferenceLibrary.STATUS_PUBLISHED
    )
    library = serializer.save(
        space=space,
        is_official=is_official,
        status=(
            ReferenceLibrary.STATUS_PUBLISHED
            if is_official
            else ReferenceLibrary.STATUS_UNPUBLISHED
        ),
        published_at=timezone.now() if is_official else None,
        published_by=request.user if is_official else None,
    )
    create_audit_log(
        user=request.user, action="admin_action", target_type="ReferenceLibrary",
        target_id=str(library.id),
        details={"op": "library_create", "space": str(space.id), "category": library.category},
        request=request,
    )
    return Response(ReferenceLibrarySerializer(library).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def library_detail(request, pk):
    """Publish / unpublish / rename / remove a reference library (platform admin)."""
    _require_platform_admin(request)
    try:
        library = ReferenceLibrary.objects.select_related("space").get(pk=pk)
    except ReferenceLibrary.DoesNotExist:
        raise NotFound("Reference library not found.") from None

    if request.method == "GET":
        return Response(ReferenceLibrarySerializer(library).data)

    if request.method == "DELETE":
        library.delete()
        create_audit_log(
            user=request.user, action="admin_action", target_type="ReferenceLibrary",
            target_id=str(pk), details={"op": "library_delete"}, request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    allowed = {"name", "description", "category", "status", "is_official"}
    updates = {k: v for k, v in request.data.items() if k in allowed}
    if not updates:
        raise ValidationError({"detail": "No editable fields supplied."})
    if "status" in updates:
        if updates["status"] not in {
            ReferenceLibrary.STATUS_PUBLISHED,
            ReferenceLibrary.STATUS_UNPUBLISHED,
        }:
            raise ValidationError({"status": "Must be 'published' or 'unpublished'."})
        if updates["status"] == ReferenceLibrary.STATUS_PUBLISHED and not library.published_at:
            library.published_at = timezone.now()
            library.published_by = request.user
        updates["is_official"] = updates["status"] == ReferenceLibrary.STATUS_PUBLISHED
    if "is_official" in updates:
        if not isinstance(updates["is_official"], bool):
            raise ValidationError({"is_official": "Provide a boolean."})
        updates["status"] = (
            ReferenceLibrary.STATUS_PUBLISHED
            if updates["is_official"]
            else ReferenceLibrary.STATUS_UNPUBLISHED
        )
        if updates["is_official"] and not library.published_at:
            library.published_at = timezone.now()
            library.published_by = request.user
    for field, value in updates.items():
        setattr(library, field, value)
    library.save()
    if not library.is_official:
        UserReferenceLibraryFavorite.objects.filter(library=library).delete()
    create_audit_log(
        user=request.user, action="admin_action", target_type="ReferenceLibrary",
        target_id=str(library.id),
        details={"op": "library_update", "fields": sorted(updates.keys()), "status": library.status},
        request=request,
    )
    return Response(ReferenceLibrarySerializer(library).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def libraries_catalog(request):
    """Compatibility catalog for member-or-higher users."""
    _require_reference_library_user(request)
    qs = ReferenceLibrary.objects.filter(
        is_official=True
    ).select_related("space").order_by("category", "name")
    favorites = {
        str(favorite.library_id): favorite
        for favorite in UserReferenceLibraryFavorite.objects.filter(user=request.user)
    }
    return Response(ReferenceLibrarySerializer(qs, many=True, context={"favorites": favorites}).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def user_reference_libraries(request):
    """Return the global official catalog with this user's favorites first."""
    _require_reference_library_user(request)
    favorites = {
        str(favorite.library_id): favorite
        for favorite in UserReferenceLibraryFavorite.objects.filter(user=request.user)
    }
    libraries = list(ReferenceLibrary.objects.filter(is_official=True).select_related("space"))
    libraries.sort(
        key=lambda library: (
            0 if str(library.id) in favorites else 1,
            favorites[str(library.id)].position if str(library.id) in favorites else 99,
            library.category,
            library.name.casefold(),
        )
    )
    return Response(
        ReferenceLibrarySerializer(
            libraries, many=True, context={"favorites": favorites}
        ).data
    )


@api_view(["POST", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def user_reference_library_favorite(request, pk):
    """Create/update or remove one of a user's five global shortcuts."""
    _require_reference_library_user(request)
    try:
        library = ReferenceLibrary.objects.get(pk=pk, is_official=True)
    except (ReferenceLibrary.DoesNotExist, ValueError, TypeError):
        raise NotFound("Official reference library not found.") from None

    if request.method == "DELETE":
        UserReferenceLibraryFavorite.objects.filter(
            user=request.user, library=library
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        existing = UserReferenceLibraryFavorite.objects.filter(
            user=request.user, library=library
        ).first()
        if existing is None and UserReferenceLibraryFavorite.objects.filter(
            user=request.user
        ).count() >= 5:
            raise ValidationError({"detail": "A user can favorite at most 5 libraries."})

        requested_position = request.data.get("position")
        if requested_position is None:
            used = set(
                UserReferenceLibraryFavorite.objects.filter(user=request.user)
                .exclude(library=library)
                .values_list("position", flat=True)
            )
            position = next(value for value in range(1, 6) if value not in used)
        else:
            try:
                position = int(requested_position)
            except (TypeError, ValueError):
                raise ValidationError(
                    {"position": "Use an integer from 1 to 5."}
                ) from None
            if position not in range(1, 6):
                raise ValidationError({"position": "Use an integer from 1 to 5."})
            if UserReferenceLibraryFavorite.objects.filter(
                user=request.user, position=position
            ).exclude(library=library).exists():
                raise ValidationError({"position": "That favorite position is in use."})

        favorite, created = UserReferenceLibraryFavorite.objects.update_or_create(
            user=request.user,
            library=library,
            defaults={"position": position},
        )
    payload = ReferenceLibrarySerializer(
        library, context={"favorites": {str(library.id): favorite}}
    ).data
    return Response(
        payload,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ── Space-scoped reference management ────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def library_references(request):
    """List / add reference libraries the active space (X-Space-Id) consumes."""
    space = resolve_request_space(request)
    if request.method == "GET":
        qs = SpaceLibraryReference.objects.filter(space=space).select_related("library")
        return Response(SpaceLibraryReferenceSerializer(qs, many=True).data)

    _require_space_library_admin(request, space)
    library_id = request.data.get("library")
    if not library_id:
        raise ValidationError({"library": "A library id is required."})
    try:
        library = ReferenceLibrary.objects.get(
            pk=library_id, is_official=True
        )
    except (ReferenceLibrary.DoesNotExist, ValueError, TypeError):
        raise ValidationError(
            {"library": "Unknown or unpublished library."}
        ) from None
    if library.space_id == space.id:
        raise ValidationError({"library": "A space cannot reference its own library."})
    reference, created = SpaceLibraryReference.objects.get_or_create(
        space=space, library=library, defaults={"added_by": request.user, "enabled": True}
    )
    if not created and not reference.enabled:
        reference.enabled = True
        reference.save(update_fields=["enabled", "updated_at"])
    create_audit_log(
        user=request.user, action="admin_action", target_type="SpaceLibraryReference",
        target_id=str(reference.id),
        details={"op": "library_reference_add", "library": str(library.id)},
        request=request,
    )
    return Response(
        SpaceLibraryReferenceSerializer(reference).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def library_reference_detail(request, pk):
    """Toggle enabled / remove a space's reference (owner/knowledge_admin)."""
    space = resolve_request_space(request)
    _require_space_library_admin(request, space)
    try:
        reference = SpaceLibraryReference.objects.get(pk=pk, space=space)
    except SpaceLibraryReference.DoesNotExist:
        raise NotFound("Reference not found.") from None

    if request.method == "DELETE":
        reference.delete()
        create_audit_log(
            user=request.user, action="admin_action", target_type="SpaceLibraryReference",
            target_id=str(pk), details={"op": "library_reference_remove"}, request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    enabled = request.data.get("enabled")
    if not isinstance(enabled, bool):
        raise ValidationError({"enabled": "Provide a boolean."})
    reference.enabled = enabled
    reference.save(update_fields=["enabled", "updated_at"])
    create_audit_log(
        user=request.user, action="admin_action", target_type="SpaceLibraryReference",
        target_id=str(reference.id),
        details={"op": "library_reference_toggle", "enabled": enabled},
        request=request,
    )
    return Response(SpaceLibraryReferenceSerializer(reference).data)


def resolve_reference_space_ids(space) -> list[str]:
    """Return space ids of the published libraries this space actively references.

    Used by the RAG pipeline to expand retrieval across the isolation boundary
    for opted-in, still-published libraries only.
    """
    return [
        str(space_id)
        for space_id in SpaceLibraryReference.objects.filter(
            space=space,
            enabled=True,
            library__is_official=True,
        ).values_list("library__space_id", flat=True)
    ]
