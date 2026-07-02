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

from django.db.models import Avg, Count, Max
from rest_framework import generics, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.views import APIView

from .models import AdminRegistrationCode, BusinessLine, Organization, OrganizationMembership
from .permissions import admin_scope, is_platform_admin
from .serializers import (
    AdminRegistrationCodeCreateSerializer,
    AdminRegistrationCodeSerializer,
    BusinessLineSerializer,
    OrganizationSerializer,
)
from .services import generate_admin_code, hash_code
from .admin_operations import (
    collect_scoped_metrics,
    collect_system_health,
    scoped_space_ids,
)
from apps.knowledge.models import Document, IngestionJob

logger = logging.getLogger(__name__)


def _audit_operations_view(request, view_name, **details):
    """Keep diagnostics available even when audit persistence is degraded."""
    try:
        from apps.audit.views import create_audit_log

        create_audit_log(
            user=request.user,
            action="system_health_view",
            target_type="System",
            details={"view": view_name, **details},
            result="success",
            request=request,
        )
    except Exception as exc:  # pragma: no cover - exercised with a mocked outage
        logger.warning("operations audit failed for %s: %s", view_name, exc)


class CanViewAdminOperations(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if is_platform_admin(request.user):
            return True
        org_ids, business_line_ids = admin_scope(request.user)
        return bool(org_ids or business_line_ids)


class SystemHealthView(APIView):
    permission_classes = [CanViewAdminOperations]

    def get(self, request):
        payload = collect_system_health()
        _audit_operations_view(request, "health", overall=payload["overall"])
        return Response(payload)


class SystemMetricsView(APIView):
    permission_classes = [CanViewAdminOperations]

    def get(self, request):
        payload = collect_scoped_metrics(request.user)
        _audit_operations_view(request, "metrics")
        return Response(payload)


class IngestionJobSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title", read_only=True)
    space_name = serializers.CharField(source="space.name", read_only=True)
    requested_by_email = serializers.EmailField(
        source="requested_by.email", read_only=True, allow_null=True
    )

    class Meta:
        model = IngestionJob
        fields = [
            "id",
            "document",
            "document_title",
            "space",
            "space_name",
            "requested_by_email",
            "trigger",
            "status",
            "celery_task_id",
            "attempt",
            "max_attempts",
            "last_error",
            "retry_of",
            "started_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class IngestionJobListView(generics.ListAPIView):
    serializer_class = IngestionJobSerializer
    permission_classes = [CanViewAdminOperations]

    def get_queryset(self):
        qs = IngestionJob.objects.select_related(
            "document", "space", "requested_by"
        )
        space_ids = scoped_space_ids(self.request.user)
        if space_ids is not None:
            qs = qs.filter(space_id__in=space_ids)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in dict(IngestionJob.STATUS_CHOICES):
                raise serializers.ValidationError({"status": "Unknown job status."})
            qs = qs.filter(status=status_filter)
        return qs


class IngestionJobRetryView(APIView):
    permission_classes = [CanViewAdminOperations]

    def post(self, request, pk):
        qs = IngestionJob.objects.select_related("document", "space")
        space_ids = scoped_space_ids(request.user)
        if space_ids is not None:
            qs = qs.filter(space_id__in=space_ids)
        try:
            failed_job = qs.get(pk=pk)
        except IngestionJob.DoesNotExist as exc:
            raise NotFound("Ingestion job not found.") from exc

        if failed_job.status != "failed":
            return Response(
                {"detail": "Only failed ingestion jobs can be retried."},
                status=status.HTTP_409_CONFLICT,
            )
        if failed_job.document.status == "archived":
            return Response(
                {"detail": "Archived documents cannot be retried."},
                status=status.HTTP_409_CONFLICT,
            )

        from apps.knowledge.ingestion import (
            IngestionAlreadyActive,
            enqueue_document_ingestion,
        )

        try:
            retry_job = enqueue_document_ingestion(
                failed_job.document,
                requested_by=request.user,
                trigger="admin_retry",
                retry_of=failed_job,
                prevent_duplicate=True,
            )
        except IngestionAlreadyActive:
            return Response(
                {"detail": "This document already has active ingestion work."},
                status=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:
            try:
                from apps.audit.views import create_audit_log

                create_audit_log(
                    user=request.user,
                    action="ingestion_retry",
                    target_type="Document",
                    target_id=str(failed_job.document_id),
                    details={
                        "failed_job_id": str(failed_job.id),
                        "error_code": exc.__class__.__name__,
                    },
                    result="failure",
                    request=request,
                )
            except Exception:
                logger.exception("Could not audit ingestion retry dispatch failure")
            return Response(
                {"detail": "The ingestion retry could not be queued."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        from apps.audit.views import create_audit_log

        create_audit_log(
            user=request.user,
            action="ingestion_retry",
            target_type="Document",
            target_id=str(failed_job.document_id),
            details={
                "failed_job_id": str(failed_job.id),
                "retry_job_id": str(retry_job.id),
            },
            request=request,
        )
        return Response(
            IngestionJobSerializer(retry_job).data,
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentQualitySerializer(serializers.ModelSerializer):
    citation_count = serializers.IntegerField(read_only=True)
    average_relevance = serializers.FloatField(read_only=True, allow_null=True)
    last_cited_at = serializers.DateTimeField(read_only=True, allow_null=True)
    flags = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "space",
            "status",
            "effective_to",
            "chunk_count",
            "citation_count",
            "average_relevance",
            "last_cited_at",
            "flags",
        ]

    def get_flags(self, obj):
        return {
            "unused": obj.status == "active" and obj.citation_count == 0,
            "high_usage": obj.citation_count >= 3,
            "stale_source": obj.status == "stale" and obj.citation_count > 0,
        }


class DocumentQualityListView(generics.ListAPIView):
    serializer_class = DocumentQualitySerializer
    permission_classes = [CanViewAdminOperations]

    def get_queryset(self):
        qs = Document.objects.filter(status__in=["active", "stale"])
        space_ids = scoped_space_ids(self.request.user)
        if space_ids is not None:
            qs = qs.filter(space_id__in=space_ids)
        qs = qs.annotate(
            citation_count=Count("citation"),
            average_relevance=Avg("citation__relevance_score"),
            last_cited_at=Max("citation__message__created_at"),
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in {"active", "stale"}:
                raise serializers.ValidationError(
                    {"status": "Quality status must be active or stale."}
                )
            qs = qs.filter(status=status_filter)

        flag = self.request.query_params.get("flag")
        if flag == "unused":
            qs = qs.filter(status="active", citation_count=0)
        elif flag == "high_usage":
            qs = qs.filter(citation_count__gte=3)
        elif flag == "stale_source":
            qs = qs.filter(status="stale", citation_count__gt=0)
        elif flag:
            raise serializers.ValidationError({"flag": "Unknown quality flag."})
        return qs.order_by("-citation_count", "title")


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
