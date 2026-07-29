"""Canonical v3 access-code, invitation, and access-request services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import random
import secrets
import unicodedata
import uuid
from datetime import timedelta

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .governed import (
    GovernedWorkflowError,
    complete_operation_record,
    digest_payload,
    durable_governed_transaction,
    normalize_text,
    operation_record,
    replay_response,
)
from .models import (
    KnowledgeSpace,
    SpaceAccessCode,
    SpaceAccessRequest,
    SpaceInvitation,
    SpaceMembership,
)
from .permissions import ensure_workspace_writable


ROLE_STRENGTH = {
    SpaceMembership.ROLE_GUEST: 1,
    SpaceMembership.ROLE_MEMBER: 2,
    SpaceMembership.ROLE_REVIEWER: 3,
    SpaceMembership.ROLE_KNOWLEDGE_ADMIN: 4,
    SpaceMembership.ROLE_OWNER: 5,
}


def _pepper_map():
    peppers = getattr(settings, "SPACE_CREDENTIAL_PEPPERS", {}) or {}
    normalized = {int(version): str(secret) for version, secret in peppers.items() if str(secret)}
    if not normalized:
        raise GovernedWorkflowError(
            "workspace_join_not_ready",
            "Workspace credential peppers are not configured.",
            status_code=503,
        )
    return normalized


def _current_pepper():
    version = int(getattr(settings, "SPACE_CREDENTIAL_PEPPER_VERSION", 1))
    peppers = _pepper_map()
    if version not in peppers:
        raise GovernedWorkflowError("workspace_join_not_ready", status_code=503)
    return version, peppers[version]


def _credential_digest(raw: str, pepper: str, *, domain: str) -> str:
    message = f"knowpilot:{domain}:{raw}".encode("utf-8")
    return hmac.new(pepper.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _new_secret(*, domain: str):
    raw = secrets.token_urlsafe(32)
    version, pepper = _current_pepper()
    return raw, version, _credential_digest(raw, pepper, domain=domain)


def _lookup_secret(model, raw, *, domain, hash_field, version_field):
    raw = normalize_text(raw, max_length=500, field="credential")
    match = None
    for version, pepper in sorted(_pepper_map().items()):
        digest = _credential_digest(raw, pepper, domain=domain)
        candidate = model.objects.filter(
            **{hash_field: digest, version_field: version}
        ).first()
        if candidate is not None and hmac.compare_digest(
            getattr(candidate, hash_field), digest
        ):
            match = candidate
    return match


def _email_hmac(email: str, *, version=None):
    normalized = unicodedata.normalize("NFC", email).strip().lower()
    if not normalized or "@" not in normalized or len(normalized) > 254:
        raise ValidationError({"target_email": "A valid email is required."})
    if version is None:
        version, pepper = _current_pepper()
    else:
        pepper = _pepper_map().get(int(version))
        if pepper is None:
            raise GovernedWorkflowError("workspace_join_not_ready", status_code=503)
    return normalized, _credential_digest(normalized, pepper, domain="invitation-email")


def _fernet():
    material = getattr(settings, "SPACE_INVITATION_ENCRYPTION_KEY", "")
    if not material:
        raise GovernedWorkflowError(
            "workspace_join_not_ready",
            "Workspace invitation encryption is not configured.",
            status_code=503,
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(f"knowpilot-invite:{material}".encode()).digest())
    return Fernet(key)


def _verified_user_for_email(normalized_email):
    """Resolve only an active account that owns this verified email."""

    try:
        from allauth.account.models import EmailAddress
    except ImportError:
        return None
    address = (
        EmailAddress.objects.select_related("user")
        .filter(
            email__iexact=normalized_email,
            verified=True,
            user__is_active=True,
        )
        .order_by("pk")
        .first()
    )
    return address.user if address is not None else None


def _actor_owns_verified_email(actor, normalized_email):
    try:
        from allauth.account.models import EmailAddress
    except ImportError:
        return False
    return EmailAddress.objects.filter(
        user=actor,
        email__iexact=normalized_email,
        verified=True,
    ).exists()


def _verified_target_keys(user):
    """Return canonical user/email target keys without exposing plaintext."""

    user_id = getattr(user, "id", user)
    keys = {f"user:{user_id}"}
    try:
        from allauth.account.models import EmailAddress
    except ImportError:
        return keys
    verified_emails = EmailAddress.objects.filter(
        user_id=user_id,
        verified=True,
    ).values_list("email", flat=True)
    for email in verified_emails:
        for version in _pepper_map():
            _, email_hmac = _email_hmac(email, version=version)
            keys.add(f"email:{email_hmac}")
    return keys


def _strict(payload, allowed):
    if not isinstance(payload, dict):
        raise ValidationError({"detail": "A JSON object is required."})
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise ValidationError({"unknown_fields": unknown})


def _completed_error_response(operation, *, code, status_code, result_reference=None):
    from rest_framework.response import Response

    body = {
        "detail": code,
        "code": code,
        "error": code,
        "errors": {"detail": code},
    }
    complete_operation_record(
        operation,
        status_code=status_code,
        body=body,
        result_reference=result_reference,
    )
    return Response(body, status=status_code)


def _lock_active_owner_space(*, actor, space_id, allow_archived=False):
    """Lock and revalidate the canonical active owner boundary."""

    try:
        space = (
            KnowledgeSpace.objects.select_for_update(of=("self",))
            .order_by("pk")
            .get(pk=space_id)
        )
    except KnowledgeSpace.DoesNotExist as exc:
        raise NotFound("Workspace not found.") from exc
    owner_mirror = (
        SpaceMembership.objects.select_for_update(of=("self",))
        .filter(
            space=space,
            user=actor,
            role=SpaceMembership.ROLE_OWNER,
            status="active",
            expires_at__isnull=True,
        )
        .order_by("pk")
        .first()
    )
    if not actor.is_active or space.owner_id != actor.id or owner_mirror is None:
        raise GovernedWorkflowError(
            "workspace_owner_required",
            status_code=403,
        )
    parents_active = (
        space.organization.status == "active"
        and (
            space.business_line_id is None
            or space.business_line.status == "active"
        )
    )
    if space.status != "active" or not parents_active:
        if allow_archived and space.status == "archived" and parents_active:
            return space
        raise GovernedWorkflowError("workspace_not_writable")
    return space


def _audit(actor, *, space, event, resource, details=None):
    from apps.audit.views import create_audit_log

    safe = {"join_event": event, "resource_id": str(resource.id)}
    if details:
        safe.update(details)
    return create_audit_log(
        user=actor,
        action="space_update",
        target_type=type(resource).__name__,
        target_id=resource.id,
        details=safe,
        organization_id=space.organization_id,
        business_line_id=space.business_line_id,
        space_id=space.id,
    )


def _notify_actionable(*, recipient, type, title, body, action_kind, resource_type, resource_uuid, resource_version, allowed_actions, deep_link):
    from apps.notifications.models import Notification

    if not deep_link.startswith("/") or deep_link.startswith("//"):
        raise GovernedWorkflowError("unsafe_notification_deep_link")
    return Notification.objects.create(
        recipient=recipient,
        type=type,
        title=title,
        body=body,
        level="info",
        link=deep_link,
        action_kind=action_kind,
        resource_type=resource_type,
        resource_uuid=resource_uuid,
        resource_version=resource_version,
        allowed_actions=allowed_actions,
        action_state=Notification.ACTION_AVAILABLE,
        deep_link=deep_link,
        metadata={},
    )


def _user_delivery_key(user_or_id):
    return f"user:{getattr(user_or_id, 'id', user_or_id)}"


def _invitation_delivery_key(invitation):
    if invitation.target_user_uuid:
        return _user_delivery_key(invitation.target_user_uuid)
    if invitation.target_email_hmac:
        return f"email_hmac:{invitation.target_email_hmac}"
    raise GovernedWorkflowError("invitation_delivery_target_missing")


def _enqueue_join_delivery(
    *,
    aggregate_type,
    aggregate_uuid,
    transition,
    transition_version,
    recipient_key,
    space_id,
    deep_link,
):
    from apps.notifications.outbox_services import (
        enqueue_action_outbox,
        wake_action_outbox,
    )

    if not deep_link.startswith("/") or deep_link.startswith("//"):
        raise GovernedWorkflowError("unsafe_notification_deep_link")
    event = enqueue_action_outbox(
        aggregate_type=aggregate_type,
        aggregate_uuid=aggregate_uuid,
        transition=transition,
        transition_version=transition_version,
        recipient_key=recipient_key,
        payload={
            "schema_version": 1,
            "event": transition,
            "resource_type": aggregate_type,
            "resource_id": str(aggregate_uuid),
            "resource_version": transition_version,
            "space_id": str(space_id),
            "deep_link": deep_link,
        },
    )
    wake_action_outbox(event.id)
    return event


def _mark_notifications(*, resource_type, resource_uuid, version, actioned=True):
    from apps.notifications.models import Notification

    values = {
        "resource_version": version,
        "allowed_actions": [],
        "action_state": Notification.ACTION_ACTIONED if actioned else Notification.ACTION_STALE,
        "is_read": True,
        "read_at": timezone.now(),
    }
    if actioned:
        values["actioned_at"] = timezone.now()
    notification_ids = list(
        Notification.objects.select_for_update(of=("self",))
        .filter(
            resource_type=resource_type,
            resource_uuid=resource_uuid,
            action_state=Notification.ACTION_AVAILABLE,
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    Notification.objects.filter(pk__in=notification_ids).update(**values)


def _access_code_body(code, *, raw=None):
    body = {
        "id": str(code.id),
        "space_id": str(code.space_id),
        "display_prefix": code.display_prefix,
        "role_ceiling": code.role_ceiling,
        "expires_at": code.expires_at.isoformat(),
        "max_uses": code.max_uses,
        "used_count": code.used_count,
        "max_pending": code.max_pending,
        "pending_count": code.pending_count,
        "status": code.status,
        "version": code.version,
    }
    if raw is not None:
        body["code"] = raw
    return body


def issue_access_code(*, actor, space, payload, idempotency_key):
    _strict(payload, {"role_ceiling", "expires_at", "max_uses", "max_pending"})
    role = payload.get("role_ceiling")
    if role not in {SpaceMembership.ROLE_MEMBER, SpaceMembership.ROLE_GUEST}:
        raise ValidationError({"role_ceiling": "Only member or guest is supported."})
    from rest_framework.fields import DateTimeField

    expires_at = DateTimeField().run_validation(payload.get("expires_at"))
    if expires_at <= timezone.now():
        raise ValidationError({"expires_at": "Must be in the future."})
    try:
        max_uses = int(payload.get("max_uses"))
        max_pending = int(payload.get("max_pending"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"limits": "max_uses and max_pending must be integers."}) from exc
    if not 1 <= max_uses <= 10000 or not 1 <= max_pending <= max_uses:
        raise ValidationError({"limits": "Invalid use/pending limits."})
    digest = digest_payload({"space_id": space.id, "role": role, "expires_at": expires_at, "max_uses": max_uses, "max_pending": max_pending})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code="space_access_code.issue", key=idempotency_key, request_digest=digest, target_uuid=space.id) as (operation, replay):
            if replay:
                return replay_response(operation)
            space = _lock_active_owner_space(
                actor=actor,
                space_id=space.id,
            )
            raw, version, secret_hash = _new_secret(domain="access-code")
            code = SpaceAccessCode.objects.create(
                space=space,
                created_by=actor,
                secret_hash=secret_hash,
                pepper_version=version,
                display_prefix=raw[:8],
                role_ceiling=role,
                max_uses=max_uses,
                max_pending=max_pending,
                policy_version=1,
                expires_at=expires_at,
            )
            _audit(actor, space=space, event="access_code_issued", resource=code, details={"role_ceiling": role, "display_prefix": code.display_prefix})
            body = _access_code_body(code, raw=raw)
            complete_operation_record(operation, status_code=201, body=body, result_reference=code.id)
            return body


def revoke_access_code(*, actor, space, code_id, expected_version, reason_code, idempotency_key):
    digest = digest_payload({"space_id": space.id, "code_id": code_id, "expected_version": expected_version, "reason_code": reason_code})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code="space_access_code.revoke", key=idempotency_key, request_digest=digest, target_uuid=code_id) as (operation, replay):
            if replay:
                return replay_response(operation)
            space = _lock_active_owner_space(
                actor=actor,
                space_id=space.id,
                allow_archived=True,
            )
            try:
                code = SpaceAccessCode.objects.select_for_update(of=("self",)).order_by("pk").get(pk=code_id, space=space)
            except SpaceAccessCode.DoesNotExist as exc:
                raise NotFound("Access code not found.") from exc
            if code.version != expected_version:
                raise GovernedWorkflowError("stale_code_version", details={"current_version": code.version})
            if code.status != SpaceAccessCode.STATUS_REVOKED:
                code.status = SpaceAccessCode.STATUS_REVOKED
                code.revoked_at = timezone.now()
                code.version += 1
                code.save(update_fields=["status", "revoked_at", "version", "updated_at"])
            _audit(actor, space=space, event="access_code_revoked", resource=code, details={"reason_code": reason_code})
            body = _access_code_body(code)
            complete_operation_record(operation, status_code=200, body=body, result_reference=code.id)
            return body


def _request_body(row):
    return {
        "id": str(row.id),
        "space_id": str(row.space_id),
        "requester_uuid": str(row.user_id),
        "source_kind": row.source_kind,
        "role": row.role,
        "role_ceiling": row.role_ceiling,
        "reason": row.reason,
        "status": row.status,
        "request_version": row.request_version,
        "expires_at": row.expires_at.isoformat(),
        "decision_reason_code": row.decision_reason_code,
        "resulting_membership_uuid": str(row.resulting_membership_uuid) if row.resulting_membership_uuid else None,
    }


def redeem_access_code(*, actor, raw_code, reason, idempotency_key):
    reason = normalize_text(reason or "", max_length=500, field="reason", required=False)
    request_digest = digest_payload({"actor_id": actor.id, "code": digest_payload(raw_code), "reason": reason})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code="space_access_code.redeem", key=idempotency_key, request_digest=request_digest) as (operation, replay):
            if replay:
                return replay_response(operation)
            code_reference = _lookup_secret(SpaceAccessCode, raw_code, domain="access-code", hash_field="secret_hash", version_field="pepper_version")
            if code_reference is None:
                raise GovernedWorkflowError("access_code_not_available", status_code=404)
            space = KnowledgeSpace.objects.select_for_update(of=("self",)).order_by("pk").get(pk=code_reference.space_id)
            membership = SpaceMembership.objects.select_for_update(of=("self",)).filter(space=space, user=actor).order_by("pk").first()
            code = SpaceAccessCode.objects.select_for_update(of=("self",)).order_by("pk").get(pk=code_reference.id)
            existing = SpaceAccessRequest.objects.select_for_update(of=("self",)).filter(space=space, user=actor, status=SpaceAccessRequest.STATUS_PENDING).order_by("pk").first()
            if (
                code.status == SpaceAccessCode.STATUS_ACTIVE
                and code.expires_at <= timezone.now()
            ):
                code.status = SpaceAccessCode.STATUS_EXPIRED
                code.version += 1
                code.save(update_fields=["status", "version", "updated_at"])
                return _completed_error_response(
                    operation,
                    code="access_code_not_available",
                    status_code=404,
                    result_reference=code.id,
                )
            if (
                code.status != SpaceAccessCode.STATUS_ACTIVE
                or space.status != "active"
                or not actor.is_active
            ):
                raise GovernedWorkflowError("access_code_not_available", status_code=404)
            if membership is not None and membership.is_effective:
                raise GovernedWorkflowError("already_member")
            if existing is not None and existing.expires_at <= timezone.now():
                existing.status = SpaceAccessRequest.STATUS_EXPIRED
                existing.request_version += 1
                existing.save(
                    update_fields=["status", "request_version", "updated_at"]
                )
                if existing.access_code_id == code.id and code.pending_count:
                    code.pending_count -= 1
                    code.save(update_fields=["pending_count", "updated_at"])
                _mark_notifications(
                    resource_type="space_access_request",
                    resource_uuid=existing.id,
                    version=existing.request_version,
                    actioned=False,
                )
                existing = None
            if existing is None and (
                code.used_count >= code.max_uses
                or code.pending_count >= code.max_pending
            ):
                raise GovernedWorkflowError("access_code_not_available", status_code=404)
            if existing is None:
                row = SpaceAccessRequest.objects.create(
                    space=space,
                    user=actor,
                    role=code.role_ceiling,
                    role_ceiling=code.role_ceiling,
                    source_kind=SpaceAccessRequest.SOURCE_ACCESS_CODE,
                    access_code=code,
                    access_code_version=code.version,
                    discovery_policy_version=None,
                    reason=reason,
                    status=SpaceAccessRequest.STATUS_PENDING,
                )
                code.used_count += 1
                code.pending_count += 1
                code.save(update_fields=["used_count", "pending_count", "updated_at"])
                owner = space.owner
                _notify_actionable(
                    recipient=owner,
                    type="space_access_request",
                    title="Workspace access requested",
                    body="A user requested access to a workspace you own.",
                    action_kind="space_access_request",
                    resource_type="space_access_request",
                    resource_uuid=row.id,
                    resource_version=row.request_version,
                    allowed_actions=["approve", "reject"],
                    deep_link=f"/workspace/{space.id}/manage/access",
                )
                _audit(actor, space=space, event="access_request_submitted", resource=row, details={"source_kind": "access_code"})
                _enqueue_join_delivery(
                    aggregate_type="space_access_request",
                    aggregate_uuid=row.id,
                    transition="submitted",
                    transition_version=row.request_version,
                    recipient_key=_user_delivery_key(owner.id),
                    space_id=space.id,
                    deep_link=f"/workspace/{space.id}/manage/access",
                )
            else:
                row = existing
            body = _request_body(row)
            complete_operation_record(operation, status_code=202, body=body, result_reference=row.id)
            return body


def create_discovery_request(*, actor, space, reason, idempotency_key):
    reason = normalize_text(reason or "", max_length=500, field="reason", required=False)
    digest = digest_payload({"actor_id": actor.id, "space_id": space.id, "reason": reason, "source": "discovery"})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code="space_access_request.discovery", key=idempotency_key, request_digest=digest, target_uuid=space.id) as (operation, replay):
            if replay:
                return replay_response(operation)
            space = KnowledgeSpace.objects.select_for_update(of=("self",)).order_by("pk").get(pk=space.id)
            ensure_workspace_writable(space)
            membership = SpaceMembership.objects.select_for_update(of=("self",)).filter(space=space, user=actor).order_by("pk").first()
            if membership and membership.is_effective:
                raise GovernedWorkflowError("already_member")
            existing = SpaceAccessRequest.objects.select_for_update(of=("self",)).filter(space=space, user=actor, status="pending").order_by("pk").first()
            if existing is None:
                row = SpaceAccessRequest.objects.create(
                    space=space,
                    user=actor,
                    role=SpaceMembership.ROLE_GUEST,
                    role_ceiling=SpaceMembership.ROLE_GUEST,
                    source_kind=SpaceAccessRequest.SOURCE_DISCOVERY,
                    discovery_policy_version=1,
                    reason=reason,
                )
                _notify_actionable(
                    recipient=space.owner,
                    type="space_access_request",
                    title="Workspace access requested",
                    body="A user requested access to a workspace you own.",
                    action_kind="space_access_request",
                    resource_type="space_access_request",
                    resource_uuid=row.id,
                    resource_version=row.request_version,
                    allowed_actions=["approve", "reject"],
                    deep_link=f"/workspace/{space.id}/manage/access",
                )
                _audit(actor, space=space, event="access_request_submitted", resource=row, details={"source_kind": "discovery"})
                _enqueue_join_delivery(
                    aggregate_type="space_access_request",
                    aggregate_uuid=row.id,
                    transition="submitted",
                    transition_version=row.request_version,
                    recipient_key=_user_delivery_key(space.owner_id),
                    space_id=space.id,
                    deep_link=f"/workspace/{space.id}/manage/access",
                )
            else:
                row = existing
            body = _request_body(row)
            complete_operation_record(operation, status_code=202, body=body, result_reference=row.id)
            return body


def cancel_access_request(*, actor, request_id, expected_version, idempotency_key):
    digest = digest_payload({"request_id": request_id, "expected_version": expected_version, "action": "cancel"})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code="space_access_request.cancel", key=idempotency_key, request_digest=digest, request_uuid=request_id) as (operation, replay):
            if replay:
                return replay_response(operation)
            try:
                row = SpaceAccessRequest.objects.select_for_update(of=("self",)).select_related("space", "access_code").order_by("pk").get(pk=request_id, user=actor)
            except SpaceAccessRequest.DoesNotExist as exc:
                raise NotFound("Access request not found.") from exc
            if (
                row.status == SpaceAccessRequest.STATUS_PENDING
                and row.expires_at <= timezone.now()
            ):
                row.status = SpaceAccessRequest.STATUS_EXPIRED
                row.request_version += 1
                row.save(
                    update_fields=["status", "request_version", "updated_at"]
                )
                if row.access_code_id:
                    SpaceAccessCode.objects.filter(
                        pk=row.access_code_id,
                        pending_count__gt=0,
                    ).update(pending_count=models.F("pending_count") - 1)
                _mark_notifications(
                    resource_type="space_access_request",
                    resource_uuid=row.id,
                    version=row.request_version,
                    actioned=False,
                )
                return _completed_error_response(
                    operation,
                    code="request_expired",
                    status_code=409,
                    result_reference=row.id,
                )
            if row.status == SpaceAccessRequest.STATUS_CANCELLED:
                body = _request_body(row)
                complete_operation_record(
                    operation,
                    status_code=200,
                    body=body,
                    result_reference=row.id,
                )
                return body
            if row.status != SpaceAccessRequest.STATUS_PENDING:
                raise GovernedWorkflowError("request_not_pending")
            if row.request_version != expected_version:
                raise GovernedWorkflowError("stale_request_version", details={"current_version": row.request_version})
            row.status = SpaceAccessRequest.STATUS_CANCELLED
            row.cancelled_at = timezone.now()
            row.request_version += 1
            row.save(update_fields=["status", "cancelled_at", "request_version", "updated_at"])
            if row.access_code_id:
                SpaceAccessCode.objects.filter(pk=row.access_code_id, pending_count__gt=0).update(pending_count=models.F("pending_count") - 1)
            _mark_notifications(resource_type="space_access_request", resource_uuid=row.id, version=row.request_version, actioned=False)
            _audit(actor, space=row.space, event="access_request_cancelled", resource=row)
            _enqueue_join_delivery(
                aggregate_type="space_access_request",
                aggregate_uuid=row.id,
                transition="cancelled",
                transition_version=row.request_version,
                recipient_key=_user_delivery_key(row.space.owner_id),
                space_id=row.space_id,
                deep_link=f"/workspace/{row.space_id}/manage/access",
            )
            body = _request_body(row)
            complete_operation_record(operation, status_code=200, body=body, result_reference=row.id)
            return body


def decide_access_request(*, actor, space, request_id, expected_version, action, role=None, reason_code="", reason_text="", idempotency_key):
    if action not in {"approve", "reject"}:
        raise ValueError("unsupported access-request action")
    if action == "reject" and not reason_code:
        raise ValidationError({"reason_code": "A controlled reason is required."})
    reason_text = normalize_text(reason_text or "", max_length=500, field="reason_text", required=False)
    digest = digest_payload({"space_id": space.id, "request_id": request_id, "expected_version": expected_version, "action": action, "role": role, "reason_code": reason_code, "reason_text": reason_text})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code=f"space_access_request.{action}", key=idempotency_key, request_digest=digest, target_uuid=space.id, request_uuid=request_id) as (operation, replay):
            if replay:
                return replay_response(operation)
            space = _lock_active_owner_space(
                actor=actor,
                space_id=space.id,
                allow_archived=(action == "reject"),
            )
            try:
                reference = SpaceAccessRequest.objects.only("user_id", "access_code_id").get(pk=request_id, space=space)
            except SpaceAccessRequest.DoesNotExist as exc:
                raise NotFound("Access request not found.") from exc
            membership = SpaceMembership.objects.select_for_update(of=("self",)).filter(space=space, user_id=reference.user_id).order_by("pk").first()
            code = None
            if reference.access_code_id:
                code = SpaceAccessCode.objects.select_for_update(of=("self",)).order_by("pk").get(pk=reference.access_code_id)
            # Serialize approval with invitation acceptance. If approval wins,
            # the still-targeted invitation remains consumable and later
            # acceptance converges through the already-member rule.
            list(
                SpaceInvitation.objects.select_for_update(of=("self",))
                .filter(
                    space=space,
                    target_key__in=_verified_target_keys(reference.user_id),
                    status=SpaceInvitation.STATUS_PENDING,
                )
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            row = SpaceAccessRequest.objects.select_for_update(of=("self",)).select_related("user").order_by("pk").get(pk=request_id)
            if (
                row.status == SpaceAccessRequest.STATUS_PENDING
                and row.expires_at <= timezone.now()
            ):
                row.status = SpaceAccessRequest.STATUS_EXPIRED
                row.request_version += 1
                row.save(
                    update_fields=["status", "request_version", "updated_at"]
                )
                if code and code.pending_count:
                    code.pending_count -= 1
                    code.save(update_fields=["pending_count", "updated_at"])
                _mark_notifications(
                    resource_type="space_access_request",
                    resource_uuid=row.id,
                    version=row.request_version,
                    actioned=False,
                )
                return _completed_error_response(
                    operation,
                    code="request_expired",
                    status_code=409,
                    result_reference=row.id,
                )
            matching_terminal_status = (
                SpaceAccessRequest.STATUS_APPROVED
                if action == "approve"
                else SpaceAccessRequest.STATUS_REJECTED
            )
            if row.status == matching_terminal_status and row.reviewed_by_id == actor.id:
                body = _request_body(row)
                complete_operation_record(
                    operation,
                    status_code=200,
                    body=body,
                    result_reference=row.id,
                )
                return body
            if row.status != SpaceAccessRequest.STATUS_PENDING:
                raise GovernedWorkflowError("request_already_resolved", details={"status": row.status})
            if row.request_version != expected_version:
                raise GovernedWorkflowError("stale_request_version", details={"current_version": row.request_version})
            if not row.user.is_active:
                raise GovernedWorkflowError("requester_not_active")
            if action == "approve":
                selected_role = role or row.role_ceiling
                allowed = {SpaceMembership.ROLE_GUEST} if row.role_ceiling == SpaceMembership.ROLE_GUEST else {SpaceMembership.ROLE_GUEST, SpaceMembership.ROLE_MEMBER}
                if selected_role not in allowed:
                    raise ValidationError({"role": "Role exceeds the request ceiling."})
                if membership is None:
                    membership = SpaceMembership.objects.create(
                        space=space,
                        user=row.user,
                        role=selected_role,
                        status="active",
                        source_kind=SpaceMembership.SOURCE_ACCESS_REQUEST,
                        invited_by=actor,
                    )
                elif (
                    membership.role != SpaceMembership.ROLE_OWNER
                    and not membership.is_effective
                ):
                    membership.role = selected_role
                    membership.status = "active"
                    membership.source_kind = SpaceMembership.SOURCE_ACCESS_REQUEST
                    membership.invited_by = actor
                    membership.expires_at = None
                    membership.membership_version += 1
                    membership.save(update_fields=["role", "status", "source_kind", "invited_by", "expires_at", "membership_version", "updated_at"])
                row.status = SpaceAccessRequest.STATUS_APPROVED
                row.resulting_membership_uuid = membership.id
            else:
                row.status = SpaceAccessRequest.STATUS_REJECTED
                row.decision_reason_code = reason_code
                row.decision_reason_text = reason_text
                row.rejection_reason = reason_text
            row.reviewed_by = actor
            row.reviewed_at = timezone.now()
            row.request_version += 1
            row.save(update_fields=["status", "resulting_membership_uuid", "decision_reason_code", "decision_reason_text", "rejection_reason", "reviewed_by", "reviewed_at", "request_version", "updated_at"])
            if code and code.pending_count:
                code.pending_count -= 1
                code.save(update_fields=["pending_count", "updated_at"])
            _mark_notifications(resource_type="space_access_request", resource_uuid=row.id, version=row.request_version, actioned=True)
            _audit(actor, space=space, event=f"access_request_{action}d", resource=row, details={"role": role if action == "approve" else None, "reason_code": reason_code})
            _enqueue_join_delivery(
                aggregate_type="space_access_request",
                aggregate_uuid=row.id,
                transition="approved" if action == "approve" else "rejected",
                transition_version=row.request_version,
                recipient_key=_user_delivery_key(row.user_id),
                space_id=space.id,
                deep_link=f"/spaces/discover?request={row.id}",
            )
            body = _request_body(row)
            complete_operation_record(operation, status_code=200, body=body, result_reference=row.id)
            return body


def _invitation_body(invitation, *, raw=None):
    body = {
        "id": str(invitation.id),
        "space_id": str(invitation.space_id),
        "target_user_id": str(invitation.target_user_uuid) if invitation.target_user_uuid else None,
        "target_kind": "user" if invitation.target_user_uuid else "email",
        "role": invitation.role,
        "token_prefix": invitation.token_prefix,
        "status": invitation.status,
        "version": invitation.version,
        "expires_at": invitation.expires_at.isoformat(),
        "resulting_membership_uuid": str(invitation.resulting_membership_uuid) if invitation.resulting_membership_uuid else None,
    }
    if raw is not None:
        body["token"] = raw
    return body


def create_invitation(*, actor, space, payload, idempotency_key):
    _strict(payload, {"target_user_id", "target_email", "role", "expires_in_days"})
    target_user_id = payload.get("target_user_id")
    target_email = payload.get("target_email")
    if bool(target_user_id) == bool(target_email):
        raise ValidationError({"target": "Exactly one target is required."})
    role = payload.get("role")
    if role not in {SpaceMembership.ROLE_KNOWLEDGE_ADMIN, SpaceMembership.ROLE_REVIEWER, SpaceMembership.ROLE_MEMBER, SpaceMembership.ROLE_GUEST}:
        raise ValidationError({"role": "A non-owner role is required."})
    try:
        days = int(payload.get("expires_in_days", 7))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expires_in_days": "Must be an integer."}) from exc
    if not 1 <= days <= 7:
        raise ValidationError({"expires_in_days": "Must be from 1 to 7."})
    target_user = None
    target_user_uuid = None
    target_email_hmac = ""
    encrypted = ""
    alias_target_key = ""
    if target_user_id:
        try:
            target_user_uuid = uuid.UUID(str(target_user_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValidationError({"target_user_id": "Must be a UUID."}) from exc
        target_user = get_user_model().objects.filter(pk=target_user_uuid, is_active=True).first()
        if target_user is None:
            raise NotFound("Invitation target not found.")
        target_key = f"user:{target_user_uuid}"
    else:
        normalized_email, target_email_hmac = _email_hmac(target_email)
        email_target_key = f"email:{target_email_hmac}"
        target_user = _verified_user_for_email(normalized_email)
        if target_user is not None:
            target_user_uuid = target_user.id
            alias_target_key = email_target_key
            target_email_hmac = ""
            target_key = f"user:{target_user.id}"
        else:
            target_key = email_target_key
            encrypted = _fernet().encrypt(normalized_email.encode("utf-8")).decode("ascii")
    digest = digest_payload({"space_id": space.id, "target_key": target_key, "role": role, "days": days})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code="space_invitation.create", key=idempotency_key, request_digest=digest, target_uuid=space.id) as (operation, replay):
            if replay:
                return replay_response(operation)
            # Relax permission: owner-only by default, but any active member
            # can invite when space.allow_member_invite is True (spec §2.3).
            if space.allow_member_invite:
                space = _lock_active_member_space(actor=actor, space_id=space.id)
            else:
                space = _lock_active_owner_space(actor=actor, space_id=space.id)
            if target_user is not None:
                target_user = (
                    get_user_model()
                    .objects.select_for_update(of=("self",))
                    .order_by("pk")
                    .filter(pk=target_user.id, is_active=True)
                    .first()
                )
                if target_user is None:
                    raise GovernedWorkflowError(
                        "invitation_not_available",
                        status_code=404,
                    )
            pending_aliases = list(
                SpaceInvitation.objects.select_for_update(of=("self",))
                .filter(
                    space=space,
                    target_key__in={target_key, alias_target_key}
                    if alias_target_key
                    else {target_key},
                    status=SpaceInvitation.STATUS_PENDING,
                )
                .order_by("pk")
            )
            for pending_alias in pending_aliases:
                if pending_alias.target_key == target_key:
                    raise GovernedWorkflowError("invitation_already_pending")
                pending_alias.status = SpaceInvitation.STATUS_INVALIDATED
                pending_alias.version += 1
                pending_alias.save(update_fields=["status", "version", "updated_at"])
                _mark_notifications(
                    resource_type="space_invitation",
                    resource_uuid=pending_alias.id,
                    version=pending_alias.version,
                    actioned=False,
                )
            raw, pepper_version, token_hash = _new_secret(domain="invitation-token")
            try:
                invitation = SpaceInvitation.objects.create(
                    space=space,
                    inviter=actor,
                    inviter_uuid=actor.id,
                    target_user=target_user,
                    target_user_uuid=target_user_uuid,
                    target_email_hmac=target_email_hmac,
                    encrypted_delivery_address=encrypted,
                    target_key=target_key,
                    role=role,
                    token_hash=token_hash,
                    token_pepper_version=pepper_version,
                    token_prefix=raw[:8],
                    policy_version=1,
                    ownership_version=space.ownership_version,
                    expires_at=timezone.now() + timedelta(days=days),
                )
            except IntegrityError as exc:
                raise GovernedWorkflowError("invitation_already_pending") from exc
            if target_user is not None:
                _notify_actionable(
                    recipient=target_user,
                    type="space_invitation",
                    title="Workspace invitation",
                    body=f"You were invited to {space.name}.",
                    action_kind="space_invitation",
                    resource_type="space_invitation",
                    resource_uuid=invitation.id,
                    resource_version=invitation.version,
                    allowed_actions=["accept", "decline"],
                    deep_link=f"/spaces/discover?invitation={invitation.id}",
                )
            _audit(actor, space=space, event="invitation_created", resource=invitation, details={"role": role, "target_kind": "user" if target_user else "email"})
            _enqueue_join_delivery(
                aggregate_type="space_invitation",
                aggregate_uuid=invitation.id,
                transition="created",
                transition_version=invitation.version,
                recipient_key=_invitation_delivery_key(invitation),
                space_id=space.id,
                deep_link=f"/spaces/discover?invitation={invitation.id}",
            )
            body = _invitation_body(invitation, raw=raw)
            complete_operation_record(operation, status_code=201, body=body, result_reference=invitation.id)
            return body


def revoke_invitation(*, actor, space, invitation_id, expected_version, reason_code, idempotency_key):
    digest = digest_payload({"space_id": space.id, "invitation_id": invitation_id, "expected_version": expected_version, "reason_code": reason_code})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code="space_invitation.revoke", key=idempotency_key, request_digest=digest, target_uuid=space.id, request_uuid=invitation_id) as (operation, replay):
            if replay:
                return replay_response(operation)
            space = _lock_active_owner_space(
                actor=actor,
                space_id=space.id,
                allow_archived=True,
            )
            invitation = SpaceInvitation.objects.select_for_update(of=("self",)).select_related("space").order_by("pk").filter(pk=invitation_id, space=space).first()
            if invitation is None:
                raise NotFound("Invitation not found.")
            if invitation.version != expected_version:
                raise GovernedWorkflowError("stale_invitation_version", details={"current_version": invitation.version})
            if invitation.status != SpaceInvitation.STATUS_PENDING:
                raise GovernedWorkflowError("invitation_already_resolved", details={"status": invitation.status})
            invitation.status = SpaceInvitation.STATUS_REVOKED
            invitation.version += 1
            invitation.save(update_fields=["status", "version", "updated_at"])
            _mark_notifications(resource_type="space_invitation", resource_uuid=invitation.id, version=invitation.version, actioned=False)
            _audit(actor, space=space, event="invitation_revoked", resource=invitation, details={"reason_code": reason_code})
            _enqueue_join_delivery(
                aggregate_type="space_invitation",
                aggregate_uuid=invitation.id,
                transition="revoked",
                transition_version=invitation.version,
                recipient_key=_invitation_delivery_key(invitation),
                space_id=space.id,
                deep_link=f"/spaces/discover?invitation={invitation.id}",
            )
            body = _invitation_body(invitation)
            complete_operation_record(operation, status_code=200, body=body, result_reference=invitation.id)
            return body


def respond_invitation(
    *,
    actor,
    action,
    idempotency_key,
    raw_token=None,
    invitation_id=None,
    expected_version=None,
):
    if action not in {"accept", "decline"}:
        raise ValidationError({"action": "Must be accept or decline."})
    if bool(raw_token) == bool(invitation_id):
        raise ValidationError({"invitation": "Exactly one token or invitation id is required."})
    digest = digest_payload(
        {
            "actor_id": actor.id,
            "token": digest_payload(raw_token) if raw_token else None,
            "invitation_id": invitation_id,
            "expected_version": expected_version,
            "action": action,
        }
    )
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code=f"space_invitation.{action}", key=idempotency_key, request_digest=digest) as (operation, replay):
            if replay:
                return replay_response(operation)
            reference = (
                _lookup_secret(
                    SpaceInvitation,
                    raw_token,
                    domain="invitation-token",
                    hash_field="token_hash",
                    version_field="token_pepper_version",
                )
                if raw_token
                else SpaceInvitation.objects.filter(pk=invitation_id).first()
            )
            if reference is None:
                raise GovernedWorkflowError("invitation_not_available", status_code=404)
            space = KnowledgeSpace.objects.select_for_update(of=("self",)).order_by("pk").get(pk=reference.space_id)
            membership = SpaceMembership.objects.select_for_update(of=("self",)).filter(space=space, user=actor).order_by("pk").first()
            already_effective_member = bool(
                membership is not None and membership.is_effective
            )
            target_keys = _verified_target_keys(actor)
            invitation_rows = list(
                SpaceInvitation.objects.select_for_update(of=("self",))
                .filter(space=space)
                .filter(
                    models.Q(pk=reference.id)
                    | models.Q(
                        target_key__in=target_keys,
                        status=SpaceInvitation.STATUS_PENDING,
                    )
                )
                .order_by("pk")
            )
            invitation = next(
                (row for row in invitation_rows if row.id == reference.id),
                None,
            )
            if invitation is None:
                raise GovernedWorkflowError(
                    "invitation_not_available",
                    status_code=404,
                )
            pending_access_requests = list(
                SpaceAccessRequest.objects.select_for_update(of=("self",))
                .filter(
                    space=space,
                    user=actor,
                    status=SpaceAccessRequest.STATUS_PENDING,
                )
                .order_by("pk")
            )
            if expected_version is not None and invitation.version != expected_version:
                raise GovernedWorkflowError(
                    "stale_invitation_version",
                    details={"current_version": invitation.version},
                )
            targeted = invitation.target_user_uuid == actor.id
            if not targeted and invitation.target_email_hmac:
                try:
                    normalized_email, candidate_hmac = _email_hmac(
                        actor.email,
                        version=invitation.token_pepper_version,
                    )
                    targeted = _actor_owns_verified_email(
                        actor,
                        normalized_email,
                    ) and hmac.compare_digest(
                        invitation.target_email_hmac,
                        candidate_hmac,
                    )
                except (ValidationError, GovernedWorkflowError):
                    targeted = False
            if not targeted:
                raise GovernedWorkflowError("invitation_not_available", status_code=404)
            if invitation.status != SpaceInvitation.STATUS_PENDING:
                raise GovernedWorkflowError(
                    "invitation_already_resolved",
                    details={"status": invitation.status},
                )
            if not actor.is_active:
                raise GovernedWorkflowError("invitation_not_available", status_code=404)
            if invitation.expires_at <= timezone.now() or space.status != "active":
                invitation.status = (
                    SpaceInvitation.STATUS_EXPIRED
                    if invitation.expires_at <= timezone.now()
                    else SpaceInvitation.STATUS_INVALIDATED
                )
                invitation.version += 1
                invitation.save(update_fields=["status", "version", "updated_at"])
                _mark_notifications(
                    resource_type="space_invitation",
                    resource_uuid=invitation.id,
                    version=invitation.version,
                    actioned=False,
                )
                return _completed_error_response(
                    operation,
                    code="invitation_not_available",
                    status_code=404,
                    result_reference=invitation.id,
                )
            if invitation.ownership_version != space.ownership_version or invitation.inviter_uuid != space.owner_id:
                invitation.status = SpaceInvitation.STATUS_INVALIDATED
                invitation.version += 1
                invitation.save(update_fields=["status", "version", "updated_at"])
                _mark_notifications(resource_type="space_invitation", resource_uuid=invitation.id, version=invitation.version, actioned=False)
                return _completed_error_response(
                    operation,
                    code="invitation_not_available",
                    status_code=404,
                    result_reference=invitation.id,
                )
            now = timezone.now()
            if action == "decline":
                invitation.status = SpaceInvitation.STATUS_DECLINED
            else:
                if membership is None:
                    membership = SpaceMembership.objects.create(
                        space=space,
                        user=actor,
                        role=invitation.role,
                        status="active",
                        source_kind=SpaceMembership.SOURCE_INVITATION,
                        invited_by=invitation.inviter,
                    )
                elif membership.role != SpaceMembership.ROLE_OWNER:
                    if not membership.is_effective:
                        membership.role = invitation.role
                        membership.status = "active"
                        membership.expires_at = None
                        membership.source_kind = SpaceMembership.SOURCE_INVITATION
                        membership.invited_by = invitation.inviter
                        membership.membership_version += 1
                        membership.save(update_fields=["role", "status", "expires_at", "source_kind", "invited_by", "membership_version", "updated_at"])
                    elif ROLE_STRENGTH[invitation.role] > ROLE_STRENGTH[membership.role]:
                        # Acceptance is not a member-role edit. Preserve an
                        # existing effective membership rather than silently
                        # upgrading/downgrading it.
                        pass
                invitation.status = SpaceInvitation.STATUS_ACCEPTED
                invitation.resulting_membership_uuid = membership.id
                SpaceAccessRequest.objects.filter(
                    pk__in=[row.id for row in pending_access_requests]
                ).update(
                    status=SpaceAccessRequest.STATUS_INVALIDATED,
                    request_version=models.F("request_version") + 1,
                    updated_at=now,
                )
                for pending_request in pending_access_requests:
                    _mark_notifications(
                        resource_type="space_access_request",
                        resource_uuid=pending_request.id,
                        version=pending_request.request_version + 1,
                        actioned=False,
                    )
            other_pending_invitation_ids = [
                row.id
                for row in invitation_rows
                if row.id != invitation.id
                and row.status == SpaceInvitation.STATUS_PENDING
            ]
            SpaceInvitation.objects.filter(
                pk__in=other_pending_invitation_ids
            ).update(
                status=SpaceInvitation.STATUS_INVALIDATED,
                version=models.F("version") + 1,
                updated_at=now,
            )
            for pending_invitation in invitation_rows:
                if pending_invitation.id in other_pending_invitation_ids:
                    _mark_notifications(
                        resource_type="space_invitation",
                        resource_uuid=pending_invitation.id,
                        version=pending_invitation.version + 1,
                        actioned=False,
                    )
            invitation.responded_by = actor
            invitation.responded_at = now
            invitation.consumed_at = now
            invitation.version += 1
            invitation.save(update_fields=["status", "resulting_membership_uuid", "responded_by", "responded_at", "consumed_at", "version", "updated_at"])
            _mark_notifications(resource_type="space_invitation", resource_uuid=invitation.id, version=invitation.version, actioned=True)
            _audit(actor, space=space, event=f"invitation_{action}ed", resource=invitation, details={"membership_id": str(invitation.resulting_membership_uuid) if invitation.resulting_membership_uuid else None})
            _enqueue_join_delivery(
                aggregate_type="space_invitation",
                aggregate_uuid=invitation.id,
                transition="accepted" if action == "accept" else "declined",
                transition_version=invitation.version,
                recipient_key=_user_delivery_key(invitation.inviter_uuid),
                space_id=space.id,
                deep_link=f"/workspace/{space.id}/manage/members",
            )
            body = _invitation_body(invitation)
            body["result"] = (
                "already_member"
                if action == "accept" and already_effective_member
                else action + "ed"
            )
            complete_operation_record(operation, status_code=200, body=body, result_reference=invitation.id)
            return body


def redeem_invitation(*, actor, raw_token, action, idempotency_key):
    return respond_invitation(
        actor=actor,
        raw_token=raw_token,
        action=action,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------------
# Simplified join-policy functions (spec §2 — access_code / global modes)
# ---------------------------------------------------------------------------

_JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_join_code():
    """Generate a system join code: ``KP-`` + 6 chars from a safe alphabet."""
    body = "".join(random.choices(_JOIN_CODE_ALPHABET, k=6))
    return f"KP-{body}"


def validate_custom_join_code(code):
    """Validate and normalise a user-supplied join code.

    Rules (spec §2.2.1): 4-20 chars, alphanumeric + hyphens, stored uppercase.
    """
    code = (code or "").strip().upper()
    if not (4 <= len(code) <= 20):
        raise ValidationError({"join_code": "Must be 4-20 characters."})
    if not all(c.isalnum() or c == "-" for c in code):
        raise ValidationError({"join_code": "Only letters, digits, and hyphens are allowed."})
    return code


def _generate_unique_join_code():
    """Generate a ``join_code`` that does not collide with existing values."""
    for _ in range(5):
        candidate = generate_join_code()
        if not KnowledgeSpace.objects.filter(join_code__iexact=candidate).exists():
            return candidate
    raise GovernedWorkflowError("join_code_generation_failed", status_code=500)


def _lock_active_member_space(*, actor, space_id):
    """Lock space and check that *actor* is an active member (any role)."""

    try:
        space = (
            KnowledgeSpace.objects.select_for_update(of=("self",))
            .order_by("pk")
            .get(pk=space_id)
        )
    except KnowledgeSpace.DoesNotExist as exc:
        raise NotFound("Workspace not found.") from exc
    member_mirror = (
        SpaceMembership.objects.select_for_update(of=("self",))
        .filter(
            space=space,
            user=actor,
            status="active",
            expires_at__isnull=True,
        )
        .order_by("pk")
        .first()
    )
    if not actor.is_active or member_mirror is None:
        raise GovernedWorkflowError("workspace_member_required", status_code=403)
    parents_active = (
        space.organization.status == "active"
        and (
            space.business_line_id is None
            or space.business_line.status == "active"
        )
    )
    if space.status != "active" or not parents_active:
        raise GovernedWorkflowError("workspace_not_writable")
    return space


def _lock_manage_space(*, actor, space_id):
    """Lock space and check that *actor* is owner or knowledge_admin."""

    try:
        space = (
            KnowledgeSpace.objects.select_for_update(of=("self",))
            .order_by("pk")
            .get(pk=space_id)
        )
    except KnowledgeSpace.DoesNotExist as exc:
        raise NotFound("Workspace not found.") from exc
    admin_mirror = (
        SpaceMembership.objects.select_for_update(of=("self",))
        .filter(
            space=space,
            user=actor,
            role__in=[
                SpaceMembership.ROLE_OWNER,
                SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
            ],
            status="active",
            expires_at__isnull=True,
        )
        .order_by("pk")
        .first()
    )
    if not actor.is_active or (admin_mirror is None and not actor.is_superuser):
        raise GovernedWorkflowError("workspace_admin_required", status_code=403)
    parents_active = (
        space.organization.status == "active"
        and (
            space.business_line_id is None
            or space.business_line.status == "active"
        )
    )
    if space.status != "active" or not parents_active:
        raise GovernedWorkflowError("workspace_not_writable")
    return space


def join_by_code(*, actor, join_code, idempotency_key):
    """Join a workspace by its join code (simplified access_code mode)."""

    code = (join_code or "").strip().upper()
    digest = digest_payload({"actor_id": actor.id, "join_code": code})
    with durable_governed_transaction():
        with operation_record(
            actor=actor,
            operation_code="space_join.by_code",
            key=idempotency_key,
            request_digest=digest,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            space = (
                KnowledgeSpace.objects.select_for_update(of=("self",))
                .filter(
                    join_code__iexact=code,
                    join_policy=KnowledgeSpace.JOIN_POLICY_ACCESS_CODE,
                )
                .order_by("pk")
                .first()
            )
            if space is None:
                raise NotFound("Join code not found.")
            if space.status != "active":
                raise GovernedWorkflowError("workspace_not_available", status_code=403)
            parents_active = (
                space.organization.status == "active"
                and (
                    space.business_line_id is None
                    or space.business_line.status == "active"
                )
            )
            if not parents_active:
                raise GovernedWorkflowError("workspace_not_available", status_code=403)
            existing = (
                SpaceMembership.objects.select_for_update(of=("self",))
                .filter(space=space, user=actor)
                .order_by("pk")
                .first()
            )
            if existing is not None and existing.is_effective:
                raise GovernedWorkflowError("already_member", status_code=409)
            if existing is None:
                membership = SpaceMembership.objects.create(
                    space=space,
                    user=actor,
                    role=SpaceMembership.ROLE_GUEST,
                    status="active",
                    source_kind=SpaceMembership.SOURCE_JOIN_CODE,
                )
            else:
                existing.role = SpaceMembership.ROLE_GUEST
                existing.status = "active"
                existing.expires_at = None
                existing.source_kind = SpaceMembership.SOURCE_JOIN_CODE
                existing.membership_version += 1
                existing.save(
                    update_fields=[
                        "role",
                        "status",
                        "expires_at",
                        "source_kind",
                        "membership_version",
                        "updated_at",
                    ]
                )
                membership = existing
            _audit(
                actor,
                space=space,
                event="join_by_code",
                resource=membership,
                details={"join_policy": space.join_policy},
            )
            # Bug fix: first joined space becomes the user's default so the
            # frontend no longer treats the new member as spaceless.
            from .services import ensure_default_space

            ensure_default_space(actor, space)
            body = {
                "space_id": str(space.id),
                "space_name": space.name,
                "membership_id": str(membership.id),
                "role": membership.role,
                "source": membership.source_kind,
            }
            complete_operation_record(
                operation,
                status_code=201,
                body=body,
                result_reference=membership.id,
            )
            return body


def global_join(*, actor, space_id, idempotency_key):
    """Join a globally-visible workspace directly (simplified global mode)."""

    digest = digest_payload({"actor_id": actor.id, "space_id": str(space_id)})
    with durable_governed_transaction():
        with operation_record(
            actor=actor,
            operation_code="space_join.global",
            key=idempotency_key,
            request_digest=digest,
            target_uuid=space_id,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            try:
                space = (
                    KnowledgeSpace.objects.select_for_update(of=("self",))
                    .order_by("pk")
                    .get(pk=space_id)
                )
            except KnowledgeSpace.DoesNotExist as exc:
                raise NotFound("Workspace not found.") from exc
            if space.join_policy != KnowledgeSpace.JOIN_POLICY_GLOBAL:
                raise GovernedWorkflowError(
                    "workspace_not_discoverable",
                    status_code=403,
                )
            if space.status != "active":
                raise GovernedWorkflowError("workspace_not_available", status_code=403)
            existing = (
                SpaceMembership.objects.select_for_update(of=("self",))
                .filter(space=space, user=actor)
                .order_by("pk")
                .first()
            )
            if existing is not None and existing.is_effective:
                raise GovernedWorkflowError("already_member", status_code=409)
            if existing is None:
                membership = SpaceMembership.objects.create(
                    space=space,
                    user=actor,
                    role=SpaceMembership.ROLE_GUEST,
                    status="active",
                    source_kind=SpaceMembership.SOURCE_DISCOVERY,
                )
            else:
                existing.role = SpaceMembership.ROLE_GUEST
                existing.status = "active"
                existing.expires_at = None
                existing.source_kind = SpaceMembership.SOURCE_DISCOVERY
                existing.membership_version += 1
                existing.save(
                    update_fields=[
                        "role",
                        "status",
                        "expires_at",
                        "source_kind",
                        "membership_version",
                        "updated_at",
                    ]
                )
                membership = existing
            _audit(
                actor,
                space=space,
                event="global_join",
                resource=membership,
                details={"join_policy": space.join_policy},
            )
            # Bug fix: first joined space becomes the user's default so the
            # frontend no longer treats the new member as spaceless.
            from .services import ensure_default_space

            ensure_default_space(actor, space)
            body = {
                "space_id": str(space.id),
                "space_name": space.name,
                "membership_id": str(membership.id),
                "role": membership.role,
                "source": membership.source_kind,
            }
            complete_operation_record(
                operation,
                status_code=201,
                body=body,
                result_reference=membership.id,
            )
            return body


def regenerate_join_code(*, actor, space_id, custom_code=None, idempotency_key):
    """Regenerate (or set a custom) join code for a workspace."""

    digest = digest_payload(
        {"space_id": str(space_id), "custom_code": custom_code}
    )
    with durable_governed_transaction():
        with operation_record(
            actor=actor,
            operation_code="space_join_code.regenerate",
            key=idempotency_key,
            request_digest=digest,
            target_uuid=space_id,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            space = _lock_manage_space(actor=actor, space_id=space_id)
            if custom_code:
                new_code = validate_custom_join_code(custom_code)
                if (
                    KnowledgeSpace.objects.exclude(pk=space.pk)
                    .filter(join_code__iexact=new_code)
                    .exists()
                ):
                    raise ValidationError(
                        {"join_code": "This code is already in use."}
                    )
            else:
                new_code = _generate_unique_join_code()
            old_code = space.join_code
            space.join_code = new_code
            space.join_code_updated_at = timezone.now()
            space.save(
                update_fields=["join_code", "join_code_updated_at", "updated_at"]
            )
            _audit(
                actor,
                space=space,
                event="join_code_regenerated",
                resource=space,
                details={
                    "old_code_prefix": (old_code or "")[:6] if old_code else None,
                    "new_code_prefix": new_code[:6],
                },
            )
            body = {
                "space_id": str(space.id),
                "join_code": new_code,
                "join_policy": space.join_policy,
                "join_code_updated_at": space.join_code_updated_at.isoformat(),
            }
            complete_operation_record(
                operation,
                status_code=200,
                body=body,
                result_reference=space.id,
            )
            return body


def switch_join_policy(*, actor, space_id, new_policy, idempotency_key):
    """Switch the join policy of a workspace between access_code and global."""

    if new_policy not in (
        KnowledgeSpace.JOIN_POLICY_ACCESS_CODE,
        KnowledgeSpace.JOIN_POLICY_GLOBAL,
    ):
        raise ValidationError({"join_policy": "Invalid join policy."})
    digest = digest_payload({"space_id": str(space_id), "new_policy": new_policy})
    with durable_governed_transaction():
        with operation_record(
            actor=actor,
            operation_code="space_join_policy.switch",
            key=idempotency_key,
            request_digest=digest,
            target_uuid=space_id,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)
            space = _lock_manage_space(actor=actor, space_id=space_id)
            if space.join_policy == new_policy:
                raise GovernedWorkflowError("join_policy_unchanged", status_code=409)
            if (
                new_policy == KnowledgeSpace.JOIN_POLICY_ACCESS_CODE
                and not space.join_code
            ):
                space.join_code = _generate_unique_join_code()
            space.join_policy = new_policy
            space.save(update_fields=["join_policy", "join_code", "updated_at"])
            _audit(
                actor,
                space=space,
                event="join_policy_switched",
                resource=space,
                details={"new_policy": new_policy},
            )
            body = {
                "space_id": str(space.id),
                "join_policy": space.join_policy,
                "join_code": (
                    space.join_code
                    if space.join_policy
                    == KnowledgeSpace.JOIN_POLICY_ACCESS_CODE
                    else None
                ),
            }
            complete_operation_record(
                operation,
                status_code=200,
                body=body,
                result_reference=space.id,
            )
            return body


# Django expressions are used only in locked convergence updates.
from django.db import models  # noqa: E402


__all__ = [
    "issue_access_code",
    "revoke_access_code",
    "redeem_access_code",
    "create_discovery_request",
    "cancel_access_request",
    "decide_access_request",
    "create_invitation",
    "revoke_invitation",
    "respond_invitation",
    "redeem_invitation",
    "generate_join_code",
    "validate_custom_join_code",
    "join_by_code",
    "global_join",
    "regenerate_join_code",
    "switch_join_policy",
]
