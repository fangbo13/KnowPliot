"""Controlled taxonomy and workspace-creation policy API adapters."""

from __future__ import annotations

import uuid

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .governed import (
    GovernedWorkflowError,
    complete_operation_record,
    digest_payload,
    durable_governed_transaction,
    normalize_code,
    normalize_text,
    operation_record,
    replay_response,
    require_idempotency_key,
)
from .models import (
    BusinessLine,
    OfficeLocation,
    Organization,
    WorkGroup,
    WorkspaceCreationPolicy,
)
from .permissions import admin_scope, is_platform_admin


KINDS = {"business-lines", "work-groups", "office-locations"}


def _uuid(value, field):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Must be a UUID."}) from exc


def _strict(data, allowed):
    if not isinstance(data, dict):
        raise ValidationError({"detail": "A JSON object is required."})
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ValidationError({"unknown_fields": unknown})


def _active_policy_lines():
    now = timezone.now()
    return WorkspaceCreationPolicy.objects.filter(
        status=WorkspaceCreationPolicy.STATUS_ACTIVE,
        audience=WorkspaceCreationPolicy.AUDIENCE_REGISTERED_BETA,
        review_route=WorkspaceCreationPolicy.ROUTE_PLATFORM,
    ).filter(
        Q(effective_from__isnull=True) | Q(effective_from__lte=now),
        Q(effective_until__isnull=True) | Q(effective_until__gte=now),
    ).values_list("business_line_id", flat=True)


def _serialize_taxonomy(kind, row):
    if kind == "business-lines":
        return {
            "id": str(row.id),
            "parent_id": str(row.organization_id),
            "normalized_code": row.code,
            "display_name": row.name,
            "description": row.description,
            "active": row.status == "active",
            "version": getattr(row, "version", 1),
        }
    parent_id = row.business_line_id if kind == "work-groups" else row.organization_id
    return {
        "id": str(row.id),
        "parent_id": str(parent_id),
        "normalized_code": row.normalized_code,
        "display_name": row.display_name,
        "description": row.description,
        "active": row.active,
        "sort_order": row.sort_order,
        "version": getattr(row, "version", 1),
    }


def _query_for(kind):
    if kind == "business-lines":
        return BusinessLine.objects.select_related("organization")
    if kind == "work-groups":
        return WorkGroup.objects.select_related("business_line", "business_line__organization")
    if kind == "office-locations":
        return OfficeLocation.objects.select_related("organization")
    raise NotFound("Taxonomy kind not found.")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def taxonomy_select(request, kind):
    if kind not in KINDS:
        raise NotFound("Taxonomy kind not found.")
    context = request.query_params.get("context", "")
    if context not in {"", "creation"}:
        raise ValidationError({"context": "Unsupported context."})
    query = normalize_text(
        request.query_params.get("q", ""),
        max_length=100,
        field="q",
        required=False,
    )
    scope_id = request.query_params.get("scope_id")
    rows = _query_for(kind)
    if kind == "business-lines":
        rows = rows.filter(status="active")
        if context == "creation":
            rows = rows.filter(id__in=_active_policy_lines())
    elif kind == "work-groups":
        rows = rows.filter(active=True, business_line__status="active")
        if scope_id:
            rows = rows.filter(business_line_id=_uuid(scope_id, "scope_id"))
        if context == "creation":
            rows = rows.filter(business_line_id__in=_active_policy_lines())
    else:
        rows = rows.filter(active=True, organization__status="active")
        if scope_id:
            rows = rows.filter(organization_id=_uuid(scope_id, "scope_id"))
        if context == "creation":
            policy_orgs = BusinessLine.objects.filter(
                id__in=_active_policy_lines()
            ).values_list("organization_id", flat=True)
            rows = rows.filter(organization_id__in=policy_orgs)
    if query:
        if kind == "business-lines":
            rows = rows.filter(Q(name__icontains=query) | Q(code__icontains=query))
        else:
            rows = rows.filter(Q(display_name__icontains=query) | Q(normalized_code__icontains=query))
    rows = rows.order_by("name", "id") if kind == "business-lines" else rows.order_by("sort_order", "display_name", "id")
    return Response({"results": [_serialize_taxonomy(kind, row) for row in rows[:100]], "next_cursor": None})


def _scope_mutation_allowed(user, kind, parent):
    if is_platform_admin(user):
        return True
    organization_ids, business_line_ids = admin_scope(user)
    if kind == "business-lines":
        return parent.id in organization_ids
    if kind == "work-groups":
        return parent.organization_id in organization_ids or parent.id in business_line_ids
    return parent.id in organization_ids


def _audit(actor, *, kind, row, event):
    from apps.audit.views import create_audit_log

    return create_audit_log(
        user=actor,
        action="config_change",
        target_type="ControlledTaxonomy",
        target_id=row.id,
        details={"taxonomy_event": event, "kind": kind, "version": getattr(row, "version", 1)},
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def admin_taxonomy_collection(request, kind):
    if kind not in KINDS:
        raise NotFound("Taxonomy kind not found.")
    if request.method == "GET":
        if not (is_platform_admin(request.user) or any(admin_scope(request.user))):
            raise PermissionDenied("Taxonomy management capability required.")
        rows = _query_for(kind).order_by("id")[:100]
        return Response({"results": [_serialize_taxonomy(kind, row) for row in rows], "next_cursor": None})

    _strict(request.data, {"parent_id", "normalized_code", "display_name"})
    parent_id = _uuid(request.data.get("parent_id"), "parent_id")
    code = normalize_code(request.data.get("normalized_code"))
    name = normalize_text(request.data.get("display_name"), max_length=200, field="display_name")
    if kind == "business-lines":
        parent = Organization.objects.filter(pk=parent_id, status="active").first()
    elif kind == "work-groups":
        parent = BusinessLine.objects.select_related("organization").filter(pk=parent_id, status="active").first()
    else:
        parent = Organization.objects.filter(pk=parent_id, status="active").first()
    if parent is None:
        raise NotFound("Parent scope not found.")
    if not _scope_mutation_allowed(request.user, kind, parent):
        raise PermissionDenied("Taxonomy management capability required.")
    key = require_idempotency_key(request)
    digest = digest_payload({"kind": kind, "parent_id": parent_id, "normalized_code": code, "display_name": name})
    with durable_governed_transaction():
        with operation_record(actor=request.user, operation_code=f"taxonomy.{kind}.create", key=key, request_digest=digest, target_uuid=parent_id) as (operation, replay):
            if replay:
                return replay_response(operation)
            if kind == "business-lines":
                row = BusinessLine.objects.create(organization=parent, code=code, name=name, status="active")
            elif kind == "work-groups":
                row = WorkGroup.objects.create(business_line=parent, normalized_code=code, display_name=name, active=True)
            else:
                row = OfficeLocation.objects.create(organization=parent, normalized_code=code, display_name=name, active=True)
            _audit(request.user, kind=kind, row=row, event="created")
            body = _serialize_taxonomy(kind, row)
            complete_operation_record(operation, status_code=201, body=body, result_reference=row.id)
            return Response(body, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def admin_taxonomy_detail(request, kind, item_id):
    if kind not in KINDS:
        raise NotFound("Taxonomy kind not found.")
    _strict(request.data, {"expected_version", "display_name", "active"})
    rows = _query_for(kind)
    try:
        row = rows.get(pk=item_id)
    except rows.model.DoesNotExist as exc:
        raise NotFound("Taxonomy value not found.") from exc
    parent = row.organization if kind in {"business-lines", "office-locations"} else row.business_line
    if not _scope_mutation_allowed(request.user, kind, parent):
        raise PermissionDenied("Taxonomy management capability required.")
    expected = request.data.get("expected_version")
    try:
        expected = int(expected)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_version": "Must be an integer."}) from exc
    key = require_idempotency_key(request)
    digest = digest_payload({"kind": kind, "item_id": item_id, **request.data})
    with durable_governed_transaction():
        with operation_record(actor=request.user, operation_code=f"taxonomy.{kind}.patch", key=key, request_digest=digest, target_uuid=item_id) as (operation, replay):
            if replay:
                return replay_response(operation)
            row = rows.select_for_update(of=("self",)).order_by("pk").get(pk=item_id)
            current = getattr(row, "version", 1)
            if current != expected:
                raise GovernedWorkflowError("stale_resource_version", details={"current_version": current})
            fields = []
            if "display_name" in request.data:
                value = normalize_text(request.data["display_name"], max_length=200, field="display_name")
                if kind == "business-lines":
                    row.name = value
                    fields.append("name")
                else:
                    row.display_name = value
                    fields.append("display_name")
            if "active" in request.data:
                if not isinstance(request.data["active"], bool):
                    raise ValidationError({"active": "Must be a boolean."})
                if kind == "business-lines":
                    row.status = "active" if request.data["active"] else "archived"
                    fields.append("status")
                else:
                    row.active = request.data["active"]
                    fields.append("active")
            if hasattr(row, "version"):
                row.version += 1
                fields.append("version")
            fields.append("updated_at")
            row.save(update_fields=fields)
            _audit(request.user, kind=kind, row=row, event="updated")
            body = _serialize_taxonomy(kind, row)
            complete_operation_record(operation, status_code=200, body=body, result_reference=row.id)
            return Response(body)


def _policy_body(policy):
    return {
        "id": str(policy.id),
        "business_line_id": str(policy.business_line_id),
        "revision": policy.revision,
        "policy_version": policy.revision,
        "status": policy.status,
        "audience": policy.audience,
        "review_route": policy.review_route,
        "effective_from": policy.effective_from.isoformat() if policy.effective_from else None,
        "effective_until": policy.effective_until.isoformat() if policy.effective_until else None,
        "reviewer_separation_required": policy.reviewer_separation_required,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def workspace_creation_policies(request):
    if not is_platform_admin(request.user):
        raise PermissionDenied("Platform creation-policy capability required.")
    if request.method == "GET":
        rows = WorkspaceCreationPolicy.objects.select_related("business_line").order_by("business_line_id", "-revision")
        return Response({"results": [_policy_body(row) for row in rows[:100]], "next_cursor": None})
    _strict(request.data, {"business_line_id", "audience", "review_route", "effective_from", "effective_until", "reviewer_separation_required"})
    business_line_id = _uuid(request.data.get("business_line_id"), "business_line_id")
    line = BusinessLine.objects.filter(pk=business_line_id, status="active").first()
    if line is None:
        raise NotFound("Business line not found.")
    audience = request.data.get("audience")
    route = request.data.get("review_route")
    if audience not in {choice[0] for choice in WorkspaceCreationPolicy.AUDIENCE_CHOICES}:
        raise ValidationError({"audience": "Unsupported audience."})
    if route not in {choice[0] for choice in WorkspaceCreationPolicy.ROUTE_CHOICES}:
        raise ValidationError({"review_route": "Unsupported route."})
    if request.data.get("reviewer_separation_required") is not True:
        raise ValidationError({"reviewer_separation_required": "Must be true for internal beta."})
    key = require_idempotency_key(request)
    digest = digest_payload(request.data)
    with durable_governed_transaction():
        with operation_record(actor=request.user, operation_code="workspace_creation_policy.create", key=key, request_digest=digest, target_uuid=line.id) as (operation, replay):
            if replay:
                return replay_response(operation)
            latest = WorkspaceCreationPolicy.objects.select_for_update(of=("self",)).filter(business_line=line).order_by("-revision").first()
            policy = WorkspaceCreationPolicy.objects.create(
                business_line=line,
                revision=(latest.revision + 1 if latest else 1),
                status=WorkspaceCreationPolicy.STATUS_DRAFT,
                audience=audience,
                review_route=route,
                effective_from=request.data.get("effective_from") or None,
                effective_until=request.data.get("effective_until") or None,
                reviewer_separation_required=True,
                created_by=request.user,
            )
            body = _policy_body(policy)
            complete_operation_record(operation, status_code=201, body=body, result_reference=policy.id)
            return Response(body, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def workspace_creation_policy_transition(request, policy_id, action):
    if not is_platform_admin(request.user):
        raise PermissionDenied("Platform creation-policy capability required.")
    if action not in {"activate", "retire"}:
        raise NotFound("Policy action not found.")
    _strict(request.data, {"expected_policy_version"})
    try:
        expected = int(request.data.get("expected_policy_version"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"expected_policy_version": "Must be an integer."}) from exc
    key = require_idempotency_key(request)
    digest = digest_payload({"policy_id": policy_id, "action": action, "expected": expected})
    with durable_governed_transaction():
        with operation_record(actor=request.user, operation_code=f"workspace_creation_policy.{action}", key=key, request_digest=digest, target_uuid=policy_id) as (operation, replay):
            if replay:
                return replay_response(operation)
            try:
                policy = WorkspaceCreationPolicy.objects.select_for_update(of=("self",)).select_related("business_line").get(pk=policy_id)
            except WorkspaceCreationPolicy.DoesNotExist as exc:
                raise NotFound("Policy not found.") from exc
            if policy.revision != expected:
                raise GovernedWorkflowError("stale_policy_version", details={"current_version": policy.revision})
            if action == "activate":
                if policy.audience != WorkspaceCreationPolicy.AUDIENCE_REGISTERED_BETA or policy.review_route != WorkspaceCreationPolicy.ROUTE_PLATFORM or not policy.reviewer_separation_required:
                    raise GovernedWorkflowError("workspace_creation_policy_not_beta_ready")
                WorkspaceCreationPolicy.objects.filter(
                    business_line=policy.business_line,
                    status=WorkspaceCreationPolicy.STATUS_ACTIVE,
                ).exclude(pk=policy.pk).update(status=WorkspaceCreationPolicy.STATUS_RETIRED, retired_at=timezone.now())
                policy.status = WorkspaceCreationPolicy.STATUS_ACTIVE
                policy.retired_at = None
                policy.save(update_fields=["status", "retired_at"])
            else:
                policy.status = WorkspaceCreationPolicy.STATUS_RETIRED
                policy.retired_at = timezone.now()
                policy.save(update_fields=["status", "retired_at"])
            body = _policy_body(policy)
            complete_operation_record(operation, status_code=200, body=body, result_reference=policy.id)
            return Response(body)


__all__ = [
    "taxonomy_select",
    "admin_taxonomy_collection",
    "admin_taxonomy_detail",
    "workspace_creation_policies",
    "workspace_creation_policy_transition",
]
