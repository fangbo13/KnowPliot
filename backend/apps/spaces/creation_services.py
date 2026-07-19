# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Internal-beta governed workspace creation service.

All mutating entry points are intentionally small wrappers around this module;
the service owns normalization, policy/taxonomy revalidation, locator locking,
idempotency, and the single-transaction approval result.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .governed import (
    GovernedWorkflowError,
    complete_operation_record,
    digest_payload,
    durable_governed_transaction,
    enqueue_transition_outbox,
    ensure_two_reviewer_gate,
    normalize_code,
    normalize_locator,
    normalize_text,
    operation_record,
    record_transition_audit,
    replay_response,
    safe_impact,
)
from .models import (
    GovernedActionRequest,
    KnowledgeSpace,
    WorkspaceCreateRequestDetail,
    WorkspaceCreationPolicy,
    WorkspaceLocatorReservation,
)


CREATE_ALLOWED_FIELDS = {
    "name",
    "code",
    "purpose",
    "visibility",
    "business_line_id",
    "work_group_id",
    "office_location_ids",
    "template_version_id",
}


def _reject_unknown(payload: dict, allowed: set[str] = CREATE_ALLOWED_FIELDS):
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValidationError({"unknown_fields": unknown})


def _uuid(value, field: str, *, required=True):
    if value in (None, ""):
        if required:
            raise ValidationError({field: "This field is required."})
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Must be a UUID."}) from exc


def _taxonomy_models():
    from .models import BusinessLine, OfficeLocation, WorkGroup

    return BusinessLine, WorkGroup, OfficeLocation


def _resolve_template_revision(template_version_id, *, business_line):
    if template_version_id is None:
        return None
    if bool(getattr(settings, "TEMPLATE_ASSET_COPY_ENABLED", False)):
        raise GovernedWorkflowError("template_clone_not_ready", status_code=503)

    from apps.scenario_templates.contract import snapshot_hash
    from apps.scenario_templates.models import ScenarioTemplateRevision

    revision = (
        ScenarioTemplateRevision.objects.select_related("template")
        .filter(
            pk=template_version_id,
            published_at__isnull=False,
            template__is_active=True,
        )
        .first()
    )
    if revision is None:
        raise GovernedWorkflowError("template_revision_unavailable")
    template = revision.template
    if template.business_line_id is not None:
        visible = template.business_line_id == business_line.id
    elif template.organization_id is not None:
        visible = template.organization_id == business_line.organization_id
    else:
        visible = True
    if not visible:
        raise GovernedWorkflowError("template_revision_unavailable")
    if revision.snapshot_hash != snapshot_hash(revision.snapshot):
        raise GovernedWorkflowError("template_revision_not_ready", status_code=503)
    return revision


def _normalize_creation_payload(payload: dict, *, actor):
    _reject_unknown(payload)
    name = normalize_text(payload.get("name"), max_length=200, field="name")
    code = normalize_code(payload.get("code"))
    purpose = normalize_text(payload.get("purpose"), max_length=1000, field="purpose")
    visibility = payload.get("visibility", "private")
    if visibility not in {choice[0] for choice in KnowledgeSpace.VISIBILITY_CHOICES}:
        raise ValidationError({"visibility": "Unsupported visibility."})
    business_line_id = _uuid(payload.get("business_line_id"), "business_line_id")
    work_group_id = _uuid(payload.get("work_group_id"), "work_group_id")
    office_values = payload.get("office_location_ids", [])
    if not isinstance(office_values, list) or not office_values:
        raise ValidationError({"office_location_ids": "At least one office location is required."})
    office_ids = sorted({_uuid(value, "office_location_ids") for value in office_values}, key=str)
    template_version_id = _uuid(payload.get("template_version_id"), "template_version_id", required=False)

    BusinessLine, WorkGroup, OfficeLocation = _taxonomy_models()
    business_line = (
        BusinessLine.objects.select_related("organization")
        .filter(pk=business_line_id, status="active", organization__status="active")
        .first()
    )
    if business_line is None:
        raise ValidationError({"business_line_id": "Business line is not selectable."})
    work_group = (
        WorkGroup.objects.filter(
            pk=work_group_id,
            business_line=business_line,
            active=True,
        )
        .first()
    )
    if work_group is None:
        raise ValidationError({"work_group_id": "Work group is not selectable in this business line."})
    locations = list(
        OfficeLocation.objects.filter(
            pk__in=office_ids,
            organization=business_line.organization,
            active=True,
        )
        .order_by("pk")
    )
    if len(locations) != len(office_ids):
        raise ValidationError({"office_location_ids": "Every location must be active in the derived organization."})

    policy = (
        WorkspaceCreationPolicy.objects.filter(
            business_line=business_line,
            status=WorkspaceCreationPolicy.STATUS_ACTIVE,
            audience=WorkspaceCreationPolicy.AUDIENCE_REGISTERED_BETA,
            review_route=WorkspaceCreationPolicy.ROUTE_PLATFORM,
        )
        .order_by("-revision", "-created_at")
        .first()
    )
    if policy is None or not policy.is_effective:
        raise GovernedWorkflowError("workspace_creation_not_ready", "Workspace creation is not enabled for this business line.", status_code=503)
    template_revision = _resolve_template_revision(
        template_version_id,
        business_line=business_line,
    )

    normalized = {
        "name": name,
        "code": code,
        "purpose": purpose,
        "visibility": visibility,
        "business_line_id": business_line.id,
        "work_group_id": work_group.id,
        "office_location_ids": [location.id for location in locations],
        "template_version_id": template_version_id,
        "template_id": template_revision.template_id if template_revision else None,
        "template_version": template_revision.version if template_revision else None,
        "template_snapshot_hash": (
            template_revision.snapshot_hash if template_revision else None
        ),
        "policy_id": policy.id,
        "policy_revision": policy.revision,
        "organization_id": business_line.organization_id,
        "organization_slug": business_line.organization.slug,
        "actor_id": actor.id,
    }
    normalized["locator"] = normalize_locator(business_line.organization.slug, code)
    return normalized, business_line, work_group, locations, policy, template_revision


def _impact_for(normalized, *, action_type=GovernedActionRequest.ACTION_WORKSPACE_CREATE):
    resources = [
        {"kind": "locator", "organization_id": normalized["organization_id"], "code": normalized["code"]},
        {"kind": "business_line", "id": normalized["business_line_id"], "updated_at": normalized.get("business_line_updated_at")},
        {"kind": "work_group", "id": normalized["work_group_id"]},
        *({"kind": "office_location", "id": location_id} for location_id in normalized["office_location_ids"]),
    ]
    if normalized.get("template_version_id"):
        resources.append(
            {
                "kind": "template_revision",
                "id": normalized["template_version_id"],
                "template_id": normalized["template_id"],
                "version": normalized["template_version"],
                "snapshot_hash": normalized["template_snapshot_hash"],
            }
        )
    return safe_impact(
        action_type=action_type,
        resources=resources,
        policy_version={"id": normalized["policy_id"], "revision": normalized["policy_revision"]},
    )


def _request_body(request: GovernedActionRequest):
    detail = getattr(request, "create_detail", None)
    body = {
        "request_id": str(request.id),
        "status": request.status,
        "request_version": request.request_version,
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
        "status_url": f"/api/v1/spaces/creation-requests/{request.id}/",
    }
    if detail is not None:
        body["submitted"] = {
            "name": detail.normalized_name,
            "code": detail.normalized_code,
            "purpose": detail.purpose,
            "visibility": detail.requested_visibility,
            "business_line_id": str(detail.business_line_id),
            "work_group_id": str(detail.work_group_id),
            "office_location_ids": [str(value) for value in detail.office_location_ids],
            "template_version_id": (
                str(detail.template_version_id) if detail.template_version_id else None
            ),
        }
    if request.result_uuid:
        body["space"] = {
            "id": str(request.result_uuid),
            "provisioning_status": "provisioning",
        }
    if request.failure_code:
        body["failure_code"] = request.failure_code
    return body


def submit_creation_request(*, actor, payload: dict, idempotency_key: uuid.UUID):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise GovernedWorkflowError("account_not_active", status_code=403)
    normalized, business_line, work_group, locations, policy, _template_revision = _normalize_creation_payload(payload, actor=actor)
    request_digest = digest_payload({"actor_id": actor.id, "action": "workspace_create", **normalized})
    with durable_governed_transaction():
        with operation_record(
            actor=actor,
            operation_code="workspace_create.submit",
            key=idempotency_key,
            request_digest=request_digest,
        ) as (operation, replay):
            if replay:
                return replay_response(operation)

            locator = (
                WorkspaceLocatorReservation.objects.select_for_update(of=("self",))
                .filter(organization=business_line.organization, normalized_code=normalized["code"])
                .first()
            )
            if locator is not None and locator.state != WorkspaceLocatorReservation.STATE_RELEASED:
                raise GovernedWorkflowError("space_locator_conflict", "That workspace locator is unavailable.")
            if locator is None:
                # The strict locator shape requires request_reserved to point
                # at an existing request. Insert a target-free released row,
                # then bind and transition it after the envelope exists in the
                # same transaction.
                locator = WorkspaceLocatorReservation.objects.create(
                    organization=business_line.organization,
                    normalized_code=normalized["code"],
                    normalized_locator=normalized["locator"],
                    state=WorkspaceLocatorReservation.STATE_RELEASED,
                )
            else:
                locator.state = WorkspaceLocatorReservation.STATE_RELEASED
                locator.normalized_locator = normalized["locator"]
                locator.live_space = None
                locator.active_request = None
                locator.tombstone = None
                locator.save(
                    update_fields=[
                        "state",
                        "normalized_locator",
                        "live_space",
                        "active_request",
                        "tombstone",
                        "updated_at",
                    ]
                )

            # The requester's normalized locator can only have one live pending
            # request even when clients use different idempotency keys.
            pending = GovernedActionRequest.objects.filter(
                requester_uuid=actor.id,
                action_type=GovernedActionRequest.ACTION_WORKSPACE_CREATE,
                status=GovernedActionRequest.STATUS_PENDING,
                create_detail__normalized_code=normalized["code"],
                organization_id=business_line.organization_id,
            ).exists()
            if pending:
                raise GovernedWorkflowError("request_already_pending")

            impact_version, impact_snapshot = _impact_for(normalized)
            request_row = GovernedActionRequest.objects.create(
                action_type=GovernedActionRequest.ACTION_WORKSPACE_CREATE,
                requester=actor,
                requester_uuid=actor.id,
                scope_type="platform",
                organization=business_line.organization,
                business_line=business_line,
                locator_reservation=locator,
                status=GovernedActionRequest.STATUS_PENDING,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                request_version=1,
                impact_revision=1,
                impact_version=impact_version,
                impact_expires_at=timezone.now() + timedelta(minutes=10),
                impact_snapshot=impact_snapshot,
                expires_at=timezone.now() + timedelta(days=30),
            )
            WorkspaceCreateRequestDetail.objects.create(
                request=request_row,
                normalized_name=normalized["name"],
                normalized_code=normalized["code"],
                purpose=normalized["purpose"],
                requested_visibility=normalized["visibility"],
                business_line=business_line,
                work_group_id=work_group.id,
                office_location_ids=[str(location.id) for location in locations],
                template_version_id=normalized["template_version_id"],
            )
            # The reservation has a one-to-one-ish active request pointer; set
            # it after the request exists through the FK id so no unsaved
            # object is accidentally assigned to the relation.
            locator.state = WorkspaceLocatorReservation.STATE_REQUEST_RESERVED
            locator.active_request_id = request_row.id
            locator.save(update_fields=["state", "active_request", "updated_at"])
            record_transition_audit(actor=actor, request=request_row, event="workspace_create_submitted", old_status=None, new_status=request_row.status)
            enqueue_transition_outbox(
                request=request_row,
                event_type="workspace_create_submitted",
                transition_version=request_row.request_version,
                recipient=actor,
                payload={"request_id": str(request_row.id), "status": request_row.status},
            )
            body = _request_body(request_row)
            complete_operation_record(operation, status_code=202, body=body, result_reference=request_row.id)
            return body


def get_creation_request(*, actor, request_id, reviewer=False):
    try:
        row = GovernedActionRequest.objects.select_related("create_detail", "requester", "organization", "business_line").get(
            pk=request_id, action_type=GovernedActionRequest.ACTION_WORKSPACE_CREATE
        )
    except GovernedActionRequest.DoesNotExist as exc:
        raise NotFound("Request not found.") from exc
    if not reviewer and row.requester_uuid != actor.id:
        raise NotFound("Request not found.")
    return row


def cancel_creation_request(*, actor, request_id, expected_version: int, idempotency_key: uuid.UUID):
    row = get_creation_request(actor=actor, request_id=request_id)
    digest = digest_payload({"request_id": request_id, "expected_request_version": expected_version, "action": "cancel"})
    with durable_governed_transaction():
        with operation_record(actor=actor, operation_code="workspace_create.cancel", key=idempotency_key, request_digest=digest, request_uuid=row.id) as (operation, replay):
            if replay:
                return replay_response(operation)
            row = GovernedActionRequest.objects.select_for_update(of=("self",)).get(pk=row.id)
            if row.status != GovernedActionRequest.STATUS_PENDING:
                raise GovernedWorkflowError("request_not_pending")
            if row.request_version != expected_version:
                raise GovernedWorkflowError("stale_request_version", details={"current_version": row.request_version})
            old = row.status
            row.status = GovernedActionRequest.STATUS_CANCELLED
            row.request_version += 1
            row.completed_at = timezone.now()
            row.save(update_fields=["status", "request_version", "completed_at", "updated_at"])
            if row.locator_reservation_id:
                WorkspaceLocatorReservation.objects.filter(pk=row.locator_reservation_id).update(
                    state=WorkspaceLocatorReservation.STATE_RELEASED,
                    active_request=None,
                    updated_at=timezone.now(),
                )
            record_transition_audit(actor=actor, request=row, event="workspace_create_cancelled", old_status=old, new_status=row.status)
            enqueue_transition_outbox(request=row, event_type="workspace_create_cancelled", transition_version=row.request_version, recipient=actor, payload={"request_id": str(row.id), "status": row.status})
            body = _request_body(row)
            complete_operation_record(operation, status_code=200, body=body, result_reference=row.id)
            return body


def reject_creation_request(*, reviewer, request_id, expected_version: int, reason_code: str, reason_text: str, idempotency_key: uuid.UUID):
    if not reason_code or len(reason_code) > 64:
        raise ValidationError({"reason_code": "A controlled reason code is required."})
    reason_text = normalize_text(reason_text or "", max_length=500, field="reason_text", required=False)
    row = get_creation_request(actor=reviewer, request_id=request_id, reviewer=True)
    digest = digest_payload({"request_id": request_id, "expected_request_version": expected_version, "reason_code": reason_code, "reason_text": reason_text, "action": "reject"})
    with durable_governed_transaction():
        with operation_record(actor=reviewer, operation_code="workspace_create.reject", key=idempotency_key, request_digest=digest, request_uuid=row.id) as (operation, replay):
            if replay:
                return replay_response(operation)
            row = GovernedActionRequest.objects.select_for_update(of=("self",)).get(pk=row.id)
            if row.status != GovernedActionRequest.STATUS_PENDING:
                raise GovernedWorkflowError("request_already_resolved")
            if row.requester_uuid == reviewer.id:
                raise GovernedWorkflowError("self_approval_forbidden")
            if row.request_version != expected_version:
                raise GovernedWorkflowError("stale_request_version", details={"current_version": row.request_version})
            old = row.status
            row.status = GovernedActionRequest.STATUS_REJECTED
            row.reason_code = reason_code
            row.reason_text = reason_text
            row.reviewer = reviewer
            row.reviewer_uuid = reviewer.id
            row.reviewed_at = timezone.now()
            row.completed_at = row.reviewed_at
            row.request_version += 1
            row.save(update_fields=["status", "reason_code", "reason_text", "reviewer", "reviewer_uuid", "reviewed_at", "completed_at", "request_version", "updated_at"])
            WorkspaceLocatorReservation.objects.filter(pk=row.locator_reservation_id).update(state=WorkspaceLocatorReservation.STATE_RELEASED, active_request=None, updated_at=timezone.now())
            record_transition_audit(actor=reviewer, request=row, event="workspace_create_rejected", old_status=old, new_status=row.status, details={"reason_code": reason_code})
            enqueue_transition_outbox(request=row, event_type="workspace_create_rejected", transition_version=row.request_version, recipient=row.requester, payload={"request_id": str(row.id), "status": row.status, "reason_code": reason_code})
            body = _request_body(row)
            complete_operation_record(operation, status_code=200, body=body, result_reference=row.id)
            return body


def approve_creation_request(*, reviewer, request_id, expected_version: int, impact_version: str, acknowledge_requester_becomes_owner: bool, idempotency_key: uuid.UUID):
    row = get_creation_request(actor=reviewer, request_id=request_id, reviewer=True)
    digest = digest_payload({"request_id": request_id, "expected_request_version": expected_version, "impact_version": impact_version, "acknowledge_requester_becomes_owner": acknowledge_requester_becomes_owner, "action": "approve"})
    with durable_governed_transaction():
        with operation_record(actor=reviewer, operation_code="workspace_create.approve", key=idempotency_key, request_digest=digest, request_uuid=row.id) as (operation, replay):
            if replay:
                return replay_response(operation)
            row = GovernedActionRequest.objects.select_for_update(of=("self",)).select_related("create_detail", "organization", "business_line", "requester").get(pk=row.id)
            if row.status != GovernedActionRequest.STATUS_PENDING:
                raise GovernedWorkflowError("request_already_resolved")
            if row.requester_uuid == reviewer.id:
                raise GovernedWorkflowError("self_approval_forbidden")
            if not acknowledge_requester_becomes_owner:
                raise ValidationError({"acknowledge_requester_becomes_owner": "Must be true."})
            if row.request_version != expected_version:
                raise GovernedWorkflowError("stale_request_version", details={"current_version": row.request_version})
            if not impact_version or impact_version != row.impact_version or not row.impact_expires_at or row.impact_expires_at <= timezone.now():
                raise GovernedWorkflowError("impact_changed", details={"current_version": row.request_version, "impact_version": row.impact_version, "impact_expires_at": row.impact_expires_at.isoformat() if row.impact_expires_at else None})
            ensure_two_reviewer_gate(requester_id=row.requester_uuid)
            detail = row.create_detail
            # Revalidate all pinned taxonomy rows under the transaction before
            # creating any space.  No client-selected owner/scope is accepted.
            normalized, business_line, work_group, locations, policy, template_revision = _normalize_creation_payload(
                {
                    "name": detail.normalized_name,
                    "code": detail.normalized_code,
                    "purpose": detail.purpose,
                    "visibility": detail.requested_visibility,
                    "business_line_id": str(detail.business_line_id),
                    "work_group_id": str(detail.work_group_id),
                    "office_location_ids": detail.office_location_ids,
                    "template_version_id": (
                        str(detail.template_version_id)
                        if detail.template_version_id
                        else None
                    ),
                },
                actor=row.requester,
            )
            if str(policy.id) != str(row.impact_snapshot.get("policy_version", {}).get("id")):
                raise GovernedWorkflowError("impact_changed")
            locator = WorkspaceLocatorReservation.objects.select_for_update(of=("self",)).get(pk=row.locator_reservation_id)
            if locator.state != WorkspaceLocatorReservation.STATE_REQUEST_RESERVED:
                raise GovernedWorkflowError("space_locator_conflict")
            from .ownership import create_space_with_owner

            try:
                space = create_space_with_owner(
                    organization=row.organization,
                    owner=row.requester,
                    business_line=business_line,
                    work_group=work_group,
                    classification_state=KnowledgeSpace.CLASSIFICATION_COMPLETE,
                    provisioning_status="provisioning",
                    name=detail.normalized_name,
                    code=detail.normalized_code,
                    description=detail.purpose,
                    visibility=detail.requested_visibility,
                )
                space.office_locations.set(locations)
            except IntegrityError as exc:
                raise GovernedWorkflowError("space_locator_conflict") from exc

            old = row.status
            row.target_space = space
            row.target_space_uuid = space.id
            row.result_uuid = space.id
            row.status = GovernedActionRequest.STATUS_COMPLETED
            row.reviewer = reviewer
            row.reviewer_uuid = reviewer.id
            row.reviewed_at = timezone.now()
            row.completed_at = row.reviewed_at
            row.request_version += 1
            row.save(update_fields=["target_space", "target_space_uuid", "result_uuid", "status", "reviewer", "reviewer_uuid", "reviewed_at", "completed_at", "request_version", "updated_at"])
            detail.created_space_uuid = space.id
            detail.save(update_fields=["created_space_uuid"])
            locator.state = WorkspaceLocatorReservation.STATE_LIVE
            locator.live_space = space
            locator.active_request = None
            locator.save(update_fields=["state", "live_space", "active_request", "updated_at"])
            if template_revision is not None:
                from apps.scenario_templates.models import ScenarioTemplateApplication

                ScenarioTemplateApplication.objects.create(
                    template=template_revision.template,
                    template_revision=template_revision,
                    space=space,
                    organization=row.organization,
                    business_line=business_line,
                    created_by=row.requester,
                    provisioning_status="completed",
                    asset_total=0,
                    task_ids=[],
                    template_snapshot={
                        "schema_version": 1,
                        "template_id": str(template_revision.template_id),
                        "template_key": template_revision.template.code,
                        "revision_id": str(template_revision.id),
                        "revision_version": template_revision.version,
                        "revision_hash": template_revision.snapshot_hash,
                    },
                )
            record_transition_audit(actor=reviewer, request=row, event="workspace_create_approved", old_status=old, new_status=row.status, details={"space_id": str(space.id)})
            enqueue_transition_outbox(request=row, event_type="workspace_create_approved", transition_version=row.request_version, recipient=row.requester, payload={"request_id": str(row.id), "status": row.status, "space_id": str(space.id)})
            body = _request_body(row)
            body["status"] = "completed"
            body["space"] = {"id": str(space.id), "provisioning_status": "provisioning"}
            complete_operation_record(operation, status_code=201, body=body, result_reference=space.id)
            return body


__all__ = [
    "submit_creation_request",
    "get_creation_request",
    "cancel_creation_request",
    "reject_creation_request",
    "approve_creation_request",
]
