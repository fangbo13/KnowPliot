"""Read-only impact preflight and transactional account-offboarding orchestration."""

from __future__ import annotations

import hashlib
import json
import uuid

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.rbac.capabilities import resolve_capabilities
from apps.spaces.models import KnowledgeSpace
from apps.spaces.ownership import effective_platform_admin
from apps.spaces.ownership_services import OwnershipTransferService
from apps.users.security import revoke_all_sessions


class OffboardingConflict(Exception):
    """Stable offboarding conflict code suitable for a 409 response."""


class OffboardingImpactService:
    @staticmethod
    def inspect(*, actor, subject) -> dict:
        from apps.audit.models import AuditLog
        from apps.rbac.models import UserRole
        from apps.chat.models import ComplianceExportJob, ConversationShare, Feedback, KnowledgeGapTicket
        from apps.knowledge.models import Document, IngestionJob
        from apps.spaces.models import AdminRegistrationCode, InviteCode, OrganizationMembership, SpaceEmailInvite
        from apps.users.models import AuthSession

        if not effective_platform_admin(actor):
            raise OffboardingConflict("insufficient_scope")
        owned_space_rows = list(
            KnowledgeSpace.objects.filter(
                owner=subject,
                status__in=("active", "archived"),
            )
            .order_by("id")
            .values("id", "name", "status", "ownership_version")
        )
        owned_spaces = [row["id"] for row in owned_space_rows]
        normalized = {
            "subject_id": str(subject.id),
            "is_active": subject.is_active,
            "owned_spaces": [str(space_id) for space_id in owned_spaces],
            "ownership_versions": {
                str(row["id"]): row["ownership_version"]
                for row in owned_space_rows
            },
        }
        active_platform_admin_roles = UserRole.objects.filter(
            role__name="admin", is_active=True, user__is_active=True
        )
        is_last_platform_admin = active_platform_admin_roles.filter(user=subject).exists() and not active_platform_admin_roles.exclude(user=subject).exists()
        active_memberships = OrganizationMembership.objects.filter(
            user=subject,
            is_active=True,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
        last_org_scopes = []
        last_business_scopes = []
        for membership in active_memberships.select_related("organization", "business_line"):
            peers = OrganizationMembership.objects.filter(
                organization=membership.organization,
                business_line=membership.business_line,
                role=membership.role,
                is_active=True,
                user__is_active=True,
            ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now())).exclude(user=subject)
            if peers.exists():
                continue
            destination = last_org_scopes if membership.business_line_id is None else last_business_scopes
            destination.append(
                {
                    "organization_id": str(membership.organization_id),
                    "business_line_id": str(membership.business_line_id) if membership.business_line_id else None,
                    "role": membership.role,
                }
            )
        has_admin_continuity_blocker = bool(is_last_platform_admin or last_org_scopes or last_business_scopes)
        normalized["last_platform_admin"] = is_last_platform_admin
        normalized["last_organization_admin_scopes"] = last_org_scopes
        normalized["last_business_admin_scopes"] = last_business_scopes
        impact_version = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "subject": {
                "id": str(subject.id),
                "display_name": subject.get_full_name() or subject.username,
                "is_active": subject.is_active,
            },
            "impact_version": impact_version,
            "blockers": {
                "owned_spaces": normalized["owned_spaces"],
                "owned_space_details": [
                    {
                        "id": str(row["id"]),
                        "display_name": row["name"],
                        "status": row["status"],
                        "ownership_version": row["ownership_version"],
                    }
                    for row in owned_space_rows
                ],
                "last_platform_admin": is_last_platform_admin,
                "last_organization_admin_scopes": last_org_scopes,
                "last_business_admin_scopes": last_business_scopes,
            },
            "actions": {
                "active_sessions": AuthSession.objects.filter(user=subject, revoked_at__isnull=True).count(),
                "active_conversation_shares": ConversationShare.objects.filter(owner=subject, revoked_at__isnull=True).count(),
                "active_invite_codes": InviteCode.objects.filter(created_by=subject, status="active", used_count=0).count(),
                "active_admin_registration_codes": AdminRegistrationCode.objects.filter(created_by=subject, status="active", used_count=0).count(),
                "pending_email_invites": SpaceEmailInvite.objects.filter(invited_by=subject, status="pending").count(),
                "open_feedback_reviews": Feedback.objects.filter(
                    reviewer=subject,
                    status__in=(Feedback.STATUS_PENDING_REVIEW, Feedback.STATUS_IN_REVIEW),
                ).count(),
                "open_knowledge_gap_tickets": KnowledgeGapTicket.objects.filter(
                    assignee=subject,
                    status__in=(KnowledgeGapTicket.STATUS_OPEN, KnowledgeGapTicket.STATUS_IN_PROGRESS),
                ).count(),
                "running_jobs": IngestionJob.objects.filter(
                    requested_by=subject,
                    status__in=("queued", "processing", "retrying"),
                ).count(),
            },
            "protected_history": {
                "documents": Document.objects.filter(uploaded_by=subject).count(),
                "crawls": 0,
                "audit_records": AuditLog.objects.filter(Q(user=subject) | Q(target_id=subject.id)).count(),
                "completed_export_jobs": ComplianceExportJob.objects.filter(
                    requested_by=subject,
                    status=ComplianceExportJob.STATUS_SUCCEEDED,
                ).count(),
            },
            "can_deactivate_without_successor": not owned_spaces and not has_admin_continuity_blocker,
        }


class OffboardingService:
    @staticmethod
    def _record_completion_audit(*, actor, subject_id, space_transfer_count, admin_succession_count):
        """Write a bounded, non-sensitive completion audit after the transaction commits."""

        from apps.audit.views import create_audit_log

        create_audit_log(
            actor,
            "user_deactivate",
            "User",
            target_id=subject_id,
            details={
                "event": "account_offboarding",
                "space_transfer_count": space_transfer_count,
                "admin_succession_count": admin_succession_count,
            },
        )

    @staticmethod
    def _apply_platform_admin_succession(*, actor, subject, succession_rows):
        """Grant the final platform-admin role before revoking the subject's role."""

        from apps.rbac.models import UserRole
        from apps.users.models import User

        mappings = [
            row for row in succession_rows or []
            if row.get("scope_type") == "platform" and row.get("role") == "admin"
        ]
        if len(mappings) != 1:
            raise OffboardingConflict("platform_admin_successor_required")
        try:
            successor = User.objects.select_for_update().get(pk=mappings[0]["successor_user_id"])
        except (User.DoesNotExist, KeyError, TypeError, ValueError) as exc:
            raise OffboardingConflict("invalid_admin_successor") from exc
        if not successor.is_active or successor.id == subject.id:
            raise OffboardingConflict("invalid_admin_successor")
        subject_assignment = UserRole.objects.select_for_update().filter(
            user=subject, role__name="admin", is_active=True
        ).select_related("role").first()
        if not subject_assignment:
            raise OffboardingConflict("offboarding_impact_changed")
        assignment, created = UserRole.objects.get_or_create(
            user=successor,
            role=subject_assignment.role,
            defaults={"assigned_by": actor, "is_active": True},
        )
        if not created and not assignment.is_active:
            assignment.is_active = True
            assignment.deactivated_at = None
            assignment.assigned_by = actor
            assignment.save(update_fields=["is_active", "deactivated_at", "assigned_by"])

    @staticmethod
    def _apply_admin_successions(*, subject, succession_rows, organization_blockers, business_blockers):
        """Grant mapped final-scope successors before revoking the subject's grants."""

        from apps.spaces.models import OrganizationMembership, SpaceMembership
        from apps.users.models import User

        expected = [*organization_blockers, *business_blockers]
        by_scope = {}
        for row in succession_rows or []:
            key = (
                str(row.get("organization_id")),
                str(row.get("business_line_id")) if row.get("business_line_id") else None,
                row.get("role"),
            )
            if key in by_scope:
                raise OffboardingConflict("invalid_admin_successor")
            by_scope[key] = row
        for blocker in expected:
            key = (
                blocker["organization_id"],
                blocker["business_line_id"],
                blocker["role"],
            )
            mapping = by_scope.get(key)
            if not mapping:
                raise OffboardingConflict("admin_successor_required")
            try:
                successor = User.objects.select_for_update().get(pk=mapping["successor_user_id"])
            except (User.DoesNotExist, KeyError, TypeError, ValueError) as exc:
                raise OffboardingConflict("invalid_admin_successor") from exc
            if not successor.is_active or successor.id == subject.id:
                raise OffboardingConflict("invalid_admin_successor")
            scope_spaces = SpaceMembership.objects.filter(
                user=successor,
                status="active",
                space__organization_id=blocker["organization_id"],
            )
            if blocker["business_line_id"]:
                scope_spaces = scope_spaces.filter(space__business_line_id=blocker["business_line_id"])
            if not scope_spaces.exists():
                raise OffboardingConflict("invalid_admin_successor")
            membership, created = OrganizationMembership.objects.get_or_create(
                user=successor,
                organization_id=blocker["organization_id"],
                business_line_id=blocker["business_line_id"],
                role=blocker["role"],
                defaults={"is_active": True},
            )
            if not created and not membership.is_active:
                membership.is_active = True
                membership.expires_at = None
                membership.save(update_fields=["is_active", "expires_at", "updated_at"])

    @staticmethod
    def offboard(*, actor, subject_id, impact_version, reason_code, space_transfers, admin_successions=None):
        from apps.users.models import User

        with transaction.atomic():
            subject = User.objects.select_for_update().get(pk=subject_id)
            impact = OffboardingImpactService.inspect(actor=actor, subject=subject)
            if impact["impact_version"] != impact_version:
                raise OffboardingConflict("offboarding_impact_changed")
            if impact["blockers"]["last_platform_admin"]:
                OffboardingService._apply_platform_admin_succession(
                    actor=actor,
                    subject=subject,
                    succession_rows=admin_successions,
                )
            if impact["blockers"]["last_organization_admin_scopes"] or impact["blockers"]["last_business_admin_scopes"]:
                OffboardingService._apply_admin_successions(
                    subject=subject,
                    succession_rows=admin_successions,
                    organization_blockers=impact["blockers"]["last_organization_admin_scopes"],
                    business_blockers=impact["blockers"]["last_business_admin_scopes"],
                )
            mapped_space_ids = {str(item.get("space_id")) for item in space_transfers}
            if any(space_id not in mapped_space_ids for space_id in impact["blockers"]["owned_spaces"]):
                raise OffboardingConflict("owner_successor_required")
            transfer_by_space = {str(item["space_id"]): item for item in space_transfers}
            for space_id in impact["blockers"]["owned_spaces"]:
                mapping = transfer_by_space[space_id]
                OwnershipTransferService.force(
                    actor=actor,
                    space_id=space_id,
                    to_owner_id=mapping["successor_user_id"],
                    expected_ownership_version=mapping["expected_ownership_version"],
                    idempotency_key=uuid.uuid4(),
                    reason_code=reason_code,
                )

            from apps.rbac.models import UserRole
            from apps.chat.models import ConversationShare, Feedback, KnowledgeGapTicket
            from apps.spaces.models import (
                AdminRegistrationCode,
                InviteCode,
                OrganizationMembership,
                SpaceEmailInvite,
                SpaceMembership,
            )

            SpaceMembership.objects.filter(user=subject, status="active").update(status="revoked")
            OrganizationMembership.objects.filter(user=subject, is_active=True).update(is_active=False)
            UserRole.objects.filter(user=subject, is_active=True).update(is_active=False)
            revoke_all_sessions(subject)
            ConversationShare.objects.filter(owner=subject, revoked_at__isnull=True).update(revoked_at=timezone.now())
            InviteCode.objects.filter(created_by=subject, status="active", used_count=0).update(status="revoked")
            AdminRegistrationCode.objects.filter(created_by=subject, status="active", used_count=0).update(status="revoked")
            SpaceEmailInvite.objects.filter(invited_by=subject, status="pending").update(status="revoked")
            Feedback.objects.filter(
                reviewer=subject,
                status__in=(Feedback.STATUS_PENDING_REVIEW, Feedback.STATUS_IN_REVIEW),
            ).update(reviewer=None, status=Feedback.STATUS_PENDING_REVIEW)
            KnowledgeGapTicket.objects.filter(
                assignee=subject,
                status__in=(KnowledgeGapTicket.STATUS_OPEN, KnowledgeGapTicket.STATUS_IN_PROGRESS),
            ).update(assignee=None, status=KnowledgeGapTicket.STATUS_OPEN)
            subject.is_active = False
            subject.deactivated_at = timezone.now()
            subject.deactivated_by = actor
            subject.deactivation_reason_code = reason_code
            subject.save(
                update_fields=[
                    "is_active",
                    "deactivated_at",
                    "deactivated_by",
                    "deactivation_reason_code",
                ]
            )
            transaction.on_commit(
                lambda: OffboardingService._record_completion_audit(
                    actor=actor,
                    subject_id=subject.id,
                    space_transfer_count=len(impact["blockers"]["owned_spaces"]),
                    admin_succession_count=len(admin_successions or []),
                )
            )
        return {"offboarded": True, "subject_id": str(subject_id)}


def _platform_offboarding_allowed(user) -> bool:
    return "platform.users.offboard" in resolve_capabilities(user)["capabilities"]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def offboarding_impact(request, user_id):
    from apps.users.models import User

    if not _platform_offboarding_allowed(request.user):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        subject = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    try:
        return Response(OffboardingImpactService.inspect(actor=request.user, subject=subject))
    except OffboardingConflict as error:
        return Response({"error_code": str(error)}, status=status.HTTP_409_CONFLICT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def offboarding_admin_successor_candidates(request, user_id):
    """Return only active users eligible to inherit a final scoped-admin grant."""

    from apps.spaces.models import SpaceMembership
    from apps.users.models import User

    if not _platform_offboarding_allowed(request.user):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        subject = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({"error_code": "resource_not_found"}, status=status.HTTP_404_NOT_FOUND)
    impact = OffboardingImpactService.inspect(actor=request.user, subject=subject)
    scope_type = request.query_params.get("scope_type")
    if scope_type == "platform":
        if not impact["blockers"]["last_platform_admin"] or request.query_params.get("role") != "admin":
            return Response({"error_code": "invalid_admin_scope"}, status=status.HTTP_400_BAD_REQUEST)
        query = request.query_params.get("q", "").strip()
        users = User.objects.filter(is_active=True).exclude(pk=subject.pk).exclude(pk=request.user.pk)
        if query:
            users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
        return Response({
            "results": [
                {"id": str(candidate.id), "display_name": candidate.get_full_name() or candidate.username}
                for candidate in users.order_by("username")[:50]
            ],
            "role": "admin",
            "next": None,
        })
    try:
        organization_id = request.query_params["organization_id"]
        business_line_id = request.query_params.get("business_line_id") or None
        role = request.query_params["role"]
    except KeyError:
        return Response({"error_code": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST)
    valid_scopes = {
        (scope["organization_id"], scope["business_line_id"], scope["role"])
        for scope in [
            *impact["blockers"]["last_organization_admin_scopes"],
            *impact["blockers"]["last_business_admin_scopes"],
        ]
    }
    if (organization_id, business_line_id, role) not in valid_scopes:
        return Response({"error_code": "invalid_admin_scope"}, status=status.HTTP_400_BAD_REQUEST)

    memberships = SpaceMembership.objects.filter(
        status="active",
        space__organization_id=organization_id,
    )
    if business_line_id:
        memberships = memberships.filter(space__business_line_id=business_line_id)
    query = request.query_params.get("q", "").strip()
    users = User.objects.filter(
        is_active=True,
        space_memberships__in=memberships,
    ).exclude(pk=subject.pk).exclude(pk=request.user.pk)
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    results = [
        {"id": str(candidate.id), "display_name": candidate.get_full_name() or candidate.username}
        for candidate in users.order_by("username").distinct()[:50]
    ]
    return Response({"results": results, "role": role, "next": None})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def offboard_user(request, user_id):
    if not _platform_offboarding_allowed(request.user):
        return Response({"error_code": "insufficient_scope"}, status=status.HTTP_403_FORBIDDEN)
    try:
        result = OffboardingService.offboard(
            actor=request.user,
            subject_id=user_id,
            impact_version=request.data["impact_version"],
            reason_code=request.data["reason_code"],
            space_transfers=request.data.get("space_transfers", []),
            admin_successions=request.data.get("admin_successions", []),
        )
    except (KeyError, TypeError, ValueError):
        return Response({"error_code": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST)
    except OffboardingConflict as error:
        return Response({"error_code": str(error)}, status=status.HTTP_409_CONFLICT)
    return Response(result)
