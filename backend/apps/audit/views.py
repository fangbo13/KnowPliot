# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Audit views."""

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, permissions
from rest_framework.permissions import BasePermission

from apps.spaces.permissions import (
    AUDIT_VIEW,
    admin_scope,
    get_space_or_404,
    is_platform_admin,
    resolve_space_id,
)

from .models import AuditLog
from .serializers import AuditLogSerializer


class CanViewScopedAuditLogs(BasePermission):
    """Authorize global governance or one exact workspace audit scope."""

    def has_permission(self, request, view):
        # Platform audit is already a metadata-wide capability. A space query
        # narrows that authorized inventory; it must not require synthetic
        # workspace membership or content authority.
        if is_platform_admin(request.user):
            return True
        space_id = request.query_params.get("space")
        if space_id:
            space = get_space_or_404(space_id)
            org_ids, business_line_ids = admin_scope(request.user)
            if (
                space.organization_id in org_ids
                or (
                    space.business_line_id is not None
                    and space.business_line_id in business_line_ids
                )
            ):
                view.audit_space = space
                return True
            view.audit_space = resolve_space_id(
                request.user,
                space_id,
                require_perm=AUDIT_VIEW,
            )
            return True
        org_ids, business_line_ids = admin_scope(request.user)
        return bool(org_ids or business_line_ids)


class AuditLogListView(generics.ListAPIView):
    """Read-only audit list, constrained to the caller's admin scope."""

    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, CanViewScopedAuditLogs]

    def get_queryset(self):
        audit_space = getattr(self, "audit_space", None)
        if audit_space is not None:
            qs = AuditLog.objects.filter(space_id=audit_space.id)
        elif not is_platform_admin(self.request.user):
            org_ids, business_line_ids = admin_scope(self.request.user)
            scope_query = Q()
            if org_ids:
                scope_query |= Q(organization_id__in=org_ids)
            if business_line_ids:
                scope_query |= Q(business_line_id__in=business_line_ids)
            qs = AuditLog.objects.filter(scope_query)
        else:
            qs = AuditLog.objects.all()

        action = self.request.query_params.get("action")
        user_id = self.request.query_params.get("user_id")
        result = self.request.query_params.get("result")
        organization_id = self.request.query_params.get("organization")
        business_line_id = self.request.query_params.get("business_line")
        space_id = self.request.query_params.get("space")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if action:
            qs = qs.filter(action=action)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if result:
            qs = qs.filter(result=result)
        if organization_id:
            qs = qs.filter(organization_id=organization_id)
        if business_line_id:
            qs = qs.filter(business_line_id=business_line_id)
        if space_id:
            qs = qs.filter(space_id=space_id)
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__lte=date_to)

        return qs


def _infer_scope(target_type, target_id, details):
    """Resolve stable scope UUIDs from high-risk target objects."""
    if not target_id:
        return None, None, None
    try:
        if target_type == "KnowledgeSpace":
            from apps.spaces.models import KnowledgeSpace

            space = KnowledgeSpace.objects.only(
                "id", "organization_id", "business_line_id"
            ).get(id=target_id)
            return space.organization_id, space.business_line_id, space.id
        if target_type == "Document":
            from apps.knowledge.models import Document

            document = Document.objects.select_related("space").get(id=target_id)
            if document.space_id:
                return (
                    document.space.organization_id,
                    document.space.business_line_id,
                    document.space_id,
                )
        if target_type == "ScenarioTemplate":
            from apps.scenario_templates.models import ScenarioTemplate

            template = ScenarioTemplate.objects.get(id=target_id)
            return template.organization_id, template.business_line_id, None
        if target_type == "AdminRegistrationCode":
            from apps.spaces.models import AdminRegistrationCode

            code = AdminRegistrationCode.objects.get(id=target_id)
            return code.organization_id, code.business_line_id, None
        if target_type == "BusinessLine":
            from apps.spaces.models import BusinessLine

            business_line = BusinessLine.objects.get(id=target_id)
            return business_line.organization_id, business_line.id, None
    except (ValueError, TypeError, ObjectDoesNotExist, DjangoValidationError):
        pass

    requested_space = (details or {}).get("space_id") or (details or {}).get("space")
    if requested_space:
        try:
            from apps.spaces.models import KnowledgeSpace

            space = KnowledgeSpace.objects.only(
                "id", "organization_id", "business_line_id"
            ).get(id=requested_space)
            return space.organization_id, space.business_line_id, space.id
        except (ValueError, TypeError, ObjectDoesNotExist, DjangoValidationError):
            pass
    return None, None, None


def create_audit_log(
    user,
    action,
    target_type,
    target_id=None,
    details=None,
    role_used=None,
    request=None,
    *,
    organization_id=None,
    business_line_id=None,
    space_id=None,
    result=None,
):
    """Helper to create an audit log entry.

    V4.0: Added role_used parameter for dual-role audit tracing.
    """
    inferred = _infer_scope(target_type, target_id, details)
    organization_id = organization_id or inferred[0]
    business_line_id = business_line_id or inferred[1]
    space_id = space_id or inferred[2]
    if not organization_id and not business_line_id and user:
        actor_org_ids, actor_business_line_ids = admin_scope(user)
        if len(actor_org_ids) == 1:
            organization_id = next(iter(actor_org_ids))
        if len(actor_business_line_ids) == 1:
            business_line_id = next(iter(actor_business_line_ids))
            if not organization_id:
                from apps.spaces.models import BusinessLine

                organization_id = BusinessLine.objects.values_list(
                    "organization_id", flat=True
                ).get(id=business_line_id)
    result = result or ("denied" if action == "permission_denied" else "success")
    return AuditLog.objects.create(
        user=user,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
        role_used=role_used or "",
        organization_id=organization_id,
        business_line_id=business_line_id,
        space_id=space_id,
        result=result,
    )
