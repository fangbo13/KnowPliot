# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §2 — taxonomy API.

Endpoints:
    GET/POST  /api/v1/documents/taxonomy/dimensions/
    PATCH     /api/v1/documents/taxonomy/dimensions/{id}/
    GET/POST  /api/v1/documents/taxonomy/terms/
    PATCH     /api/v1/documents/taxonomy/terms/{id}/
    POST      /api/v1/documents/taxonomy/seed-defaults/
    GET       /api/v1/documents/taxonomy/presets/
    PUT       /api/v1/documents/{id}/tags/
    GET/POST  /api/v1/documents/term-owners/
    DELETE    /api/v1/documents/term-owners/{id}/
    GET       /api/v1/documents/my-terms/
    POST      /api/v1/documents/{id}/confirm-fresh/

KB optimization spec §2.1: a space's ``taxonomy_mode`` decides which dimensions
it sees — ``inherit`` (shared org/business-line dimensions, legacy), ``space``
(space-private dimensions + org-wide shared) or ``none`` (no taxonomy). Reads
require space context (X-Space-Id).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.audit.views import create_audit_log
from apps.spaces.permissions import (
    DOCUMENT_UPDATE,
    effective_space_role,
    has_space_permission,
    is_platform_admin,
    resolve_request_space,
)

from .models import (
    Document,
    DocumentChunk,
    DocumentTag,
    TaxonomyDimension,
    TaxonomyTerm,
    TermOwnership,
)

TAXONOMY_ADMIN_ROLES = {"owner", "knowledge_admin"}


# ── Serializers ──────────────────────────────────────────────────────


class TaxonomyTermSerializer(serializers.ModelSerializer):
    dimension_code = serializers.CharField(source="dimension.code", read_only=True)

    class Meta:
        model = TaxonomyTerm
        fields = [
            "id", "dimension", "dimension_code", "parent", "code", "label",
            "synonyms", "sort_order", "status", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TaxonomyDimensionSerializer(serializers.ModelSerializer):
    terms = serializers.SerializerMethodField()

    class Meta:
        model = TaxonomyDimension
        fields = [
            "id", "organization", "business_line", "space", "code", "name",
            "is_hierarchical", "required", "sort_order", "status", "terms",
        ]
        read_only_fields = ["id", "organization", "space"]

    def get_terms(self, obj):
        terms = [t for t in obj.terms.all() if t.status == "active"]
        return TaxonomyTermSerializer(terms, many=True).data


class TermOwnershipSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    term_code = serializers.CharField(source="term.code", read_only=True)
    term_label = serializers.CharField(source="term.label", read_only=True)

    class Meta:
        model = TermOwnership
        fields = ["id", "space", "term", "term_code", "term_label", "owner", "owner_name", "created_at"]
        read_only_fields = ["id", "space", "created_at"]

    def get_owner_name(self, obj):
        return obj.owner.username or obj.owner.email


# ── Helpers ──────────────────────────────────────────────────────────


def _require_taxonomy_admin(request, space):
    """Dimension/term/ownership writes: platform admin or space owner/knowledge_admin."""
    if is_platform_admin(request.user):
        return
    role = effective_space_role(request.user, space)
    if role not in TAXONOMY_ADMIN_ROLES:
        raise PermissionDenied("Taxonomy management requires knowledge admin rights.")


def _require_dimension_admin(request, space, dimension):
    """KB spec §4: shared dimensions (space is null) are platform-managed only;
    space-private dimensions may be managed by that space's owner/knowledge_admin."""
    if is_platform_admin(request.user):
        return
    if dimension.space_id is None:
        raise PermissionDenied("Shared dimensions can only be edited by a platform admin.")
    if dimension.space_id != space.id:
        raise PermissionDenied("Dimension belongs to another space.")
    role = effective_space_role(request.user, space)
    if role not in TAXONOMY_ADMIN_ROLES:
        raise PermissionDenied("Taxonomy management requires knowledge admin rights.")


def visible_dimensions_qs(space):
    """KB spec §2.1: dimensions visible to a space depend on its taxonomy_mode.

    inherit — shared org/business-line dimensions (space is null).
    space   — this space's private dimensions + org-wide shared (business_line & space null).
    none    — nothing.
    """
    from django.db.models import Q

    mode = getattr(space, "taxonomy_mode", "inherit")
    base = TaxonomyDimension.objects.filter(
        organization_id=space.organization_id, status="active"
    )
    if mode == "none":
        return base.none()
    if mode == "space":
        return base.filter(
            Q(space_id=space.id)
            | Q(space__isnull=True, business_line__isnull=True)
        )
    # inherit (legacy): shared dimensions for the space's business line.
    return base.filter(space__isnull=True).filter(
        Q(business_line__isnull=True) | Q(business_line_id=space.business_line_id)
    )


def document_term_codes(document) -> list[str]:
    return list(
        DocumentTag.objects.filter(document=document, term__status="active")
        .values_list("term__code", flat=True)
        .order_by("term__code")
    )


def sync_chunk_term_metadata(document) -> None:
    """Denormalize the document's term codes into every chunk's metadata.

    Spec §2.4: chunk metadata carries {"terms": [...]} so pgvector / lexical
    retrieval can filter and boost by term without an extra join.
    """
    codes = document_term_codes(document)
    chunks = DocumentChunk.objects.filter(document=document).only("id", "metadata")
    updated = []
    for chunk in chunks:
        metadata = dict(chunk.metadata or {})
        if metadata.get("terms") == codes:
            continue
        metadata["terms"] = codes
        chunk.metadata = metadata
        updated.append(chunk)
    if updated:
        DocumentChunk.objects.bulk_update(updated, ["metadata"], batch_size=200)


def validate_required_dimensions(document, *, organization_id, business_line_id):
    """Raise if a required dimension has no tag on this document (spec §2.5).

    KB optimization spec §2.1: required-dimension enforcement follows the
    space's taxonomy_mode — ``none`` spaces skip the check entirely, ``space``
    spaces check their private (+ org-wide) required dimensions, and legacy
    ``inherit`` spaces keep the original shared-dimension behavior.
    """
    space = document.space
    if space is None:
        return
    required_dims = visible_dimensions_qs(space).filter(required=True)
    tagged_dims = set(
        DocumentTag.objects.filter(document=document).values_list(
            "term__dimension_id", flat=True
        )
    )
    missing = [d.name for d in required_dims if d.id not in tagged_dims]
    if missing:
        raise ValidationError(
            {"tags": f"Required dimensions missing tags: {', '.join(missing)}"}
        )


# ── Dimension / term endpoints ───────────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def taxonomy_dimensions(request):
    space = resolve_request_space(request)
    if request.method == "GET":
        from django.db.models import Prefetch

        dims = (
            visible_dimensions_qs(space)
            .prefetch_related(
                Prefetch("terms", queryset=TaxonomyTerm.objects.order_by("sort_order", "code"))
            )
            .order_by("sort_order", "code")
        )
        return Response(TaxonomyDimensionSerializer(dims, many=True).data)

    _require_taxonomy_admin(request, space)
    mode = getattr(space, "taxonomy_mode", "inherit")
    serializer = TaxonomyDimensionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    # KB spec §2.1: space-mode spaces create space-private dimensions (managed
    # by the space's own admins). inherit/none spaces can only create shared
    # dimensions, which is platform-admin only.
    if mode == "space" and not is_platform_admin(request.user):
        dimension = serializer.save(
            organization_id=space.organization_id, space=space
        )
    else:
        if not is_platform_admin(request.user):
            raise PermissionDenied(
                "Only a platform admin can create shared dimensions. "
                "Set this space's taxonomy mode to 'space' to self-manage."
            )
        dimension = serializer.save(organization_id=space.organization_id)
    create_audit_log(
        user=request.user, action="admin_action", target_type="TaxonomyDimension",
        target_id=str(dimension.id),
        details={"op": "dimension_create", "code": dimension.code,
                 "space": str(dimension.space_id) if dimension.space_id else None},
        request=request,
    )
    return Response(
        TaxonomyDimensionSerializer(dimension).data, status=status.HTTP_201_CREATED
    )


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def taxonomy_dimension_detail(request, pk):
    """KB spec §3.1: edit / archive a dimension (name/required/sort_order/status)."""
    space = resolve_request_space(request)
    try:
        dimension = TaxonomyDimension.objects.get(
            pk=pk, organization_id=space.organization_id
        )
    except TaxonomyDimension.DoesNotExist:
        raise NotFound("Dimension not found.")
    _require_dimension_admin(request, space, dimension)
    allowed = {"name", "required", "sort_order", "status", "is_hierarchical"}
    updates = {k: v for k, v in request.data.items() if k in allowed}
    if not updates:
        raise ValidationError({"detail": "No editable fields supplied."})
    if "status" in updates and updates["status"] not in {"active", "archived"}:
        raise ValidationError({"status": "Must be 'active' or 'archived'."})
    for field, value in updates.items():
        setattr(dimension, field, value)
    dimension.save(update_fields=[*updates.keys(), "updated_at"])
    create_audit_log(
        user=request.user, action="admin_action", target_type="TaxonomyDimension",
        target_id=str(dimension.id),
        details={"op": "dimension_update", "fields": sorted(updates.keys())},
        request=request,
    )
    return Response(TaxonomyDimensionSerializer(dimension).data)


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def taxonomy_terms(request):
    space = resolve_request_space(request)
    if request.method == "GET":
        qs = TaxonomyTerm.objects.filter(
            dimension__organization_id=space.organization_id, status="active"
        ).select_related("dimension").order_by("sort_order", "code")
        # KB spec §2.1: only terms of dimensions visible to this space.
        visible_ids = list(visible_dimensions_qs(space).values_list("id", flat=True))
        qs = qs.filter(dimension_id__in=visible_ids)
        dimension_code = request.query_params.get("dimension")
        if dimension_code:
            qs = qs.filter(dimension__code=dimension_code)
        return Response(TaxonomyTermSerializer(qs, many=True).data)

    serializer = TaxonomyTermSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    dimension = serializer.validated_data["dimension"]
    if dimension.organization_id != space.organization_id:
        raise PermissionDenied("Dimension belongs to another organization.")
    # Term writes obey the parent dimension's admin scope (shared vs private).
    _require_dimension_admin(request, space, dimension)
    parent = serializer.validated_data.get("parent")
    if parent is not None and parent.dimension_id != dimension.id:
        raise ValidationError({"parent": "Parent term must be in the same dimension."})
    term = serializer.save()
    create_audit_log(
        user=request.user, action="admin_action", target_type="TaxonomyTerm",
        target_id=str(term.id),
        details={"op": "term_create", "code": term.code, "dimension": dimension.code},
        request=request,
    )
    return Response(TaxonomyTermSerializer(term).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def taxonomy_term_detail(request, pk):
    """KB spec §3.1: edit / archive a term (label/sort_order/status)."""
    space = resolve_request_space(request)
    try:
        term = TaxonomyTerm.objects.select_related("dimension").get(
            pk=pk, dimension__organization_id=space.organization_id
        )
    except TaxonomyTerm.DoesNotExist:
        raise NotFound("Term not found.")
    _require_dimension_admin(request, space, term.dimension)
    allowed = {"label", "sort_order", "status", "synonyms"}
    updates = {k: v for k, v in request.data.items() if k in allowed}
    if not updates:
        raise ValidationError({"detail": "No editable fields supplied."})
    if "status" in updates and updates["status"] not in {"active", "archived"}:
        raise ValidationError({"status": "Must be 'active' or 'archived'."})
    # P2 §A4: synonyms must be a list of non-empty strings.
    if "synonyms" in updates:
        synonyms = updates["synonyms"]
        if not isinstance(synonyms, list) or any(
            not isinstance(s, str) or not s.strip() for s in synonyms
        ):
            raise ValidationError({"synonyms": "Must be a list of non-empty strings."})
        updates["synonyms"] = [s.strip()[:200] for s in synonyms][:20]
    for field, value in updates.items():
        setattr(term, field, value)
    term.save(update_fields=[*updates.keys(), "updated_at"])
    create_audit_log(
        user=request.user, action="admin_action", target_type="TaxonomyTerm",
        target_id=str(term.id),
        details={"op": "term_update", "fields": sorted(updates.keys())},
        request=request,
    )
    return Response(TaxonomyTermSerializer(term).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def taxonomy_presets(request):
    """KB spec §3.1: preset catalog for the creation wizard / seed-defaults."""
    from .taxonomy_presets import list_presets

    return Response({"presets": list_presets()})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def taxonomy_seed_defaults(request):
    """KB spec §3.1: one-click import of a default preset into this space.

    Only valid for space-mode spaces; idempotent (get_or_create).
    """
    from .taxonomy_presets import get_preset, seed_space_taxonomy

    space = resolve_request_space(request)
    _require_taxonomy_admin(request, space)
    mode = getattr(space, "taxonomy_mode", "inherit")
    if mode != "space":
        raise ValidationError(
            {"detail": "Default seeding is only available when taxonomy mode is 'space'."}
        )
    preset_code = request.data.get("preset", "audit_default")
    if get_preset(preset_code) is None:
        raise ValidationError({"preset": "Unknown preset."})
    created = seed_space_taxonomy(space, preset_code)
    create_audit_log(
        user=request.user, action="admin_action", target_type="KnowledgeSpace",
        target_id=str(space.id),
        details={"op": "taxonomy_seed_defaults", "preset": preset_code, "created": created},
        request=request,
    )
    from django.db.models import Prefetch

    dims = (
        visible_dimensions_qs(space)
        .prefetch_related(
            Prefetch("terms", queryset=TaxonomyTerm.objects.order_by("sort_order", "code"))
        )
        .order_by("sort_order", "code")
    )
    return Response(
        {"created": created, "dimensions": TaxonomyDimensionSerializer(dims, many=True).data},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# ── Document tagging ─────────────────────────────────────────────────


@api_view(["GET", "PUT"])
@permission_classes([permissions.IsAuthenticated])
def document_tags(request, pk):
    try:
        document = Document.objects.select_related("space").get(pk=pk)
    except Document.DoesNotExist:
        raise NotFound("Document not found.")
    space = resolve_request_space(request, required=False)
    if space is not None and document.space_id != space.id:
        raise NotFound("Document not found.")
    space = document.space
    if space is None or effective_space_role(request.user, space) is None:
        raise NotFound("Document not found.")

    if request.method == "GET":
        tags = DocumentTag.objects.filter(document=document).select_related(
            "term", "term__dimension"
        )
        return Response(
            [
                {
                    "term_id": str(t.term_id),
                    "code": t.term.code,
                    "label": t.term.label,
                    "dimension": t.term.dimension.code,
                }
                for t in tags
            ]
        )

    if not has_space_permission(request.user, space, DOCUMENT_UPDATE):
        raise PermissionDenied("You cannot edit tags in this space.")
    term_ids = request.data.get("term_ids")
    if not isinstance(term_ids, list):
        raise ValidationError({"term_ids": "Provide a list of term UUIDs."})
    # KB spec §2.1: only allow terms from dimensions visible to this space, so a
    # space can never tag with another space's private terms.
    visible_ids = list(visible_dimensions_qs(space).values_list("id", flat=True))
    terms = list(
        TaxonomyTerm.objects.filter(
            id__in=term_ids,
            status="active",
            dimension_id__in=visible_ids,
        )
    )
    if len(terms) != len(set(str(t) for t in term_ids)):
        raise ValidationError({"term_ids": "One or more terms are invalid for this organization."})

    with transaction.atomic():
        DocumentTag.objects.filter(document=document).exclude(
            term_id__in=[t.id for t in terms]
        ).delete()
        existing = set(
            DocumentTag.objects.filter(document=document).values_list("term_id", flat=True)
        )
        DocumentTag.objects.bulk_create(
            [
                DocumentTag(document=document, term=term, tagged_by=request.user)
                for term in terms
                if term.id not in existing
            ],
            ignore_conflicts=True,
        )
        sync_chunk_term_metadata(document)

    create_audit_log(
        user=request.user, action="document_update", target_type="Document",
        target_id=str(document.id),
        details={"op": "tags_update", "terms": [t.code for t in terms]},
        request=request,
    )
    return Response({"terms": [t.code for t in terms]})


# ── Term ownership ("我负责的科目") ─────────────────────────────────


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def term_owners(request):
    space = resolve_request_space(request)
    if request.method == "GET":
        qs = TermOwnership.objects.filter(space=space).select_related("term", "owner")
        term_id = request.query_params.get("term")
        if term_id:
            qs = qs.filter(term_id=term_id)
        return Response(TermOwnershipSerializer(qs, many=True).data)

    _require_taxonomy_admin(request, space)
    serializer = TermOwnershipSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    term = serializer.validated_data["term"]
    owner = serializer.validated_data["owner"]
    if term.dimension.organization_id != space.organization_id:
        raise ValidationError({"term": "Term belongs to another organization."})
    if effective_space_role(owner, space) is None:
        raise ValidationError({"owner": "Owner must be a member of this space."})
    ownership, created = TermOwnership.objects.get_or_create(
        space=space, term=term, owner=owner
    )
    if created:
        from apps.notifications.services import notify

        notify(
            owner, "term_ownership_assigned",
            f"你已被指派为「{term.label}」的负责人",
            body=f"空间 {space.name} 下与该科目相关的审批与陈旧预警将通知你。",
            link=f"/knowledge?term={term.code}",
        )
    return Response(
        TermOwnershipSerializer(ownership).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def term_owner_delete(request, pk):
    space = resolve_request_space(request)
    _require_taxonomy_admin(request, space)
    try:
        ownership = TermOwnership.objects.get(pk=pk, space=space)
    except TermOwnership.DoesNotExist:
        raise NotFound("Ownership not found.")
    ownership.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def my_terms(request):
    """Documents under terms the requesting user owns in the active space."""
    space = resolve_request_space(request)
    ownerships = TermOwnership.objects.filter(
        space=space, owner=request.user
    ).select_related("term", "term__dimension")
    term_ids = [o.term_id for o in ownerships]
    docs = (
        Document.objects.filter(
            space=space,
            taxonomy_tags__term_id__in=term_ids,
            status__in=["active", "stale", "pending_review"],
        )
        .distinct()
        .order_by("-updated_at")
    )
    return Response(
        {
            "terms": TermOwnershipSerializer(ownerships, many=True).data,
            "documents": [
                {
                    "id": str(d.id),
                    "title": d.title,
                    "status": d.status,
                    "version": d.version,
                    "updated_at": d.updated_at,
                }
                for d in docs[:200]
            ],
        }
    )


# ── Freshness confirmation (spec §4 L3) ──────────────────────────────


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def confirm_fresh(request, pk):
    """Owner confirms a document is still current — resets the stale clock."""
    try:
        document = Document.objects.select_related("space").get(pk=pk)
    except Document.DoesNotExist:
        raise NotFound("Document not found.")
    space = document.space
    if space is None or effective_space_role(request.user, space) is None:
        raise NotFound("Document not found.")
    if not has_space_permission(request.user, space, DOCUMENT_UPDATE):
        raise PermissionDenied("You cannot confirm freshness in this space.")

    document.last_reviewed_at = timezone.now()
    update_fields = ["last_reviewed_at", "updated_at"]
    if document.status == "stale":
        document.status = "active"
        update_fields.append("status")
    document.save(update_fields=update_fields)
    create_audit_log(
        user=request.user, action="document_update", target_type="Document",
        target_id=str(document.id),
        details={"op": "confirm_fresh", "status": document.status},
        request=request,
    )
    return Response(
        {
            "id": str(document.id),
            "status": document.status,
            "last_reviewed_at": document.last_reviewed_at,
        }
    )
