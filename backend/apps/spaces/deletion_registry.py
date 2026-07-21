"""Fail-closed workspace purge dependency registry and safe manifest builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db.models import ForeignKey, OneToOneField, Q, UUIDField
from django.utils import timezone

from .governed import canonical_payload, digest_payload


SPACE_LABEL = "spaces.knowledgespace"
REQUEST_LABEL = "spaces.governedactionrequest"
PURGE_JOB_LABEL = "spaces.workspacepurgejob"


@dataclass(frozen=True)
class RegistryBinding:
    """Validated way to resolve one registry row to a workspace."""

    model: Any
    lookup: str
    kind: str
    direct_space_field: str | None = None


@dataclass(frozen=True)
class PurgeRegistryAudit:
    ready: bool
    code: str
    expected_count: int
    registered_count: int
    missing: tuple[str, ...] = ()
    invalid: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()

    def public_payload(self) -> dict[str, Any]:
        """Return bounded readiness facts without model or tenant details."""

        return {
            "status": "ok" if self.ready else "not_ready",
            "code": self.code,
            "expected_count": self.expected_count,
            "registered_count": self.registered_count,
        }


def _space_relations() -> dict[str, Any]:
    """Discover every concrete installed FK that can retain a live space."""

    relations: dict[str, Any] = {}
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if not isinstance(field, (ForeignKey, OneToOneField)):
                continue
            remote = getattr(field.remote_field, "model", None)
            if remote is None or remote._meta.label_lower != SPACE_LABEL:
                continue
            key = f"{model._meta.label_lower}.{field.name}"
            relations[key] = (model, field)
    return relations


def _field_for_segment(model, segment: str):
    """Resolve either a Django field name or its concrete ``attname``."""

    try:
        return model._meta.get_field(segment)
    except FieldDoesNotExist:
        for field in model._meta.concrete_fields:
            if getattr(field, "attname", None) == segment:
                return field
    raise FieldDoesNotExist(f"{model._meta.label_lower}.{segment}")


def _registry_binding(row) -> RegistryBinding:
    """Validate a migration-owned registry lookup without executing it.

    Most rows end at a live ``KnowledgeSpace`` FK. Retained evidence also uses
    immutable UUID snapshots, and purge checkpoints are reached through their
    request/job lineage. These are distinct contracts and must not be guessed
    by comparing model names at runtime.
    """

    try:
        model = apps.get_model(row.model_label)
    except (LookupError, ValueError) as exc:
        raise FieldDoesNotExist(row.model_label) from exc
    if model is None or not row.space_field:
        raise FieldDoesNotExist(row.space_field or "<empty>")

    current_model = model
    parts = row.space_field.split("__")
    final_field = None
    for index, part in enumerate(parts):
        final_field = _field_for_segment(current_model, part)
        if index < len(parts) - 1:
            remote = getattr(final_field.remote_field, "model", None)
            if remote is None:
                raise FieldDoesNotExist(row.space_field)
            current_model = remote

    remote = getattr(getattr(final_field, "remote_field", None), "model", None)
    remote_label = remote._meta.label_lower if remote is not None else ""
    if remote_label == SPACE_LABEL:
        direct = final_field.name if len(parts) == 1 else None
        return RegistryBinding(model, row.space_field, "space_relation", direct)
    if isinstance(final_field, UUIDField) and final_field.name in {
        "space_id",
        "space_uuid",
        "original_space_uuid",
        "resource_uuid",
        "target_space_uuid",
    }:
        return RegistryBinding(model, row.space_field, "space_uuid")
    if remote_label == REQUEST_LABEL:
        return RegistryBinding(model, row.space_field, "request_lineage")
    if remote_label == PURGE_JOB_LABEL:
        return RegistryBinding(model, row.space_field, "job_lineage")
    raise FieldDoesNotExist(row.space_field)


def _validate_metadata_fields(row, binding: RegistryBinding) -> list[str]:
    invalid: list[str] = []
    for field_name in tuple(row.snapshot_fields or ()) + tuple(row.scrub_fields or ()):
        if not isinstance(field_name, str) or not field_name:
            invalid.append(f"{binding.model._meta.label_lower}.{field_name!s}")
            continue
        try:
            _field_for_segment(binding.model, field_name)
        except FieldDoesNotExist:
            invalid.append(f"{binding.model._meta.label_lower}.{field_name}")
    return invalid


def registered_queryset(row, *, space):
    """Resolve a validated registry row to exactly one workspace queryset."""

    binding = _registry_binding(row)
    if binding.kind == "space_relation":
        lookup = {binding.lookup: space}
    elif binding.kind == "space_uuid":
        lookup = {binding.lookup: space.pk}
        if binding.model._meta.label_lower == "notifications.notification":
            # Workspace notifications are safe evidence, never authority. Other
            # resource UUIDs are terminalized by the purge service from the
            # exact registered resource set rather than by a broad UUID match.
            lookup["resource_type"] = "workspace"
    elif binding.kind == "request_lineage":
        lookup = {f"{binding.lookup}__target_space_uuid": space.pk}
    elif binding.kind == "job_lineage":
        lookup = {f"{binding.lookup}__request__target_space_uuid": space.pk}
    else:  # pragma: no cover - bindings are closed above
        raise FieldDoesNotExist(row.space_field)
    return binding.model._default_manager.filter(**lookup)


def audit_purge_registry() -> PurgeRegistryAudit:
    """Verify registrations against the live Django model graph.

    A new space-bearing model or a registration left in ``pending`` state makes
    deletion readiness fail closed.  The registry rows are migration-owned;
    runtime code never auto-registers or guesses a disposition.
    """

    from .models import WorkspacePurgeDependency

    expected = _space_relations()
    rows = list(
        WorkspacePurgeDependency.objects.filter(active=True, required=True).order_by(
            "lock_order", "purge_order", "model_label", "space_field"
        )
    )
    registered = {f"{row.model_label.lower()}.{row.space_field}": row for row in rows}
    covered_direct: set[str] = set()
    pending = tuple(
        sorted(
            key
            for key, row in registered.items()
            if row.registration_state != WorkspacePurgeDependency.STATE_READY
        )
    )
    invalid: list[str] = []
    for key, row in registered.items():
        try:
            binding = _registry_binding(row)
        except (FieldDoesNotExist, LookupError, ValueError):
            invalid.append(key)
            continue
        if binding.direct_space_field:
            covered_direct.add(
                f"{binding.model._meta.label_lower}.{binding.direct_space_field}"
            )
        invalid.extend(_validate_metadata_fields(row, binding))
        if row.lock_order <= 0 or row.purge_order <= 0 or row.schema_revision <= 0:
            invalid.append(key)
    missing = tuple(sorted(set(expected) - covered_direct))
    invalid_tuple = tuple(sorted(set(invalid)))
    ready = not missing and not pending and not invalid_tuple
    if missing:
        code = "purge_registry_missing_dependency"
    elif pending:
        code = "purge_registry_pending_migration"
    elif invalid_tuple:
        code = "purge_registry_invalid"
    else:
        code = "purge_registry_ready"
    return PurgeRegistryAudit(
        ready=ready,
        code=code,
        expected_count=len(expected),
        registered_count=len(registered),
        missing=missing,
        invalid=invalid_tuple,
        pending=pending,
    )


def _safe_row_snapshot(queryset, *, model, limit: int | None = None) -> list[dict[str, Any]]:
    """Build manifest evidence from identifiers and controlled state only."""

    allowed = ["pk"]
    field_names = {field.name for field in model._meta.concrete_fields}
    for name in (
        "status",
        "state",
        "version",
        "request_version",
        "updated_at",
        "completed_at",
        "expires_at",
    ):
        if name in field_names:
            allowed.append(name)
    rows = queryset.order_by("pk").values(*allowed)
    if limit is not None:
        rows = rows[:limit]
    return [canonical_payload(row) for row in rows]


_TERMINAL_TASK_STATE_FIELDS = {
    "knowledge.ingestionjob": ("status", {"succeeded", "failed"}),
    "knowledge.batchimportresultrecord": ("status", {"completed", "failed"}),
    "chat.feedback": ("status", {"resolved", "dismissed", "withdrawn"}),
    "chat.knowledgegapticket": ("status", {"resolved", "wont_fix"}),
    "chat.complianceexportjob": ("status", {"succeeded", "failed", "expired"}),
    # Purge jobs deliberately call their state column ``state`` while per-store
    # checkpoints use ``status``. Keep this mapping explicit: guessing a common
    # field turned deletion-impact reads into a 500 and would keep ACKed
    # checkpoints as blockers forever.
    "spaces.workspacepurgejob": ("state", {"completed"}),
    "spaces.workspacepurgecheckpoint": ("status", {"acked"}),
}


def _blocker_queryset(row, queryset, *, now=None):
    """Return only active blocker rows for the registry entry.

    Blocker predicates are deliberately closed and stable. An unknown blocker
    code fails closed by treating every matching row as active.
    """

    now = now or timezone.now()
    code = row.blocker_code
    label = row.model_label.lower()
    if not code:
        return queryset.none()
    if code == "active_shares":
        return queryset.filter(revoked_at__isnull=True, expires_at__gt=now)
    if code == "child_categories":
        return queryset.filter(parent__isnull=False)
    if code == "ownership_transition_pending":
        return queryset.filter(status="pending")
    if code == "retention_hold":
        return queryset.filter(status="active").filter(
            Q(release_not_before__isnull=True) | Q(release_not_before__gt=now)
        )
    if code == "active_chat_execution":
        terminal = ("completed", "failed", "cancelled")
        safety_cutoff = now - timedelta(minutes=15)
        return queryset.filter(
            ~Q(status__in=terminal) | Q(updated_at__gte=safety_cutoff)
        )
    if code == "open_tasks":
        terminal_contract = _TERMINAL_TASK_STATE_FIELDS.get(label)
        if terminal_contract is None:
            return queryset
        state_field, terminal = terminal_contract
        return queryset.exclude(**{f"{state_field}__in": terminal})
    return queryset


def _retention_dates(*, space, rows) -> list[str]:
    values = []
    if getattr(space, "retention_until", None):
        values.append(space.retention_until)
    for row, queryset in rows:
        if row.blocker_code != "retention_hold":
            continue
        values.extend(
            queryset.filter(release_not_before__isnull=False).values_list(
                "release_not_before", flat=True
            )
        )
    return sorted({value.isoformat() for value in values if value is not None})


def build_deletion_manifest(*, space) -> dict[str, Any]:
    """Return a deterministic, content-free manifest and blocker summary."""

    from .models import WorkspacePurgeDependency

    audit = audit_purge_registry()
    if not audit.ready:
        payload = {
            "ready": False,
            "version": 0,
            "resources": [],
            "counts": {"eligible_content": 0, "retained_evidence": 0},
            "blockers": [
                {
                    "kind": "storage_manifest_unavailable",
                    "id": "purge-registry",
                    "status": "not_ready",
                    "remediation_route": "/platform-admin/readiness",
                }
            ],
            "retention_dates": [],
        }
        payload["manifest_digest"] = digest_payload(payload)
        return payload

    resources: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    counts = {"eligible_content": 0, "retained_evidence": 0}
    entries = WorkspacePurgeDependency.objects.filter(
        active=True,
        required=True,
        registration_state=WorkspacePurgeDependency.STATE_READY,
    ).order_by("purge_order", "model_label", "space_field")
    resolved_rows = []
    for entry in entries:
        model = apps.get_model(entry.model_label)
        try:
            queryset = registered_queryset(entry, space=space)
        except (FieldDoesNotExist, LookupError, TypeError, ValueError):
            payload = {
                "ready": False,
                "version": 0,
                "resources": [],
                "counts": counts,
                "blockers": [
                    {
                        "kind": "storage_manifest_unavailable",
                        "id": "purge-registry",
                        "status": "not_ready",
                        "remediation_route": "/platform-admin/readiness",
                    }
                ],
                "retention_dates": [],
            }
            payload["manifest_digest"] = digest_payload(payload)
            return payload
        resolved_rows.append((entry, queryset))
        count = queryset.count()
        snapshots = _safe_row_snapshot(queryset, model=model)
        resource = {
            "model": entry.model_label.lower(),
            "space_field": entry.space_field,
            "disposition": entry.disposition,
            "schema_revision": entry.schema_revision,
            "count": count,
            "rows_digest": digest_payload(snapshots),
        }
        resources.append(resource)
        if entry.disposition == WorkspacePurgeDependency.DISPOSITION_ELIGIBLE:
            counts["eligible_content"] += count
        elif entry.disposition == WorkspacePurgeDependency.DISPOSITION_RETAINED:
            counts["retained_evidence"] += count
        active_blockers = _blocker_queryset(entry, queryset)
        if active_blockers.exists():
            blockers.append(
                {
                    "kind": entry.blocker_code or "storage_manifest_unavailable",
                    "id": digest_payload(
                        {"space": space.pk, "model": entry.model_label, "field": entry.space_field}
                    )[:32],
                    "status": "active",
                    "remediation_route": "",
                }
            )

    registry_fingerprint = digest_payload(
        [
            [entry.model_label.lower(), entry.space_field, entry.schema_revision]
            for entry in entries
        ]
    )
    manifest_core = {
        "ready": True,
        "version": max((entry.schema_revision for entry in entries), default=1),
        "registry_digest": registry_fingerprint,
        "resources": resources,
        "counts": counts,
        "blockers": sorted(blockers, key=lambda item: (item["kind"], item["id"])),
        "retention_dates": _retention_dates(space=space, rows=resolved_rows),
    }
    # Append-only retained evidence (including this deletion request's own
    # audits/outbox lineage) may legitimately grow after impact is issued. It
    # must be detached at purge, but must not invalidate the frozen eligible-
    # content/storage inventory merely because an audit row was appended.
    manifest_core["manifest_digest"] = digest_payload(
        {
            "version": manifest_core["version"],
            "registry_digest": registry_fingerprint,
            "resources": [
                resource
                for resource in resources
                if resource["disposition"]
                != WorkspacePurgeDependency.DISPOSITION_RETAINED
            ],
            "blockers": manifest_core["blockers"],
            "retention_dates": manifest_core["retention_dates"],
        }
    )
    return manifest_core


__all__ = [
    "PurgeRegistryAudit",
    "audit_purge_registry",
    "build_deletion_manifest",
    "registered_queryset",
]
