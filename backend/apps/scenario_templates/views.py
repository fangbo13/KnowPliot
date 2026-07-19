# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from .models import (
    ScenarioTemplate,
    ScenarioTemplateApplication,
    ScenarioTemplateRevision,
    ScenarioTemplateAsset,
    TemplateAssetApplication,
    TemplateCategory,
    TemplateTag,
)
from .serializers import (
    CloneScenarioTemplateSerializer,
    ScenarioTemplateApplicationSerializer,
    ScenarioTemplateRevisionActivateSerializer,
    ScenarioTemplateRevisionCreateSerializer,
    ScenarioTemplateRevisionSerializer,
    ScenarioTemplateSerializer,
    ScenarioTemplateAssetSerializer,
)
from apps.knowledge.models import Document
from apps.spaces.models import KnowledgeSpace, Organization, BusinessLine
from apps.spaces.permissions import is_platform_admin, admin_scope
from apps.spaces.views import _audit
from .contract import (
    legacy_template_projection,
    normalize_revision_snapshot,
    preview_payload,
    revision_snapshot,
    snapshot_hash,
)


def is_any_admin(user):
    """Check if the user is a platform admin, org admin, or business admin."""
    if not user or not user.is_authenticated:
        return False
    if is_platform_admin(user):
        return True
    org_ids, bl_ids = admin_scope(user)
    return bool(org_ids) or bool(bl_ids)


def _resolve_space_scope(user, org, bl):
    """Resolve and enforce the organization/business-line scope for space creation."""
    if bl and org and bl.organization_id != org.id:
        raise ValidationError(
            {"business_line": ["Business line must belong to the selected organization."]}
        )

    if is_platform_admin(user):
        if org is None and bl is not None:
            org = bl.organization
        if org is None:
            org = (
                Organization.objects.filter(slug="default").first()
                or Organization.objects.first()
            )
            if org is None:
                org = Organization.objects.create(name="Default Organization", slug="default")
        return org, bl

    org_ids, bl_ids = admin_scope(user)

    if bl_ids and not org_ids:
        allowed_lines = BusinessLine.objects.filter(id__in=list(bl_ids)).select_related("organization")
        if bl is None:
            if allowed_lines.count() != 1:
                raise ValidationError(
                    {"business_line": ["Business line is required for this administrator."]}
                )
            bl = allowed_lines.first()
        if bl.id not in bl_ids:
            raise PermissionDenied("You cannot create spaces outside your business line.")
        if org is None:
            org = bl.organization
        elif org.id != bl.organization_id:
            raise ValidationError(
                {"business_line": ["Business line must belong to the selected organization."]}
            )
        return org, bl

    if org_ids:
        if org is None:
            if len(org_ids) != 1:
                raise ValidationError(
                    {"organization": ["Organization is required for this administrator."]}
                )
            org = Organization.objects.get(id=next(iter(org_ids)))
        if org.id not in org_ids:
            raise PermissionDenied("You cannot create spaces outside your organization.")
        if bl and bl.organization_id != org.id:
            raise ValidationError(
                {"business_line": ["Business line must belong to the selected organization."]}
            )
        return org, bl

    raise PermissionDenied("Only administrators can create spaces from templates.")


def _template_scope_filter(user):
    """Templates visible to the current user."""
    base = Q(organization__isnull=True, business_line__isnull=True)
    if is_platform_admin(user):
        return Q()
    org_ids, bl_ids = admin_scope(user)
    if org_ids:
        base |= Q(organization_id__in=list(org_ids))
    if bl_ids:
        base |= Q(business_line_id__in=list(bl_ids))
    return base


def _resolve_template_scope(user, org, bl):
    """Resolve and enforce template ownership scope for create/update."""
    if bl and org and bl.organization_id != org.id:
        raise ValidationError(
            {"business_line": ["Business line must belong to the selected organization."]}
        )
    if bl and org is None:
        org = bl.organization

    if is_platform_admin(user):
        return org, bl

    org_ids, bl_ids = admin_scope(user)

    if bl_ids and not org_ids:
        allowed_lines = BusinessLine.objects.filter(id__in=list(bl_ids)).select_related("organization")
        if bl is None:
            if allowed_lines.count() != 1:
                raise ValidationError(
                    {"business_line": ["Business line is required for this administrator."]}
                )
            bl = allowed_lines.first()
        if bl.id not in bl_ids:
            raise PermissionDenied("You cannot manage templates outside your business line.")
        return bl.organization, bl

    if org_ids:
        if org is None:
            if len(org_ids) != 1:
                raise ValidationError(
                    {"organization": ["Organization is required for this administrator."]}
                )
            org = Organization.objects.get(id=next(iter(org_ids)))
        if org.id not in org_ids:
            raise PermissionDenied("You cannot manage templates outside your organization.")
        if bl and bl.organization_id != org.id:
            raise ValidationError(
                {"business_line": ["Business line must belong to the selected organization."]}
            )
        return org, bl

    raise PermissionDenied("Only administrators can manage templates.")


def _can_manage_template(user, template):
    """Whether the user may edit/delete this template."""
    if is_platform_admin(user):
        return True
    # Global templates are platform-owned; scoped admins can use them but not edit them.
    if template.organization_id is None and template.business_line_id is None:
        return False
    org_ids, bl_ids = admin_scope(user)
    if template.business_line_id:
        return template.business_line_id in bl_ids or template.organization_id in org_ids
    if template.organization_id:
        return template.organization_id in org_ids
    return False


def _can_use_template(user, template):
    """Whether the user may instantiate this template."""
    if is_platform_admin(user):
        return True
    if template.organization_id is None and template.business_line_id is None:
        return True
    org_ids, bl_ids = admin_scope(user)
    if template.business_line_id:
        return template.business_line_id in bl_ids or template.organization_id in org_ids
    if template.organization_id:
        return template.organization_id in org_ids
    return False


def _application_scope_filter(user):
    """Application records visible to the current administrator."""
    if is_platform_admin(user):
        return Q()
    org_ids, bl_ids = admin_scope(user)
    q = Q()
    if org_ids:
        q |= Q(organization_id__in=list(org_ids))
    if bl_ids:
        q |= Q(business_line_id__in=list(bl_ids))
    return q


def _apply_template_query_filters(qs, params, *, allow_inactive=False):
    """Apply user-supplied list filters after RBAC/scope visibility is resolved."""
    scenario_type = params.get("scenario_type")
    if scenario_type:
        qs = qs.filter(scenario_type=scenario_type)

    is_active = params.get("is_active")
    if is_active is not None and allow_inactive:
        normalized = str(is_active).strip().lower()
        if normalized in {"true", "1", "yes", "active"}:
            qs = qs.filter(is_active=True)
        elif normalized in {"false", "0", "no", "inactive"}:
            qs = qs.filter(is_active=False)

    scope = params.get("scope")
    if scope == "global":
        qs = qs.filter(organization__isnull=True, business_line__isnull=True)
    elif scope == "organization":
        qs = qs.filter(organization__isnull=False, business_line__isnull=True)
    elif scope == "business_line":
        qs = qs.filter(business_line__isnull=False)

    organization = params.get("organization")
    if organization:
        qs = qs.filter(organization_id=organization)

    business_line = params.get("business_line")
    if business_line:
        qs = qs.filter(business_line_id=business_line)

    q = params.get("q")
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(code__icontains=q)
            | Q(description__icontains=q)
        )

    category = params.get("category")
    if category:
        qs = qs.filter(category__slug=category)

    tags = [value.strip() for value in params.get("tags", "").split(",") if value.strip()]
    if tags:
        qs = qs.filter(tags__slug__in=tags).annotate(
            matched_tag_count=Count("tags", filter=Q(tags__slug__in=tags), distinct=True)
        ).filter(matched_tag_count=len(tags))

    qs = qs.annotate(application_count=Count("applications", distinct=True))
    sort = params.get("sort", "recommended")
    if sort == "popular":
        qs = qs.order_by("-application_count", "-updated_at", "name")
    elif sort == "recent":
        qs = qs.order_by("-updated_at", "name")
    elif sort == "name":
        qs = qs.order_by("name")
    else:
        qs = qs.order_by("-featured", "-application_count", "-updated_at", "name")
    return qs.distinct()


def _template_snapshot(template):
    """Build a stable snapshot used by revisions and application records."""
    return {
        "template_id": str(template.id),
        "template_code": template.code,
        "template_name": template.name,
        "description": template.description,
        "scenario_type": template.scenario_type,
        "default_language": template.default_language,
        "icon": template.icon,
        "category": str(template.category_id) if template.category_id else None,
        "tags": list(template.tags.order_by("slug").values_list("slug", flat=True)),
        "featured": template.featured,
        "quick_questions": template.quick_questions,
        "prompt_policy": template.prompt_policy,
        "retrieval_policy": template.retrieval_policy,
        "default_visibility": template.default_visibility,
        "is_active": template.is_active,
        "organization": str(template.organization_id) if template.organization_id else None,
        "business_line": str(template.business_line_id) if template.business_line_id else None,
    }


def _record_template_revision(template, user, change_note=""):
    """Append a draft revision without moving the published current pointer."""

    from .contract import legacy_template_components

    with transaction.atomic():
        locked = ScenarioTemplate.objects.select_for_update(of=("self",)).get(
            pk=template.pk
        )
        latest = locked.revisions.order_by("-version").first()
        next_version = (latest.version if latest else 0) + 1
        return ScenarioTemplateRevision.objects.create(
            template=locked,
            version=next_version,
            snapshot=revision_snapshot(
                legacy_template_components(_template_snapshot(locked))
            ),
            change_note=change_note,
            created_by=user,
        )


def _create_component_revision(*, template, user, components, change_note=""):
    with transaction.atomic():
        locked = ScenarioTemplate.objects.select_for_update(of=("self",)).get(
            pk=template.pk
        )
        latest = locked.revisions.order_by("-version").first()
        return ScenarioTemplateRevision.objects.create(
            template=locked,
            version=(latest.version if latest else 0) + 1,
            snapshot=revision_snapshot(components),
            change_note=change_note,
            created_by=user,
        )


def _latest_template_version(template) -> int:
    return (
        template.revisions.order_by("-version").values_list("version", flat=True).first()
        or 0
    )


def _assert_revision_integrity(revision):
    if revision.snapshot_hash != snapshot_hash(revision.snapshot):
        from apps.spaces.governed import GovernedWorkflowError

        raise GovernedWorkflowError("template_revision_not_ready", status_code=503)


def _provision_template_asset(application, asset, user):
    """Historical asset copying is fail-closed under the v3 clone contract."""
    from apps.spaces.governed import GovernedWorkflowError

    raise GovernedWorkflowError(
        "template_asset_copy_disabled",
        "Template document copying is disabled by the v3 clone contract.",
        status_code=503,
    )


class ScenarioTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing scenario templates and instantiating spaces from them."""

    queryset = ScenarioTemplate.objects.all()
    serializer_class = ScenarioTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ScenarioTemplate.objects.select_related(
            "organization", "business_line", "category", "current_revision"
        ).prefetch_related("tags")
        if is_any_admin(user):
            qs = qs.filter(_template_scope_filter(user))
            return _apply_template_query_filters(
                qs,
                self.request.query_params,
                allow_inactive=True,
            )
        qs = qs.filter(is_active=True, organization__isnull=True, business_line__isnull=True)
        return _apply_template_query_filters(
            qs,
            self.request.query_params,
            allow_inactive=False,
        )

    def create(self, request, *args, **kwargs):
        if not is_any_admin(request.user):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.create"},
                request=request,
            )
            raise PermissionDenied("Only administrators can create templates.")
        canonical_fields = {"scope_type", "scope_id", "key", "display_name"}
        if canonical_fields.intersection(request.data):
            unknown = sorted(set(request.data) - canonical_fields)
            missing = sorted(canonical_fields - set(request.data))
            if unknown or missing:
                raise ValidationError(
                    {"unknown_fields": unknown, "missing_fields": missing}
                )
            scope_type = request.data.get("scope_type")
            scope_id = request.data.get("scope_id")
            org = bl = None
            try:
                if scope_type == "global":
                    if scope_id not in (None, ""):
                        raise ValidationError(
                            {"scope_id": "Global templates do not have a scope ID."}
                        )
                elif scope_type == "organization":
                    org = Organization.objects.get(pk=scope_id)
                elif scope_type == "business_line":
                    bl = BusinessLine.objects.select_related("organization").get(
                        pk=scope_id
                    )
                    org = bl.organization
                else:
                    raise ValidationError({"scope_type": "Unsupported template scope."})
            except (Organization.DoesNotExist, BusinessLine.DoesNotExist, ValueError):
                raise ValidationError({"scope_id": "Template scope was not found."})
            serializer_input = {
                "name": request.data.get("display_name"),
                "code": request.data.get("key"),
                "organization": str(org.id) if org else None,
                "business_line": str(bl.id) if bl else None,
            }
        else:
            serializer_input = request.data
        serializer = self.get_serializer(data=serializer_input)
        serializer.is_valid(raise_exception=True)
        org, bl = _resolve_template_scope(
            request.user,
            serializer.validated_data.get("organization"),
            serializer.validated_data.get("business_line"),
        )
        with transaction.atomic():
            template = serializer.save(
                created_by=request.user,
                organization=org,
                business_line=bl,
            )
            _record_template_revision(template, request.user, "created")
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if not is_any_admin(request.user):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.update"},
                request=request,
            )
            raise PermissionDenied("Only administrators can update templates.")
        template = self.get_object()
        if not _can_manage_template(request.user, template):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.update", "template_code": template.code},
                request=request,
            )
            raise PermissionDenied("You cannot update this template.")
        with transaction.atomic():
            template = ScenarioTemplate.objects.select_for_update(of=("self",)).get(
                pk=template.pk
            )
            serializer = self.get_serializer(
                template,
                data=request.data,
                partial=kwargs.pop("partial", False),
            )
            serializer.is_valid(raise_exception=True)
            org, bl = _resolve_template_scope(
                request.user,
                serializer.validated_data.get("organization", template.organization),
                serializer.validated_data.get("business_line", template.business_line),
            )
            template = serializer.save(organization=org, business_line=bl)
            _record_template_revision(template, request.user, "updated")
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        if not is_any_admin(request.user):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.delete"},
                request=request,
            )
            raise PermissionDenied("Only administrators can delete templates.")
        template = self.get_object()
        if not _can_manage_template(request.user, template):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.delete", "template_code": template.code},
                request=request,
            )
            raise PermissionDenied("You cannot delete this template.")
        from apps.spaces.governed import GovernedWorkflowError

        raise GovernedWorkflowError(
            "template_delete_disabled",
            "Templates are archived; published revision history is not deleted.",
        )

    @action(detail=True, methods=["post"], url_path="create-space")
    def create_space(self, request, pk=None):
        """Compatibility adapter: submit a governed request, never clone data."""
        try:
            template = self.get_queryset().get(pk=pk)
        except ScenarioTemplate.DoesNotExist:
            raise NotFound("Template not found.")
        if not template.is_active or not _can_use_template(request.user, template):
            raise NotFound("Template not found.")
        if bool(getattr(settings, "TEMPLATE_ASSET_COPY_ENABLED", False)):
            from apps.spaces.governed import GovernedWorkflowError

            raise GovernedWorkflowError("template_clone_not_ready", status_code=503)
        revision = template.current_revision
        if revision is None or revision.published_at is None:
            from apps.spaces.governed import GovernedWorkflowError

            raise GovernedWorkflowError("template_revision_not_ready", status_code=503)
        _assert_revision_integrity(revision)
        revision_defaults = legacy_template_projection(revision.snapshot)
        allowed = {
            "name",
            "code",
            "purpose",
            "visibility",
            "business_line_id",
            "work_group_id",
            "office_location_ids",
        }
        unknown = sorted(set(request.data) - allowed)
        if unknown:
            raise ValidationError({"unknown_fields": unknown})
        from apps.spaces.creation_services import submit_creation_request
        from apps.spaces.governed import require_idempotency_key

        payload = {
            "name": request.data.get("name"),
            "code": request.data.get("code"),
            "purpose": request.data.get("purpose", template.description),
            "visibility": request.data.get(
                "visibility",
                revision_defaults.get("default_visibility", "private"),
            ),
            "business_line_id": request.data.get("business_line_id"),
            "work_group_id": request.data.get("work_group_id"),
            "office_location_ids": request.data.get("office_location_ids"),
            "template_version_id": str(revision.id),
        }
        body = submit_creation_request(
            actor=request.user,
            payload=payload,
            idempotency_key=require_idempotency_key(request),
        )
        if isinstance(body, Response):
            return body
        return Response(body, status=status.HTTP_202_ACCEPTED)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"applications/(?P<application_id>[^/.]+)/retry-assets",
    )
    def retry_assets(self, request, pk=None, application_id=None):
        from apps.spaces.governed import GovernedWorkflowError

        raise GovernedWorkflowError(
            "template_asset_copy_disabled", status_code=503
        )

    @action(detail=True, methods=["get"], url_path="applications")
    def applications(self, request, pk=None):
        """List application records for this template, filtered by admin scope."""
        if not is_any_admin(request.user):
            raise PermissionDenied("Only administrators can view template applications.")
        try:
            template = self.get_queryset().get(pk=pk)
        except ScenarioTemplate.DoesNotExist:
            raise NotFound("Template not found.")
        if not _can_use_template(request.user, template):
            raise NotFound("Template not found.")

        qs = (
            ScenarioTemplateApplication.objects
            .filter(template=template)
            .filter(_application_scope_filter(request.user))
            .select_related("template", "space", "organization", "business_line", "created_by")
        )
        serializer = ScenarioTemplateApplicationSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"], url_path="revisions")
    def revisions(self, request, pk=None):
        """List revisions or append one exact, immutable draft snapshot."""
        try:
            template = self.get_queryset().get(pk=pk)
        except ScenarioTemplate.DoesNotExist:
            raise NotFound("Template not found.")
        if not _can_use_template(request.user, template):
            raise NotFound("Template not found.")

        if request.method == "POST":
            if not _can_manage_template(request.user, template):
                raise PermissionDenied("You cannot create revisions for this template.")
            payload = ScenarioTemplateRevisionCreateSerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            from apps.spaces.governed import (
                complete_operation_record,
                digest_payload,
                operation_record,
                replay_response,
                require_idempotency_key,
            )

            request_digest = digest_payload(
                {
                    "template_id": template.id,
                    "action": "template_revision_create",
                    **payload.validated_data,
                }
            )
            with transaction.atomic():
                with operation_record(
                    actor=request.user,
                    operation_code="template.revision.create",
                    key=require_idempotency_key(request),
                    request_digest=request_digest,
                    target_uuid=template.id,
                ) as (operation, replay):
                    if replay:
                        return replay_response(operation)
                    locked = ScenarioTemplate.objects.select_for_update(
                        of=("self",)
                    ).get(pk=template.pk)
                    latest_version = _latest_template_version(locked)
                    expected = payload.validated_data["expected_template_version"]
                    if expected != latest_version:
                        from apps.spaces.governed import GovernedWorkflowError

                        raise GovernedWorkflowError(
                            "stale_template_version",
                            details={"current_version": latest_version},
                        )
                    revision = ScenarioTemplateRevision.objects.create(
                        template=locked,
                        version=latest_version + 1,
                        snapshot=revision_snapshot(payload.validated_data["components"]),
                        change_note="v3 draft",
                        created_by=request.user,
                    )
                    _audit(
                        request.user,
                        "config_change",
                        target_id=template.id,
                        details={
                            "action": "template.revision.create",
                            "revision_id": str(revision.id),
                            "revision_version": revision.version,
                            "snapshot_hash": revision.snapshot_hash,
                        },
                        request=request,
                    )
                    body = ScenarioTemplateRevisionSerializer(revision).data
                    complete_operation_record(
                        operation,
                        status_code=status.HTTP_201_CREATED,
                        body=body,
                        result_reference=revision.id,
                    )
            return Response(body, status=status.HTTP_201_CREATED)

        qs = (
            ScenarioTemplateRevision.objects
            .filter(template=template)
            .select_related("template", "created_by")
            .order_by("-version")
        )
        if not _can_manage_template(request.user, template):
            qs = qs.filter(published_at__isnull=False)
        serializer = ScenarioTemplateRevisionSerializer(qs, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get"],
        url_path=r"revisions/(?P<revision_id>[^/.]+)/preview",
    )
    def revision_preview(self, request, pk=None, revision_id=None):
        try:
            template = self.get_queryset().get(pk=pk)
        except ScenarioTemplate.DoesNotExist:
            raise NotFound("Template not found.")
        if not _can_use_template(request.user, template):
            raise NotFound("Template not found.")
        try:
            revision = template.revisions.get(pk=revision_id)
        except (ScenarioTemplateRevision.DoesNotExist, ValueError):
            raise NotFound("Template revision not found.")
        if revision.published_at is None and not _can_manage_template(
            request.user, template
        ):
            raise NotFound("Template revision not found.")
        _assert_revision_integrity(revision)
        return Response(preview_payload(revision))

    @action(
        detail=True,
        methods=["post"],
        url_path=r"revisions/(?P<revision_id>[^/.]+)/activate",
    )
    def activate_revision(self, request, pk=None, revision_id=None):
        template = self.get_object()
        if not _can_manage_template(request.user, template):
            raise PermissionDenied("You cannot activate revisions for this template.")
        payload = ScenarioTemplateRevisionActivateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        from apps.spaces.governed import (
            complete_operation_record,
            digest_payload,
            operation_record,
            replay_response,
            require_idempotency_key,
        )

        request_digest = digest_payload(
            {
                "template_id": template.id,
                "revision_id": revision_id,
                "action": "template_revision_activate",
                **payload.validated_data,
            }
        )

        with transaction.atomic():
            with operation_record(
                actor=request.user,
                operation_code="template.revision.activate",
                key=require_idempotency_key(request),
                request_digest=request_digest,
                target_uuid=template.id,
            ) as (operation, replay):
                if replay:
                    return replay_response(operation)
                locked = ScenarioTemplate.objects.select_for_update(of=("self",)).get(
                    pk=template.pk
                )
                try:
                    revision = ScenarioTemplateRevision.objects.select_for_update(
                        of=("self",)
                    ).get(pk=revision_id, template=locked)
                except (ScenarioTemplateRevision.DoesNotExist, ValueError):
                    raise NotFound("Template revision not found.")
                latest_version = _latest_template_version(locked)
                expected_version = payload.validated_data["expected_template_version"]
                if expected_version != latest_version or revision.version != latest_version:
                    from apps.spaces.governed import GovernedWorkflowError

                    raise GovernedWorkflowError(
                        "stale_template_version",
                        details={"current_version": latest_version},
                    )
                _assert_revision_integrity(revision)
                if revision.snapshot_hash != payload.validated_data["expected_revision_hash"]:
                    from apps.spaces.governed import GovernedWorkflowError

                    raise GovernedWorkflowError(
                        "template_revision_hash_mismatch",
                        details={"current_version": latest_version},
                    )
                if revision.published_at is None:
                    published_at = timezone.now()
                    ScenarioTemplateRevision.objects.filter(
                        pk=revision.pk,
                        published_at__isnull=True,
                    ).update(published_at=published_at)
                    revision.published_at = published_at
                projection = legacy_template_projection(revision.snapshot)
                ScenarioTemplate.objects.filter(pk=locked.pk).update(
                    current_revision=revision,
                    updated_at=timezone.now(),
                    **projection,
                )
                _audit(
                    request.user,
                    "config_change",
                    target_id=template.id,
                    details={
                        "action": "template.revision.activate",
                        "revision_id": str(revision.id),
                        "revision_version": revision.version,
                        "snapshot_hash": revision.snapshot_hash,
                    },
                    request=request,
                )
                body = ScenarioTemplateRevisionSerializer(revision).data
                complete_operation_record(
                    operation,
                    status_code=status.HTTP_200_OK,
                    body=body,
                    result_reference=revision.id,
                )
        return Response(body)

    @action(detail=True, methods=["get"], url_path="diff")
    def revision_diff(self, request, pk=None):
        template = self.get_object()
        if not is_any_admin(request.user) or not _can_use_template(request.user, template):
            raise NotFound("Template not found.")
        try:
            from_version = int(request.query_params["from"])
            to_version = int(request.query_params["to"])
            revisions = {
                row.version: row
                for row in template.revisions.filter(version__in=[from_version, to_version])
            }
            before, after = revisions[from_version], revisions[to_version]
        except (KeyError, TypeError, ValueError):
            raise ValidationError({"detail": "Valid from and to revisions are required."})
        keys = sorted(set(before.snapshot) | set(after.snapshot))
        changes = {
            key: {"from": before.snapshot.get(key), "to": after.snapshot.get(key)}
            for key in keys
            if before.snapshot.get(key) != after.snapshot.get(key)
        }
        return Response({"from": from_version, "to": to_version, "changes": changes})

    @action(detail=True, methods=["post"], url_path="rollback")
    def rollback(self, request, pk=None):
        template = self.get_object()
        if not _can_manage_template(request.user, template):
            raise PermissionDenied("You cannot roll back this template.")
        unknown = sorted(set(request.data) - {"revision", "expected_template_version"})
        if unknown:
            raise ValidationError({"unknown_fields": unknown})
        try:
            source_version = int(request.data["revision"])
            expected_version = int(request.data["expected_template_version"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError(
                {
                    "detail": (
                        "revision and expected_template_version are required integers."
                    )
                }
            )
        with transaction.atomic():
            locked = ScenarioTemplate.objects.select_for_update(of=("self",)).get(
                pk=template.pk
            )
            latest_version = _latest_template_version(locked)
            if expected_version != latest_version:
                from apps.spaces.governed import GovernedWorkflowError

                raise GovernedWorkflowError(
                    "stale_template_version",
                    details={"current_version": latest_version},
                )
            try:
                source_revision = locked.revisions.get(version=source_version)
            except ScenarioTemplateRevision.DoesNotExist:
                raise ValidationError({"revision": "A valid revision is required."})
            _assert_revision_integrity(source_revision)
            revision = ScenarioTemplateRevision.objects.create(
                template=locked,
                version=latest_version + 1,
                snapshot=normalize_revision_snapshot(source_revision.snapshot),
                created_by=request.user,
                change_note=f"rollback draft from revision {source_revision.version}",
            )
        _audit(
            request.user,
            "template_update",
            target_id=template.id,
            details={
                "operation": "rollback",
                "source_revision": source_revision.version,
                "draft_revision": revision.version,
                "snapshot_hash": revision.snapshot_hash,
            },
            request=request,
        )
        template.refresh_from_db()
        return Response(self.get_serializer(template).data)

    @action(detail=True, methods=["get", "post"], url_path="assets")
    def assets(self, request, pk=None):
        template = self.get_object()
        if not _can_manage_template(request.user, template):
            raise PermissionDenied("You cannot manage assets for this template.")
        if request.method == "GET":
            return Response(
                ScenarioTemplateAssetSerializer(
                    template.assets.select_related("document", "document__space"),
                    many=True,
                ).data
            )
        from apps.spaces.governed import GovernedWorkflowError

        raise GovernedWorkflowError(
            "template_asset_attachment_disabled",
            "Document assets are historical evidence only and cannot be attached.",
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"assets/(?P<asset_id>[^/.]+)",
    )
    def delete_asset(self, request, pk=None, asset_id=None):
        template = self.get_object()
        if not _can_manage_template(request.user, template):
            raise PermissionDenied("You cannot manage assets for this template.")
        deleted, _ = template.assets.filter(id=asset_id).delete()
        if not deleted:
            raise NotFound("Asset not found.")
        _audit(
            request.user,
            "template_update",
            target_id=template.id,
            details={"operation": "asset_delete", "asset_id": str(asset_id)},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, pk=None):
        """Clone a visible template into a new scoped template."""
        if not is_any_admin(request.user):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.clone"},
                request=request,
            )
            raise PermissionDenied("Only administrators can clone templates.")

        try:
            source = self.get_queryset().get(pk=pk)
        except ScenarioTemplate.DoesNotExist:
            raise NotFound("Template not found.")
        if not _can_use_template(request.user, source):
            raise NotFound("Template not found.")

        serializer = CloneScenarioTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org, bl = _resolve_template_scope(
            request.user,
            serializer.validated_data.get("organization"),
            serializer.validated_data.get("business_line"),
        )

        with transaction.atomic():
            source = ScenarioTemplate.objects.select_for_update(of=("self",)).select_related(
                "current_revision"
            ).get(pk=source.pk)
            source_revision = source.current_revision
            if source_revision is None or source_revision.published_at is None:
                from apps.spaces.governed import GovernedWorkflowError

                raise GovernedWorkflowError(
                    "template_revision_not_ready", status_code=503
                )
            _assert_revision_integrity(source_revision)
            clone = ScenarioTemplate.objects.create(
                name=serializer.validated_data["name"],
                code=serializer.validated_data["code"],
                description=source.description,
                scenario_type=source.scenario_type,
                default_language=source.default_language,
                icon=source.icon,
                quick_questions=source.quick_questions,
                prompt_policy=source.prompt_policy,
                retrieval_policy=source.retrieval_policy,
                default_visibility=source.default_visibility,
                is_active=serializer.validated_data.get("is_active", source.is_active),
                organization=org,
                business_line=bl,
                created_by=request.user,
            )
            cloned_revision = ScenarioTemplateRevision.objects.create(
                template=clone,
                version=1,
                snapshot=normalize_revision_snapshot(source_revision.snapshot),
                change_note=(
                    f"cloned draft from {source.code} revision {source_revision.version}"
                ),
                created_by=request.user,
            )

        _audit(
            request.user,
            "config_change",
            target_id=clone.id,
            details={
                "action": "template.clone",
                "source_template_code": source.code,
                "source_revision_id": str(source_revision.id),
                "source_revision_hash": source_revision.snapshot_hash,
                "draft_revision_id": str(cloned_revision.id),
                "template_code": clone.code,
            },
            request=request,
        )

        out = ScenarioTemplateSerializer(clone, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        """Archive a manageable template without deleting history."""
        if not is_any_admin(request.user):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.archive"},
                request=request,
            )
            raise PermissionDenied("Only administrators can archive templates.")

        template = self.get_object()
        if not _can_manage_template(request.user, template):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.archive", "template_code": template.code},
                request=request,
            )
            raise PermissionDenied("You cannot archive this template.")

        if template.is_active:
            template.is_active = False
            template.save(update_fields=["is_active", "updated_at"])

        _audit(
            request.user,
            "config_change",
            target_id=template.id,
            details={"action": "template.archive", "template_code": template.code},
            request=request,
        )
        out = ScenarioTemplateSerializer(template, context={"request": request})
        return Response(out.data)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        """Restore an archived manageable template."""
        if not is_any_admin(request.user):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.restore"},
                request=request,
            )
            raise PermissionDenied("Only administrators can restore templates.")

        template = self.get_object()
        if not _can_manage_template(request.user, template):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "template.restore", "template_code": template.code},
                request=request,
            )
            raise PermissionDenied("You cannot restore this template.")

        if not template.is_active:
            template.is_active = True
            template.save(update_fields=["is_active", "updated_at"])

        _audit(
            request.user,
            "config_change",
            target_id=template.id,
            details={"action": "template.restore", "template_code": template.code},
            request=request,
        )
        out = ScenarioTemplateSerializer(template, context={"request": request})
        return Response(out.data)
