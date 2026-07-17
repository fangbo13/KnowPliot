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

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Avg, Count, Max
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.knowledge.models import Document, IngestionJob

from .admin_operations import (
    collect_scoped_metrics,
    collect_system_health,
    scoped_space_ids,
)
from .models import (
    AdminRegistrationCode,
    BusinessLine,
    GovernancePolicy,
    KnowledgeSpace,
    ModelProfile,
    Organization,
    OrganizationMembership,
    SpaceAccessRequest,
    SpaceMembership,
    create_policy_revision,
    resolve_effective_policy,
)
from .permissions import admin_scope, is_platform_admin
from .serializers import (
    AdminRegistrationCodeCreateSerializer,
    AdminRegistrationCodeSerializer,
    BusinessLineSerializer,
    GovernancePolicySerializer,
    ModelProfileSerializer,
    OrganizationSerializer,
    SpaceAccessRequestSerializer,
)
from .services import generate_admin_code, hash_code

logger = logging.getLogger(__name__)


class ModelProfileListCreateView(generics.ListCreateAPIView):
    serializer_class = ModelProfileSerializer
    permission_classes = [IsAuthenticated]
    queryset = ModelProfile.objects.all().order_by("name")

    def get_queryset(self):
        queryset = super().get_queryset()
        if not is_platform_admin(self.request.user):
            queryset = queryset.filter(enabled=True)
        return queryset

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if is_platform_admin(request.user):
            return
        organization_ids, _ = admin_scope(request.user)
        if request.method == "GET" and organization_ids:
            return
        if request.method == "GET":
            raise PermissionDenied("You cannot view model profiles.")
        else:
            raise PermissionDenied("Only platform administrators can manage model profiles.")


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def governance_policies(request):
    if request.method == "GET":
        space_id = request.query_params.get("space")
        if not space_id:
            raise ValidationError({"space": "Required."})
        try:
            space = KnowledgeSpace.objects.get(pk=space_id)
        except KnowledgeSpace.DoesNotExist as exc:
            raise NotFound("Space not found.") from exc
        if (
            not is_platform_admin(request.user)
            and space.organization_id not in admin_scope(request.user)[0]
        ):
            raise PermissionDenied("You cannot view this policy.")
        revisions = GovernancePolicy.objects.filter(space=space)
        return Response(
            {
                "effective": resolve_effective_policy(space),
                "revisions": GovernancePolicySerializer(revisions, many=True).data,
            }
        )
    serializer = GovernancePolicySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data
    organization = validated.get("organization")
    space = validated.get("space")
    if bool(organization) == bool(space):
        raise ValidationError(
            {"scope": "Provide exactly one organization or workspace scope."}
        )
    target_organization = organization or space.organization
    if not is_platform_admin(request.user):
        organization_ids, _ = admin_scope(request.user)
        if target_organization.id not in organization_ids:
            raise PermissionDenied("You cannot create a policy in this organization.")
    policy = create_policy_revision(
        organization=organization,
        space=space,
        values=validated.get("values"),
    )
    return Response(GovernancePolicySerializer(policy).data, status=status.HTTP_201_CREATED)


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
    return (
        grants_role == OrganizationMembership.ROLE_BUSINESS_ADMIN
        and organization.id in org_ids
    )


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


class OrganizationListView(generics.ListCreateAPIView):
    """List organizations the user administers (super sees all)."""

    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        org_ids = _scoped_org_ids(self.request.user)
        qs = Organization.objects.all()
        return qs if org_ids is None else qs.filter(id__in=list(org_ids))

    def create(self, request, *args, **kwargs):
        if not is_platform_admin(request.user):
            raise PermissionDenied("Only platform administrators can create organizations.")
        serializer = OrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.save()
        from apps.audit.views import create_audit_log
        create_audit_log(request.user, "organization_create", "Organization", organization.id, request=request)
        return Response(OrganizationSerializer(organization).data, status=status.HTTP_201_CREATED)


class OrganizationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org_ids = _scoped_org_ids(self.request.user)
        qs = Organization.objects.all()
        return qs if org_ids is None else qs.filter(id__in=list(org_ids))

    def perform_update(self, serializer):
        organization = serializer.save()
        from apps.audit.views import create_audit_log
        create_audit_log(
            self.request.user,
            "organization_update",
            "Organization",
            organization.id,
            request=self.request,
        )


def _organization_lifecycle(request, pk, status_value, action):
    org_ids = _scoped_org_ids(request.user)
    qs = Organization.objects.all() if org_ids is None else Organization.objects.filter(id__in=list(org_ids))
    try:
        organization = qs.get(pk=pk)
    except Organization.DoesNotExist as exc:
        raise NotFound("Organization not found.") from exc
    if not is_platform_admin(request.user) and action == "archive":
        raise PermissionDenied("Only platform administrators can archive organizations.")
    organization.status = status_value
    organization.save(update_fields=["status", "updated_at"])
    from apps.audit.views import create_audit_log
    create_audit_log(request.user, f"organization_{action}", "Organization", organization.id, request=request)
    return Response(OrganizationSerializer(organization).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def organization_archive(request, pk):
    return _organization_lifecycle(request, pk, "archived", "archive")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def organization_restore(request, pk):
    return _organization_lifecycle(request, pk, "active", "restore")


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


class BusinessLineDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = BusinessLineSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org_ids = _scoped_org_ids(self.request.user)
        qs = BusinessLine.objects.select_related("organization")
        return qs if org_ids is None else qs.filter(organization_id__in=list(org_ids))

    def perform_update(self, serializer):
        line = serializer.save()
        from apps.audit.views import create_audit_log
        create_audit_log(self.request.user, "business_line_update", "BusinessLine", line.id, request=self.request)


def _business_line_lifecycle(request, pk, status_value, action):
    org_ids = _scoped_org_ids(request.user)
    qs = (
        BusinessLine.objects.all()
        if org_ids is None
        else BusinessLine.objects.filter(organization_id__in=list(org_ids))
    )
    try:
        line = qs.get(pk=pk)
    except BusinessLine.DoesNotExist as exc:
        raise NotFound("Business line not found.") from exc
    line.status = status_value
    line.save(update_fields=["status", "updated_at"])
    from apps.audit.views import create_audit_log
    create_audit_log(request.user, f"business_line_{action}", "BusinessLine", line.id, request=request)
    return Response(BusinessLineSerializer(line).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def business_line_archive(request, pk):
    return _business_line_lifecycle(request, pk, "archived", "archive")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def business_line_restore(request, pk):
    return _business_line_lifecycle(request, pk, "active", "restore")


def _can_manage_space(user, space):
    if is_platform_admin(user):
        return True
    org_ids, line_ids = admin_scope(user)
    return (
        space.organization_id in org_ids
        or space.business_line_id in line_ids
        or SpaceMembership.objects.filter(
            user=user, space=space, status="active", role=SpaceMembership.ROLE_OWNER
        ).exists()
    )


class SpaceAccessRequestListView(generics.ListAPIView):
    serializer_class = SpaceAccessRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        try:
            space = KnowledgeSpace.objects.get(pk=self.kwargs["pk"])
        except KnowledgeSpace.DoesNotExist as exc:
            raise NotFound("Space not found.") from exc
        if not _can_manage_space(self.request.user, space):
            raise PermissionDenied("You cannot review access requests for this space.")
        return SpaceAccessRequest.objects.filter(space=space).select_related("user", "reviewed_by")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_access_request_approve(request, pk, request_id):
    try:
        space = KnowledgeSpace.objects.get(pk=pk)
        access_request = SpaceAccessRequest.objects.get(pk=request_id, space=space)
    except (KnowledgeSpace.DoesNotExist, SpaceAccessRequest.DoesNotExist) as exc:
        raise NotFound("Access request not found.") from exc
    if not _can_manage_space(request.user, space):
        raise PermissionDenied("You cannot approve this access request.")
    if access_request.status != SpaceAccessRequest.STATUS_PENDING:
        return Response({"detail": "Request is already resolved."}, status=status.HTTP_409_CONFLICT)
    with transaction.atomic():
        membership, _ = SpaceMembership.objects.update_or_create(
            space=space,
            user=access_request.user,
            defaults={"role": access_request.role, "status": "active", "invited_by": request.user},
        )
        access_request.status = SpaceAccessRequest.STATUS_APPROVED
        access_request.reviewed_by = request.user
        access_request.reviewed_at = timezone.now()
        access_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    from apps.audit.views import create_audit_log
    create_audit_log(request.user, "space_access_request_approve", "KnowledgeSpace", space.id, request=request)
    from apps.notifications.services import notify
    notify(
        access_request.user,
        "space_access_approved",
        "Space access approved",
        body=f"Your request to join {space.name} has been approved.",
        link=f"/spaces/{space.id}",
        metadata={"space_id": str(space.id), "access_request_id": str(access_request.id)},
    )
    return Response(SpaceAccessRequestSerializer(access_request).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def space_access_request_reject(request, pk, request_id):
    try:
        space = KnowledgeSpace.objects.get(pk=pk)
        access_request = SpaceAccessRequest.objects.get(pk=request_id, space=space)
    except (KnowledgeSpace.DoesNotExist, SpaceAccessRequest.DoesNotExist) as exc:
        raise NotFound("Access request not found.") from exc
    if not _can_manage_space(request.user, space):
        raise PermissionDenied("You cannot reject this access request.")
    if access_request.status != SpaceAccessRequest.STATUS_PENDING:
        return Response({"detail": "Request is already resolved."}, status=status.HTTP_409_CONFLICT)
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        raise ValidationError({"reason": "A rejection reason is required."})
    if len(reason) > 2000:
        raise ValidationError({"reason": "Rejection reason is too long."})
    access_request.status = SpaceAccessRequest.STATUS_REJECTED
    access_request.rejection_reason = reason
    access_request.reviewed_by = request.user
    access_request.reviewed_at = timezone.now()
    access_request.save(update_fields=[
        "status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"
    ])
    from apps.audit.views import create_audit_log
    create_audit_log(
        request.user,
        "space_access_request_reject",
        "KnowledgeSpace",
        space.id,
        details={"access_request_id": str(access_request.id)},
        request=request,
    )
    from apps.notifications.services import notify
    notify(
        access_request.user,
        "space_access_rejected",
        "Space access request reviewed",
        body=f"Your request to join {space.name} was not approved.",
        metadata={"space_id": str(space.id), "access_request_id": str(access_request.id)},
    )
    return Response(SpaceAccessRequestSerializer(access_request).data)


User = get_user_model()


class ScopedAdminUserListView(generics.ListAPIView):
    """Paginated users visible in the caller's organization/business scope."""
    permission_classes = [CanViewAdminOperations]

    def list(self, request, *args, **kwargs):
        if is_platform_admin(request.user):
            qs = User.objects.all()
        else:
            org_ids, line_ids = admin_scope(request.user)
            scoped_user_ids = set(OrganizationMembership.objects.filter(
                organization_id__in=org_ids | set()
            ).values_list("user_id", flat=True))
            if line_ids:
                scoped_user_ids.update(OrganizationMembership.objects.filter(
                    business_line_id__in=line_ids
                ).values_list("user_id", flat=True))
                scoped_user_ids.update(SpaceMembership.objects.filter(
                    space__business_line_id__in=line_ids
                ).values_list("user_id", flat=True))
            scoped_user_ids.update(SpaceMembership.objects.filter(
                space__organization_id__in=org_ids
            ).values_list("user_id", flat=True))
            qs = User.objects.filter(id__in=scoped_user_ids)
        query = request.query_params.get("q", "").strip()
        if query:
            qs = qs.filter(email__icontains=query)
        page = self.paginate_queryset(qs.order_by("email"))
        rows = [{"id": str(user.id), "email": user.email, "is_active": user.is_active} for user in page]
        return self.get_paginated_response(rows)


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def scoped_user_assignment(request, user_id):
    try:
        target = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise NotFound("User not found.") from exc
    scope = request.data.get("scope")
    role = request.data.get("role")
    scope_id = request.data.get("scope_id")
    if scope == "organization":
        try:
            organization = Organization.objects.get(pk=scope_id)
        except Organization.DoesNotExist as exc:
            raise NotFound("Organization not found.") from exc
        if not is_platform_admin(request.user) and organization.id not in _scoped_org_ids(request.user):
            raise PermissionDenied("You cannot manage this organization.")
        if role not in {OrganizationMembership.ROLE_ORG_ADMIN, OrganizationMembership.ROLE_BUSINESS_ADMIN}:
            raise ValidationError({"role": "Invalid organization role."})
        if role == OrganizationMembership.ROLE_ORG_ADMIN and not is_platform_admin(request.user):
            raise PermissionDenied("Only platform administrators can grant organization admin.")
        if request.method == "POST":
            assignment, _ = OrganizationMembership.objects.get_or_create(
                user=target, organization=organization, business_line=None, role=role
            )
        else:
            OrganizationMembership.objects.filter(
                user=target,
                organization=organization,
                business_line=None,
                role=role,
            ).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
    elif scope == "space":
        try:
            space = KnowledgeSpace.objects.get(pk=scope_id)
        except KnowledgeSpace.DoesNotExist as exc:
            raise NotFound("Space not found.") from exc
        if not _can_manage_space(request.user, space):
            raise PermissionDenied("You cannot manage this space.")
        if role not in dict(SpaceMembership.ROLE_CHOICES):
            raise ValidationError({"role": "Invalid space role."})
        if request.method == "POST":
            assignment, _ = SpaceMembership.objects.update_or_create(
                user=target,
                space=space,
                defaults={
                    "role": role,
                    "status": "active",
                    "invited_by": request.user,
                },
            )
        else:
            is_last_owner = (
                role == SpaceMembership.ROLE_OWNER
                and SpaceMembership.objects.filter(
                    space=space,
                    role=role,
                    status="active",
                ).count()
                <= 1
            )
            if is_last_owner:
                raise ValidationError({"detail": "Cannot remove the last owner."})
            SpaceMembership.objects.filter(user=target, space=space, role=role).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
    else:
        raise ValidationError({"scope": "Use organization or space."})
    from apps.audit.views import create_audit_log
    create_audit_log(
        request.user,
        "scoped_role_assign",
        "User",
        target.id,
        details={"scope": scope, "scope_id": str(scope_id), "role": role},
        request=request,
    )
    return Response(
        {
            "id": str(assignment.id),
            "user_id": str(target.id),
            "scope": scope,
            "role": role,
        },
        status=status.HTTP_201_CREATED,
    )
