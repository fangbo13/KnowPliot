# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from django.db import transaction
from django.db.models import Q
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
)
from .serializers import (
    CloneScenarioTemplateSerializer,
    CreateSpaceFromTemplateSerializer,
    ScenarioTemplateApplicationSerializer,
    ScenarioTemplateRevisionSerializer,
    ScenarioTemplateSerializer,
)
from apps.spaces.models import KnowledgeSpace, SpaceMembership, Organization, BusinessLine
from apps.spaces.serializers import KnowledgeSpaceSerializer
from apps.spaces.permissions import is_platform_admin, admin_scope
from apps.spaces.views import _audit


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

    return qs


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
        "quick_questions": template.quick_questions,
        "prompt_policy": template.prompt_policy,
        "retrieval_policy": template.retrieval_policy,
        "default_visibility": template.default_visibility,
        "is_active": template.is_active,
        "organization": str(template.organization_id) if template.organization_id else None,
        "business_line": str(template.business_line_id) if template.business_line_id else None,
    }


def _record_template_revision(template, user, change_note=""):
    """Append a new immutable revision for a template."""
    latest = (
        ScenarioTemplateRevision.objects
        .filter(template=template)
        .order_by("-version")
        .first()
    )
    next_version = (latest.version if latest else 0) + 1
    return ScenarioTemplateRevision.objects.create(
        template=template,
        version=next_version,
        snapshot=_template_snapshot(template),
        change_note=change_note,
        created_by=user,
    )


class ScenarioTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing scenario templates and instantiating spaces from them."""

    queryset = ScenarioTemplate.objects.all()
    serializer_class = ScenarioTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ScenarioTemplate.objects.select_related("organization", "business_line")
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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org, bl = _resolve_template_scope(
            request.user,
            serializer.validated_data.get("organization"),
            serializer.validated_data.get("business_line"),
        )
        template = serializer.save(created_by=request.user, organization=org, business_line=bl)
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
        serializer = self.get_serializer(template, data=request.data, partial=kwargs.pop("partial", False))
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
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="create-space")
    def create_space(self, request, pk=None):
        """Instantiate a KnowledgeSpace from a ScenarioTemplate."""
        if not is_any_admin(request.user):
            _audit(
                request.user,
                "permission_denied",
                details={"action": "space.create_from_template"},
                request=request,
            )
            raise PermissionDenied("Only administrators can create spaces from templates.")

        try:
            template = self.get_queryset().get(pk=pk)
        except ScenarioTemplate.DoesNotExist:
            raise NotFound("Template not found.")

        # Ensure active template or platform/org admin bypass
        if not template.is_active and not is_platform_admin(request.user):
            raise NotFound("Template not found.")
        if not _can_use_template(request.user, template):
            raise NotFound("Template not found.")

        serializer = CreateSpaceFromTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data["name"]
        code = serializer.validated_data["code"]
        org = serializer.validated_data.get("organization")
        bl = serializer.validated_data.get("business_line")
        visibility = serializer.validated_data.get("visibility", template.default_visibility)

        org, bl = _resolve_space_scope(request.user, org, bl)

        with transaction.atomic():
            space = KnowledgeSpace.objects.create(
                organization=org,
                business_line=bl,
                name=name,
                code=code,
                description=template.description,
                icon=template.icon,
                language=template.default_language,
                visibility=visibility,
                status="active",
                created_by=request.user,
                settings={
                    "template_id": str(template.id),
                    "template_code": template.code,
                    "scenario_type": template.scenario_type,
                    "quick_questions": template.quick_questions,
                },
            )
            
            # Creator becomes space owner
            SpaceMembership.objects.create(
                space=space,
                user=request.user,
                role=SpaceMembership.ROLE_OWNER,
                status="active",
                last_accessed_at=timezone.now(),
            )
            application = ScenarioTemplateApplication.objects.create(
                template=template,
                space=space,
                organization=org,
                business_line=bl,
                created_by=request.user,
                template_snapshot={
                    **_template_snapshot(template),
                    "latest_version": template.revisions.order_by("-version").values_list("version", flat=True).first() or 0,
                },
            )

        _audit(
            request.user,
            "space_create",
            target_id=space.id,
            details={
                "code": space.code,
                "name": space.name,
                "template_code": template.code,
                "scenario_type": template.scenario_type,
                "template_application_id": str(application.id),
            },
            request=request,
        )

        out = KnowledgeSpaceSerializer(space, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

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

    @action(detail=True, methods=["get"], url_path="revisions")
    def revisions(self, request, pk=None):
        """List immutable revision snapshots for this template."""
        if not is_any_admin(request.user):
            raise PermissionDenied("Only administrators can view template revisions.")
        try:
            template = self.get_queryset().get(pk=pk)
        except ScenarioTemplate.DoesNotExist:
            raise NotFound("Template not found.")
        if not _can_use_template(request.user, template):
            raise NotFound("Template not found.")

        qs = (
            ScenarioTemplateRevision.objects
            .filter(template=template)
            .select_related("template", "created_by")
            .order_by("-version")
        )
        serializer = ScenarioTemplateRevisionSerializer(qs, many=True)
        return Response(serializer.data)

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
            _record_template_revision(clone, request.user, f"cloned from {source.code}")

        _audit(
            request.user,
            "config_change",
            target_id=clone.id,
            details={
                "action": "template.clone",
                "source_template_code": source.code,
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
            _record_template_revision(template, request.user, "archived")

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
            _record_template_revision(template, request.user, "restored")

        _audit(
            request.user,
            "config_change",
            target_id=template.id,
            details={"action": "template.restore", "template_code": template.code},
            request=request,
        )
        out = ScenarioTemplateSerializer(template, context={"request": request})
        return Response(out.data)
