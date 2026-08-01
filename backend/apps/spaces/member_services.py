"""Versioned, owner-only non-owner member lifecycle service."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.rbac.capabilities import resolve_capabilities

from .governed import (
    GovernedWorkflowError,
    complete_operation_record,
    digest_payload,
    durable_governed_transaction,
    normalize_text,
    operation_record,
    replay_response,
)
from .models import KnowledgeSpace, OwnershipTransfer, SpaceMembership


MUTABLE_ROLES = {
    SpaceMembership.ROLE_SPACE_ADMIN,
    SpaceMembership.ROLE_MEMBER,
    SpaceMembership.ROLE_GUEST,
}


def member_body(membership, *, canonical_owner_id=None):
    return {
        "id": str(membership.id),
        "user": {
            "id": str(membership.user_id),
            "email": membership.user.email,
            "display_name": getattr(membership.user, "get_full_name", lambda: "")() or membership.user.username,
        },
        "role": membership.role,
        "status": membership.status,
        "expires_at": membership.expires_at.isoformat() if membership.expires_at else None,
        "effective": membership.is_effective,
        "source_kind": membership.source_kind,
        "membership_version": membership.membership_version,
        "immutable_owner": membership.user_id == canonical_owner_id,
        "updated_at": membership.updated_at.isoformat(),
    }


def list_members(*, actor, space):
    _require_member_management(actor=actor, space_id=space.id)
    actor_role = SpaceMembership.objects.filter(
        space=space, user=actor, status="active", expires_at__isnull=True
    ).values_list("role", flat=True).first()
    if actor_role not in {SpaceMembership.ROLE_OWNER, SpaceMembership.ROLE_SPACE_ADMIN} or space.status not in {"active", "archived"}:
        raise NotFound("Workspace not found.")
    rows = SpaceMembership.objects.filter(space=space).select_related("user").order_by("created_at", "id")[:100]
    return {"results": [member_body(row, canonical_owner_id=space.owner_id) for row in rows], "next_cursor": None}


def _require_member_management(*, actor, space_id):
    try:
        capabilities = resolve_capabilities(actor, space_id=space_id)["capabilities"]
    except NotFound as exc:
        raise NotFound("Workspace not found.") from exc
    if "workspace.members.manage" in capabilities:
        return
    archived_owner = KnowledgeSpace.objects.filter(
        pk=space_id,
        status="archived",
        owner=actor,
        memberships__user=actor,
        memberships__role=SpaceMembership.ROLE_OWNER,
        memberships__status="active",
        memberships__expires_at__isnull=True,
    ).exists()
    if not archived_owner:
        raise NotFound("Workspace not found.")


def _reason(reason_code, reason_text):
    if not reason_code or not isinstance(reason_code, str) or len(reason_code) > 64:
        raise ValidationError({"reason_code": "A controlled reason code is required."})
    return normalize_text(reason_text or "", max_length=500, field="reason_text", required=False)


def _audit(actor, *, space, membership, event, reason_code, reason_text):
    from apps.audit.views import create_audit_log

    return create_audit_log(
        user=actor,
        action="space_member_update" if event == "updated" else "space_member_remove",
        target_type="SpaceMembership",
        target_id=membership.id,
        details={
            "member_event": event,
            "member_user_id": str(membership.user_id),
            "membership_version": membership.membership_version,
            "reason_code": reason_code,
            "reason_text": reason_text,
        },
        organization_id=space.organization_id,
        business_line_id=space.business_line_id,
        space_id=space.id,
    )


def _fence_member_access(*, space, target_user):
    """Cancel active turns/replay surfaces before access becomes ineffective."""

    from apps.chat.models import ChatSession, ChatTurn, ConversationShare

    sessions = (
        ChatSession.objects.select_for_update(of=("self",))
        .filter(space=space, user=target_user)
        .order_by("pk")
    )
    session_ids = list(sessions.values_list("pk", flat=True))
    turns = (
        ChatTurn.objects.select_for_update(of=("self",))
        .filter(
        session_id__in=session_ids,
        status__in=[
            ChatTurn.STATUS_ACCEPTED,
            ChatTurn.STATUS_RETRIEVING,
            ChatTurn.STATUS_REASONING,
            ChatTurn.STATUS_ANSWERING,
            ChatTurn.STATUS_SAVING,
        ],
        )
        .order_by("pk")
    )
    turn_ids = list(turns.values_list("pk", flat=True))
    shares = (
        ConversationShare.objects.select_for_update(of=("self",))
        .filter(
            session_id__in=session_ids,
            revoked_at__isnull=True,
        )
        .order_by("pk")
    )
    share_ids = list(shares.values_list("pk", flat=True))

    if session_ids:
        from apps.chat.coordination import create_redis_client, session_lease_key

        try:
            client = create_redis_client()
            client.delete(*(session_lease_key(session_id) for session_id in session_ids))
        except Exception as exc:
            raise GovernedWorkflowError(
                "chat_coordination_unavailable",
                status_code=503,
            ) from exc

    now = timezone.now()
    ChatTurn.objects.filter(pk__in=turn_ids).update(
        status=ChatTurn.STATUS_CANCELLED,
        error_code="membership_revoked",
        completed_at=now,
        updated_at=now,
    )
    ChatSession.objects.filter(pk__in=session_ids).update(is_active=False, updated_at=now)
    ConversationShare.objects.filter(pk__in=share_ids).update(revoked_at=now)


def update_member(
    *,
    actor,
    space_id,
    membership_id,
    expected_version,
    fields,
    reason_code,
    reason_text,
    idempotency_key,
):
    _require_member_management(actor=actor, space_id=space_id)
    unknown = sorted(set(fields) - {"role", "status", "expires_at"})
    if unknown:
        raise ValidationError({"unknown_fields": unknown})
    if not fields:
        raise ValidationError({"member": "At least one mutable field is required."})
    reason_text = _reason(reason_code, reason_text)
    digest = digest_payload(
        {
            "space_id": space_id,
            "membership_id": membership_id,
            "expected_version": expected_version,
            "fields": fields,
            "reason_code": reason_code,
            "reason_text": reason_text,
        }
    )
    with durable_governed_transaction():
        with operation_record(
            actor=actor,
            operation_code="space_member.update",
            key=idempotency_key,
            request_digest=digest,
            target_uuid=membership_id,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            reference = SpaceMembership.objects.only("user_id").filter(
                pk=membership_id, space_id=space_id
            ).first()
            if reference is None:
                raise NotFound("Member not found.")
            users = list(
                get_user_model()
                .objects.select_for_update(of=("self",))
                .filter(pk__in={actor.id, reference.user_id})
                .order_by("pk")
            )
            target_user = next((row for row in users if row.id == reference.user_id), None)
            space = KnowledgeSpace.objects.select_for_update(of=("self",)).order_by("pk").get(pk=space_id)
            membership = SpaceMembership.objects.select_for_update(of=("self",)).select_related("user").order_by("pk").get(pk=membership_id, space=space)
            actor_role = SpaceMembership.objects.filter(
                space=space, user=actor, status="active", expires_at__isnull=True
            ).values_list("role", flat=True).first()
            if actor_role not in {SpaceMembership.ROLE_OWNER, SpaceMembership.ROLE_SPACE_ADMIN} or space.status not in {"active", "archived"}:
                raise NotFound("Workspace not found.")
            if membership.user_id == space.owner_id or membership.role == SpaceMembership.ROLE_OWNER:
                raise GovernedWorkflowError("ownership_workflow_required")
            if target_user is None or not target_user.is_active:
                raise GovernedWorkflowError("member_not_active")
            if membership.membership_version != expected_version:
                raise GovernedWorkflowError("stale_membership_version", details={"current_version": membership.membership_version})
            next_role = fields.get("role", membership.role)
            next_status = fields.get("status", membership.status)
            if next_role not in MUTABLE_ROLES:
                raise GovernedWorkflowError("ownership_workflow_required")
            if actor_role == SpaceMembership.ROLE_SPACE_ADMIN and (
                membership.role == SpaceMembership.ROLE_SPACE_ADMIN
                or next_role == SpaceMembership.ROLE_SPACE_ADMIN
            ):
                raise GovernedWorkflowError("workspace_admin_required", status_code=403)
            if next_status not in {"active", "revoked"}:
                raise ValidationError({"status": "Unsupported member status."})
            expires_at = membership.expires_at
            if "expires_at" in fields:
                from rest_framework.fields import DateTimeField

                expires_at = (
                    None
                    if fields["expires_at"] in (None, "")
                    else DateTimeField().run_validation(fields["expires_at"])
                )
            if space.status != "active" and (
                "role" in fields
                or next_status == "active"
                and (expires_at is None or expires_at > timezone.now())
            ):
                raise GovernedWorkflowError("workspace_not_writable")
            if next_status != "active" or (expires_at and expires_at <= timezone.now()):
                _fence_member_access(space=space, target_user=target_user)
            membership.role = next_role
            membership.status = next_status
            membership.expires_at = expires_at
            membership.membership_version += 1
            membership.save(update_fields=["role", "status", "expires_at", "membership_version", "updated_at"])
            _audit(actor, space=space, membership=membership, event="updated", reason_code=reason_code, reason_text=reason_text)
            body = member_body(membership, canonical_owner_id=space.owner_id)
            complete_operation_record(operation, status_code=200, body=body, result_reference=membership.id)
            return body


def remove_member(
    *,
    actor,
    space_id,
    membership_id,
    expected_version,
    reason_code,
    reason_text,
    idempotency_key,
):
    _require_member_management(actor=actor, space_id=space_id)
    reason_text = _reason(reason_code, reason_text)
    digest = digest_payload(
        {
            "space_id": space_id,
            "membership_id": membership_id,
            "expected_version": expected_version,
            "reason_code": reason_code,
            "reason_text": reason_text,
        }
    )
    with durable_governed_transaction():
        with operation_record(
            actor=actor,
            operation_code="space_member.remove",
            key=idempotency_key,
            request_digest=digest,
            target_uuid=membership_id,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            reference = SpaceMembership.objects.only("user_id").filter(pk=membership_id, space_id=space_id).first()
            if reference is None:
                raise NotFound("Member not found.")
            users = list(get_user_model().objects.select_for_update(of=("self",)).filter(pk__in={actor.id, reference.user_id}).order_by("pk"))
            target_user = next((row for row in users if row.id == reference.user_id), None)
            space = KnowledgeSpace.objects.select_for_update(of=("self",)).order_by("pk").get(pk=space_id)
            membership = SpaceMembership.objects.select_for_update(of=("self",)).select_related("user").order_by("pk").get(pk=membership_id, space=space)
            actor_role = SpaceMembership.objects.filter(
                space=space, user=actor, status="active", expires_at__isnull=True
            ).values_list("role", flat=True).first()
            if actor_role not in {SpaceMembership.ROLE_OWNER, SpaceMembership.ROLE_SPACE_ADMIN} or space.status not in {"active", "archived"}:
                raise NotFound("Workspace not found.")
            if membership.user_id == space.owner_id or membership.role == SpaceMembership.ROLE_OWNER:
                raise GovernedWorkflowError("ownership_workflow_required")
            if actor_role == SpaceMembership.ROLE_SPACE_ADMIN and membership.role == SpaceMembership.ROLE_SPACE_ADMIN:
                raise GovernedWorkflowError("workspace_admin_required", status_code=403)
            if membership.membership_version != expected_version:
                raise GovernedWorkflowError("stale_membership_version", details={"current_version": membership.membership_version})
            transfers = list(
                OwnershipTransfer.objects.select_for_update(of=("self",))
                .filter(
                    space=space,
                    to_owner_id=membership.user_id,
                    status=OwnershipTransfer.STATUS_PENDING,
                    mode=OwnershipTransfer.MODE_VOLUNTARY,
                )
                .order_by("pk")
            )
            if transfers:
                from .ownership_services import OwnershipTransferService

                for transfer in transfers:
                    transfer.status = OwnershipTransfer.STATUS_INVALIDATED
                    transfer.save(update_fields=["status"])
                    OwnershipTransferService._audit_transition(
                        actor=actor,
                        transfer=transfer,
                        event="ownership_transfer_invalidated_member_removed",
                    )
            if target_user is not None:
                _fence_member_access(space=space, target_user=target_user)
            membership.status = "revoked"
            membership.membership_version += 1
            membership.save(update_fields=["status", "membership_version", "updated_at"])
            _audit(actor, space=space, membership=membership, event="removed", reason_code=reason_code, reason_text=reason_text)
            body = {"removed": True, "membership": member_body(membership, canonical_owner_id=space.owner_id)}
            complete_operation_record(operation, status_code=200, body=body, result_reference=membership.id)
            return body


__all__ = ["member_body", "list_members", "update_member", "remove_member"]
