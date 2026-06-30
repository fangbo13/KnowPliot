# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Admin governance views — V7.0.

Platform-level administration mounted at ``/api/v1/admin/``. Phase 1 ships the
tiered **Admin Registration Code** management. Phase 2 extends this module with
user management, business-line CRUD, and announcement governance.

Authorization model (docs/KnowPilot_V7_Identity_RBAC_Spec.md §4.1):
  - Super Admin  -> may issue any code for any organization.
  - Org Admin    -> may issue only ``business_admin`` codes within their org(s).
"""

import logging

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied

from .models import AdminRegistrationCode, BusinessLine, Organization, OrganizationMembership
from .permissions import admin_scope, is_platform_admin
from .serializers import (
    AdminRegistrationCodeCreateSerializer,
    AdminRegistrationCodeSerializer,
    BusinessLineSerializer,
    OrganizationSerializer,
)
from .services import generate_admin_code, hash_code

logger = logging.getLogger(__name__)


def _audit(user, action, target_id=None, details=None, request=None):
    try:
        from apps.audit.views import create_audit_log
        create_audit_log(
            user=user, action=action, target_type="AdminRegistrationCode",
            target_id=target_id, details=details or {}, request=request,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("admin audit failed for %s: %s", action, exc)


def _can_issue(user, grants_role, organization) -> bool:
    """Whether ``user`` may issue a code of ``grants_role`` for ``organization``."""
    if is_platform_admin(user):
        return True
    org_ids, _ = admin_scope(user)
    # Org admins may only mint business_admin codes within their own org.
    if grants_role == OrganizationMembership.ROLE_BUSINESS_ADMIN and organization.id in org_ids:
        return True
    return False


class AdminRegistrationCodeListCreateView(generics.ListCreateAPIView):
    """GET: list manageable codes. POST: issue a new admin code."""

    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        return (
            AdminRegistrationCodeCreateSerializer
            if self.request.method == "POST"
            else AdminRegistrationCodeSerializer
        )

    def get_queryset(self):
        user = self.request.user
        qs = AdminRegistrationCode.objects.select_related("organization", "business_line")
        if is_platform_admin(user):
            return qs
        org_ids, _ = admin_scope(user)
        if not org_ids:
            raise PermissionDenied("You cannot manage admin registration codes.")
        return qs.filter(organization_id__in=list(org_ids))

    def create(self, request, *args, **kwargs):
        serializer = AdminRegistrationCodeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not _can_issue(request.user, data["grants_role"], data["organization"]):
            _audit(request.user, "permission_denied",
                   details={"action": "admin_code.create"}, request=request)
            raise PermissionDenied("You cannot issue this type of admin code.")

        raw = generate_admin_code(prefix=data["grants_role"][:3])
        code = AdminRegistrationCode.objects.create(
            code_hash=hash_code(raw),
            code_prefix=raw[:8],
            grants_role=data["grants_role"],
            organization=data["organization"],
            business_line=data.get("business_line"),
            expires_at=data.get("expires_at"),
            max_uses=data.get("max_uses", 0),
            created_by=request.user,
        )
        _audit(request.user, "admin_code_create", target_id=code.id,
               details={"grants_role": code.grants_role, "code_prefix": code.code_prefix},
               request=request)

        out = AdminRegistrationCodeSerializer(code).data
        out["code"] = raw  # plaintext returned exactly once, on creation
        return Response(out, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def admin_code_revoke(request, pk):
    code = AdminRegistrationCode.objects.filter(pk=pk).select_related("organization").first()
    if code is None:
        raise NotFound("Admin code not found.")
    if not _can_issue(request.user, code.grants_role, code.organization):
        _audit(request.user, "permission_denied",
               details={"action": "admin_code.revoke"}, request=request)
        raise PermissionDenied("You cannot revoke this admin code.")
    code.status = "revoked"
    code.save(update_fields=["status"])
    _audit(request.user, "admin_code_revoke", target_id=code.id,
           details={"code_prefix": code.code_prefix}, request=request)
    return Response({"revoked": True})


# ── Organizations & Business Lines (governance dropdowns + org structure) ──

def _scoped_org_ids(user):
    """Organization ids the user administers (super -> all -> sentinel None)."""
    if is_platform_admin(user):
        return None  # all
    org_ids, _ = admin_scope(user)
    return org_ids


class OrganizationListView(generics.ListAPIView):
    """List organizations the user administers (super sees all)."""

    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        org_ids = _scoped_org_ids(self.request.user)
        qs = Organization.objects.all()
        return qs if org_ids is None else qs.filter(id__in=list(org_ids))


class BusinessLineListCreateView(generics.ListCreateAPIView):
    """GET: list business lines in scope. POST: create one (super / org admin)."""

    serializer_class = BusinessLineSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        org_ids = _scoped_org_ids(self.request.user)
        qs = BusinessLine.objects.select_related("organization")
        org_filter = self.request.query_params.get("organization")
        if org_filter:
            qs = qs.filter(organization_id=org_filter)
        return qs if org_ids is None else qs.filter(organization_id__in=list(org_ids))

    def create(self, request, *args, **kwargs):
        serializer = BusinessLineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = serializer.validated_data["organization"]

        org_ids = _scoped_org_ids(request.user)
        if org_ids is not None and org.id not in org_ids:
            _audit(request.user, "permission_denied",
                   details={"action": "business_line.create"}, request=request)
            raise PermissionDenied("You cannot create business lines in this organization.")

        bl = serializer.save()
        try:
            from apps.audit.views import create_audit_log
            create_audit_log(user=request.user, action="config_change",
                             target_type="BusinessLine", target_id=bl.id,
                             details={"name": bl.name, "code": bl.code}, request=request)
        except Exception:  # pragma: no cover
            pass
        return Response(BusinessLineSerializer(bl).data, status=status.HTTP_201_CREATED)
