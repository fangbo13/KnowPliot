# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Audit and explicitly map legacy HR authority into tenant scopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)
from apps.spaces.permissions import active_space_lifecycle_q

User = get_user_model()
MAPPING_VERSION = 1
MIGRATION_AUDIT_TAG = "legacy_admin_scope_v1"


@dataclass(frozen=True)
class ScopeMapping:
    user_id: UUID
    scope_type: str
    scope_id: UUID
    role: str


def _parse_uuid(value, *, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise CommandError(f"Invalid {field}; expected UUID.") from exc


def _load_mapping_file(path_value: str | None) -> list[ScopeMapping]:
    if not path_value:
        return []
    path = Path(path_value)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError("Unable to read a valid JSON mapping file.") from exc
    if not isinstance(payload, dict) or payload.get("version") != MAPPING_VERSION:
        raise CommandError(f"Mapping file version must be {MAPPING_VERSION}.")
    rows = payload.get("mappings")
    if not isinstance(rows, list):
        raise CommandError("Mapping file must contain a mappings list.")

    allowed_roles = {
        "organization": {OrganizationMembership.ROLE_ORG_ADMIN},
        "business_line": {OrganizationMembership.ROLE_BUSINESS_ADMIN},
        "space": {choice[0] for choice in SpaceMembership.ROLE_CHOICES},
    }
    mappings: list[ScopeMapping] = []
    seen: set[tuple[UUID, str, UUID, str]] = set()
    scoped_roles: dict[tuple[UUID, str, UUID], str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise CommandError("Each mapping must be an object.")
        scope_type = row.get("scope_type")
        role = row.get("role")
        if scope_type not in allowed_roles or role not in allowed_roles[scope_type]:
            raise CommandError("Mapping contains an unsupported scope and role combination.")
        mapping = ScopeMapping(
            user_id=_parse_uuid(row.get("user_id"), field="user_id"),
            scope_type=scope_type,
            scope_id=_parse_uuid(row.get("scope_id"), field="scope_id"),
            role=role,
        )
        scope_identity = (mapping.user_id, mapping.scope_type, mapping.scope_id)
        previous_role = scoped_roles.get(scope_identity)
        if previous_role is not None and previous_role != mapping.role:
            raise CommandError("Mapping assigns conflicting roles to the same user scope.")
        scoped_roles[scope_identity] = mapping.role
        identity = (mapping.user_id, mapping.scope_type, mapping.scope_id, mapping.role)
        if identity not in seen:
            mappings.append(mapping)
            seen.add(identity)
    return sorted(
        mappings,
        key=lambda item: (
            str(item.user_id),
            item.scope_type,
            str(item.scope_id),
            item.role,
        ),
    )


def _legacy_candidates():
    return (
        User.objects.filter(is_active=True, is_superuser=False)
        .filter(
            Q(is_hr_admin=True)
            | Q(
                user_roles__is_active=True,
                user_roles__role__name="hr",
                user_roles__role__is_active=True,
            )
        )
        .distinct()
        .order_by("id")
    )


def _resolve_scope(mapping: ScopeMapping):
    if mapping.scope_type == "organization":
        try:
            return Organization.objects.get(pk=mapping.scope_id, status="active")
        except Organization.DoesNotExist as exc:
            raise CommandError("Mapped organization is unavailable.") from exc
    if mapping.scope_type == "business_line":
        try:
            return BusinessLine.objects.select_related("organization").get(
                pk=mapping.scope_id,
                status="active",
                organization__status="active",
            )
        except BusinessLine.DoesNotExist as exc:
            raise CommandError("Mapped business line is unavailable.") from exc
    try:
        return KnowledgeSpace.objects.select_related("organization", "business_line").get(
            Q(business_line__isnull=True) | Q(business_line__status="active"),
            pk=mapping.scope_id,
            status="active",
            organization__status="active",
        )
    except KnowledgeSpace.DoesNotExist as exc:
        raise CommandError("Mapped space is unavailable.") from exc


def _mapping_memberships(user, mapping: ScopeMapping, scope, *, lock: bool):
    if mapping.scope_type == "space":
        manager = (
            SpaceMembership.objects.select_for_update()
            if lock
            else SpaceMembership.objects
        )
        return list(manager.filter(user=user, space=scope)[:2])

    manager = (
        OrganizationMembership.objects.select_for_update()
        if lock
        else OrganizationMembership.objects
    )
    organization = scope if mapping.scope_type == "organization" else scope.organization
    business_line = None if mapping.scope_type == "organization" else scope
    return list(
        manager.filter(
            user=user,
            organization=organization,
            business_line=business_line,
        )[:2]
    )


def _plan_mapping(user, mapping: ScopeMapping, scope, *, lock: bool) -> str:
    memberships = _mapping_memberships(user, mapping, scope, lock=lock)
    if not memberships:
        return "create"
    if len(memberships) != 1:
        raise CommandError("Existing scoped memberships conflict with the mapping.")
    membership = memberships[0]
    if mapping.scope_type == "space":
        exact = (
            membership.role == mapping.role
            and membership.status == "active"
            and membership.expires_at is None
        )
    else:
        exact = (
            membership.role == mapping.role
            and membership.is_active
            and membership.expires_at is None
        )
    if not exact:
        raise CommandError("Existing scoped membership conflicts with the mapping.")
    return "unchanged"


def _create_mapping(user, mapping: ScopeMapping, scope):
    if mapping.scope_type == "space":
        return SpaceMembership.objects.create(
            user=user,
            space=scope,
            role=mapping.role,
            status="active",
        )
    organization = scope if mapping.scope_type == "organization" else scope.organization
    business_line = None if mapping.scope_type == "organization" else scope
    return OrganizationMembership.objects.create(
        user=user,
        organization=organization,
        business_line=business_line,
        role=mapping.role,
    )


def _effectively_scoped_user_ids(candidate_ids: set[UUID]) -> set[UUID]:
    if not candidate_ids:
        return set()
    now = timezone.now()
    space_user_ids = SpaceMembership.objects.filter(
        active_space_lifecycle_q(prefix="space__"),
        user_id__in=candidate_ids,
        status="active",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now)).values_list(
        "user_id", flat=True
    )
    governance_user_ids = (
        OrganizationMembership.objects.filter(
            user_id__in=candidate_ids,
            is_active=True,
            organization__status="active",
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
        .filter(
            Q(role=OrganizationMembership.ROLE_ORG_ADMIN)
            | Q(
                role=OrganizationMembership.ROLE_BUSINESS_ADMIN,
                business_line__isnull=False,
                business_line__status="active",
                business_line__organization_id=F("organization_id"),
            )
        )
        .values_list("user_id", flat=True)
    )
    return set(space_user_ids) | set(governance_user_ids)


def _write_audit(user, mapping: ScopeMapping, membership, scope) -> None:
    organization_id = (
        scope.id if mapping.scope_type == "organization" else scope.organization_id
    )
    AuditLog.objects.create(
        user=None,
        action="role_assign",
        target_type=type(membership).__name__,
        target_id=membership.id,
        details={
            "migration": MIGRATION_AUDIT_TAG,
            "user_id": str(user.id),
            "scope_type": mapping.scope_type,
            "scope_id": str(mapping.scope_id),
            "target_role": mapping.role,
        },
        role_used="migration",
        organization_id=organization_id,
        business_line_id=(
            scope.id if mapping.scope_type == "business_line" else None
        ),
        space_id=scope.id if mapping.scope_type == "space" else None,
    )


class Command(BaseCommand):
    help = (
        "Audit legacy hr/is_hr_admin accounts and apply only explicit tenant-scope mappings."
    )

    def add_arguments(self, parser):
        parser.add_argument("--mapping-file")
        parser.add_argument("--exception-report")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply validated mappings. Without this flag the command is read-only.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        mapping_file = options.get("mapping_file")
        if apply_changes and not mapping_file:
            raise CommandError("--apply requires --mapping-file.")
        mappings = _load_mapping_file(mapping_file)
        candidates = list(_legacy_candidates())
        candidate_by_id = {candidate.id: candidate for candidate in candidates}
        unknown_ids = sorted(
            {mapping.user_id for mapping in mappings} - set(candidate_by_id),
            key=str,
        )
        if unknown_ids:
            raise CommandError("Mapping contains a user who is not an active legacy candidate.")

        resolved = [(mapping, _resolve_scope(mapping)) for mapping in mappings]
        mapped_user_ids = {mapping.user_id for mapping in mappings}
        existing_scope_ids = _effectively_scoped_user_ids(set(candidate_by_id))
        already_scoped_ids = existing_scope_ids - mapped_user_ids
        exception_ids = sorted(
            (
                candidate.id
                for candidate in candidates
                if candidate.id not in mapped_user_ids
                and candidate.id not in already_scoped_ids
            ),
            key=str,
        )

        created = 0
        unchanged = 0
        if apply_changes:
            with transaction.atomic():
                plans = [
                    (
                        mapping,
                        scope,
                        _plan_mapping(
                            candidate_by_id[mapping.user_id],
                            mapping,
                            scope,
                            lock=True,
                        ),
                    )
                    for mapping, scope in resolved
                ]
                self.stdout.write("mode=apply")
                for mapping, scope, plan in plans:
                    user = candidate_by_id[mapping.user_id]
                    if plan == "create":
                        membership = _create_mapping(user, mapping, scope)
                        created += 1
                        _write_audit(user, mapping, membership, scope)
                        action = "created"
                    else:
                        unchanged += 1
                        action = "unchanged"
                    self.stdout.write(
                        f"candidate={user.id} scope={mapping.scope_type}:{mapping.scope_id} "
                        f"role={mapping.role} action={action}"
                    )
        else:
            plans = [
                (
                    mapping,
                    _plan_mapping(
                        candidate_by_id[mapping.user_id],
                        mapping,
                        scope,
                        lock=False,
                    ),
                )
                for mapping, scope in resolved
            ]
            self.stdout.write("mode=dry-run")
            for mapping, plan in plans:
                action = "would-create" if plan == "create" else "unchanged"
                if plan == "unchanged":
                    unchanged += 1
                self.stdout.write(
                    f"candidate={mapping.user_id} scope={mapping.scope_type}:{mapping.scope_id} "
                    f"role={mapping.role} action={action}"
                )

        for user_id in sorted(already_scoped_ids, key=str):
            self.stdout.write(f"candidate={user_id} action=already-scoped")
        for user_id in exception_ids:
            self.stdout.write(f"candidate={user_id} action=exception reason=unscoped")

        exception_report = options.get("exception_report")
        if exception_report:
            report = {"unscoped_user_ids": [str(user_id) for user_id in exception_ids]}
            try:
                Path(exception_report).write_text(
                    json.dumps(report, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                raise CommandError("Unable to write exception report.") from exc

        self.stdout.write(
            "summary "
            f"candidates={len(candidates)} "
            f"mapped={len(mapped_user_ids)} "
            f"already_scoped={len(already_scoped_ids)} "
            f"exceptions={len(exception_ids)} "
            f"created={created} "
            f"unchanged={unchanged}"
        )
