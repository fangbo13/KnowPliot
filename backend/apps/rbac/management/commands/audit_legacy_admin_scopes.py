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
from django.db.models import Q

from apps.audit.models import AuditLog
from apps.spaces.models import (
    BusinessLine,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)

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


def _apply_mapping(user, mapping: ScopeMapping, scope) -> tuple[object, bool]:
    if mapping.scope_type == "space":
        membership = SpaceMembership.objects.filter(user=user, space=scope).first()
        if membership is None:
            return (
                SpaceMembership.objects.create(
                    user=user,
                    space=scope,
                    role=mapping.role,
                    status="active",
                ),
                True,
            )
        if (
            membership.role == mapping.role
            and membership.status == "active"
            and membership.expires_at is None
        ):
            return membership, False
        membership.role = mapping.role
        membership.status = "active"
        membership.expires_at = None
        membership.save(update_fields=["role", "status", "expires_at", "updated_at"])
        return membership, True

    organization = scope if mapping.scope_type == "organization" else scope.organization
    business_line = None if mapping.scope_type == "organization" else scope
    membership = OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
        business_line=business_line,
        role=mapping.role,
    ).first()
    if membership is None:
        return (
            OrganizationMembership.objects.create(
                user=user,
                organization=organization,
                business_line=business_line,
                role=mapping.role,
            ),
            True,
        )
    if membership.is_active and membership.expires_at is None:
        return membership, False
    membership.is_active = True
    membership.expires_at = None
    membership.save(update_fields=["is_active", "expires_at", "updated_at"])
    return membership, True


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
        exception_ids = sorted(
            (candidate.id for candidate in candidates if candidate.id not in mapped_user_ids),
            key=str,
        )
        self.stdout.write(f"mode={'apply' if apply_changes else 'dry-run'}")

        created = 0
        unchanged = 0
        if apply_changes:
            with transaction.atomic():
                for mapping, scope in resolved:
                    user = candidate_by_id[mapping.user_id]
                    membership, changed = _apply_mapping(user, mapping, scope)
                    if changed:
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
            for mapping, _scope in resolved:
                self.stdout.write(
                    f"candidate={mapping.user_id} scope={mapping.scope_type}:{mapping.scope_id} "
                    f"role={mapping.role} action=would-apply"
                )

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
            f"exceptions={len(exception_ids)} "
            f"created={created} "
            f"unchanged={unchanged}"
        )
