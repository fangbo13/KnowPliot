import hashlib
import unicodedata

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


REGISTRY_ROW_COUNT = 36
DIRECT_SPACE_FK_COUNT = 30


def _locator_digest(value):
    canonical = unicodedata.normalize("NFC", value or "")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def backfill_stage_c_snapshots(apps, schema_editor):
    Locator = apps.get_model("spaces", "WorkspaceLocatorReservation")
    OwnershipTransfer = apps.get_model("spaces", "OwnershipTransfer")
    GovernancePolicy = apps.get_model("spaces", "GovernancePolicy")

    scope_by_space = {
        row[0]: (row[1], _locator_digest(row[2]))
        for row in Locator.objects.exclude(live_space_id__isnull=True).values_list(
            "live_space_id", "organization_id", "normalized_locator"
        )
    }
    for transfer in OwnershipTransfer.objects.all().only("pk", "space_id"):
        scope = scope_by_space.get(transfer.space_id)
        if scope is None:
            raise RuntimeError(
                "workspace deletion Stage C requires a durable locator for "
                f"OwnershipTransfer {transfer.pk}"
            )
        OwnershipTransfer.objects.filter(pk=transfer.pk).update(
            space_uuid=transfer.space_id,
            organization_uuid=scope[0],
            locator_digest=scope[1],
        )

    for policy in GovernancePolicy.objects.exclude(space_id__isnull=True).only(
        "pk", "space_id"
    ):
        scope = scope_by_space.get(policy.space_id)
        if scope is None:
            raise RuntimeError(
                "workspace deletion Stage C requires a durable locator for "
                f"GovernancePolicy {policy.pk}"
            )
        GovernancePolicy.objects.filter(pk=policy.pk).update(
            space_uuid=policy.space_id,
            organization_uuid=scope[0],
            locator_digest=scope[1],
        )


FINAL_REGISTRY_METADATA = {
    "users.User": (
        "default_space",
        [],
        [],
    ),
    "spaces.SpaceMembership": ("space", [], []),
    "spaces.InviteCode": ("space", [], []),
    "spaces.SpaceEmailInvite": ("space", [], []),
    "spaces.SpaceAccessCode": ("space", [], []),
    "spaces.SpaceInvitation": ("space", [], []),
    "spaces.SpaceAccessRequest": ("space", [], []),
    "spaces.WorkspaceUsageDaily": ("space", [], []),
    "spaces.KnowledgeSpaceOfficeLocation": ("space", [], []),
    "spaces.WorkspaceUsageSummary": ("space", [], []),
    "spaces.GovernancePolicy": (
        "space",
        ["space_uuid", "organization_uuid", "locator_digest", "tombstone_id"],
        [],
    ),
    "spaces.OwnershipTransfer": (
        "space",
        [
            "space_uuid",
            "organization_uuid",
            "locator_digest",
            "tombstone_id",
            "from_owner_id",
            "to_owner_id",
            "requested_by_id",
            "accepted_by_id",
        ],
        ["reason_note"],
    ),
    "spaces.GovernedActionRequest": (
        "target_space",
        [
            "target_space_uuid",
            "requester_uuid",
            "reviewer_uuid",
            "locator_reservation_id",
        ],
        ["impact_snapshot", "reason_text"],
    ),
    "spaces.WorkspaceRetentionHold": (
        "space",
        [
            "space_uuid",
            "organization_uuid",
            "locator_digest",
            "tombstone_id",
            "created_by_uuid",
            "released_by_uuid",
        ],
        [],
    ),
    "spaces.WorkspaceLocatorReservation": (
        "live_space",
        [
            "organization_id",
            "normalized_locator",
            "live_space_id",
            "active_request_id",
            "tombstone_id",
        ],
        [],
    ),
    "spaces.WorkspaceTombstone": (
        "original_space_uuid",
        [
            "original_space_uuid",
            "organization_uuid",
            "request_uuid",
            "locator_reservation_id",
            "locator_digest",
            "normalized_locator",
            "normalized_org_slug",
            "normalized_space_code",
        ],
        [],
    ),
    "spaces.WorkspacePurgeJob": (
        "request",
        [
            "request_id",
            "session_fence_token",
            "request_version_snapshot",
            "lifecycle_version_snapshot",
            "ownership_version_snapshot",
            "impact_version_snapshot",
            "retention_not_before",
            "manifest_version",
            "manifest_digest",
        ],
        [],
    ),
    "spaces.WorkspacePurgeCheckpoint": (
        "job",
        [
            "job_id",
            "store_code",
            "batch_key",
            "expected_digest",
            "acknowledged_digest",
            "lease_generation",
            "acknowledged_at",
        ],
        [],
    ),
    "notifications.Notification": (
        "resource_uuid",
        ["resource_type", "resource_uuid", "resource_version"],
        ["body", "metadata", "link", "allowed_actions", "deep_link"],
    ),
}


def _field_names(model):
    names = set()
    for field in model._meta.concrete_fields:
        names.add(field.name)
        names.add(field.attname)
    return names


def finalize_and_validate_registry(apps, schema_editor):
    Registry = apps.get_model("spaces", "WorkspacePurgeDependency")
    Space = apps.get_model("spaces", "KnowledgeSpace")

    for model_label, (space_field, snapshot_fields, scrub_fields) in (
        FINAL_REGISTRY_METADATA.items()
    ):
        updated = Registry.objects.filter(
            model_label=model_label,
            space_field=space_field,
            required=True,
            active=True,
        ).update(
            snapshot_fields=snapshot_fields,
            scrub_fields=scrub_fields,
            registration_state="ready",
            schema_revision=1,
        )
        if updated != 1:
            raise RuntimeError(
                f"missing or duplicate final purge registry row for {model_label}"
            )

    rows = list(
        Registry.objects.filter(required=True, active=True).order_by(
            "model_label", "space_field"
        )
    )
    if len(rows) != REGISTRY_ROW_COUNT:
        raise RuntimeError(
            f"purge registry expected {REGISTRY_ROW_COUNT} rows, found {len(rows)}"
        )
    if any(row.registration_state != "ready" for row in rows):
        raise RuntimeError("purge registry contains a pending required migration")

    registered_direct = set()
    invalid_metadata = []
    for row in rows:
        try:
            model = apps.get_model(row.model_label)
        except (LookupError, ValueError) as exc:
            raise RuntimeError(f"unknown purge registry model {row.model_label}") from exc
        names = _field_names(model)
        for field_name in tuple(row.snapshot_fields or ()) + tuple(
            row.scrub_fields or ()
        ):
            if field_name not in names:
                invalid_metadata.append(f"{row.model_label}.{field_name}")
        if "__" not in row.space_field and row.space_field in names:
            field = next(
                (
                    candidate
                    for candidate in model._meta.concrete_fields
                    if row.space_field in {candidate.name, candidate.attname}
                ),
                None,
            )
            remote = getattr(getattr(field, "remote_field", None), "model", None)
            if remote is Space:
                registered_direct.add(
                    f"{model._meta.label_lower}.{field.name}"
                )
    if invalid_metadata:
        raise RuntimeError(
            "purge registry references missing fields: "
            + ", ".join(sorted(invalid_metadata))
        )

    expected_direct = set()
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            remote = getattr(getattr(field, "remote_field", None), "model", None)
            if remote is Space:
                expected_direct.add(f"{model._meta.label_lower}.{field.name}")
    if len(expected_direct) != DIRECT_SPACE_FK_COUNT:
        raise RuntimeError(
            f"direct workspace FK oracle expected {DIRECT_SPACE_FK_COUNT}, "
            f"found {len(expected_direct)}"
        )
    missing = expected_direct - registered_direct
    if missing:
        raise RuntimeError(
            "purge registry is missing direct workspace FKs: "
            + ", ".join(sorted(missing))
        )


def install_postgresql_purge_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION spaces_guard_tombstoned_locator()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.state = 'tombstoned' THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'tombstoned workspace locator is permanent'
                        USING ERRCODE = '23514';
                END IF;
                IF NEW.state <> 'tombstoned'
                   OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
                   OR NEW.normalized_code IS DISTINCT FROM OLD.normalized_code
                   OR NEW.normalized_locator IS DISTINCT FROM OLD.normalized_locator
                   OR NEW.tombstone_id IS DISTINCT FROM OLD.tombstone_id THEN
                    RAISE EXCEPTION 'tombstoned workspace locator is immutable'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$;

        DROP TRIGGER IF EXISTS spaces_locator_tombstone_guard
            ON spaces_workspacelocatorreservation;
        CREATE TRIGGER spaces_locator_tombstone_guard
            BEFORE UPDATE OR DELETE ON spaces_workspacelocatorreservation
            FOR EACH ROW EXECUTE FUNCTION spaces_guard_tombstoned_locator();
        """
    )
    schema_editor.execute(
        f"""
        CREATE OR REPLACE FUNCTION spaces_guard_workspace_delete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_request spaces_governedactionrequest;
            v_detail spaces_workspacedeletionrequestdetail;
            v_job spaces_workspacepurgejob;
            v_tombstone spaces_workspacetombstone;
            v_locator spaces_workspacelocatorreservation;
            v_count integer;
            v_external integer;
            v_database integer;
            v_fence text;
        BEGIN
            SELECT COUNT(*) INTO v_count
              FROM spaces_governedactionrequest
             WHERE action_type = 'workspace_permanent_delete'
               AND status = 'executing'
               AND target_space_id = OLD.id
               AND target_space_uuid = OLD.id;
            IF v_count <> 1 THEN
                RAISE EXCEPTION 'workspace purge guard: executing request mismatch'
                    USING ERRCODE = '23514';
            END IF;

            SELECT * INTO STRICT v_request
              FROM spaces_governedactionrequest
             WHERE action_type = 'workspace_permanent_delete'
               AND status = 'executing'
               AND target_space_id = OLD.id
               AND target_space_uuid = OLD.id;
            SELECT * INTO STRICT v_detail
              FROM spaces_workspacedeletionrequestdetail
             WHERE request_id = v_request.id;
            SELECT * INTO STRICT v_job
              FROM spaces_workspacepurgejob
             WHERE request_id = v_request.id;
            SELECT * INTO STRICT v_tombstone
              FROM spaces_workspacetombstone
             WHERE request_id = v_request.id
               AND original_space_uuid = OLD.id;
            SELECT * INTO STRICT v_locator
              FROM spaces_workspacelocatorreservation
             WHERE id = v_request.locator_reservation_id;

            IF OLD.status <> 'archived'
               OR OLD.archived_at IS NULL
               OR (OLD.retention_until IS NOT NULL AND OLD.retention_until > clock_timestamp())
               OR v_detail.confirmed_at IS NULL
               OR v_detail.purge_not_before IS NULL
               OR v_detail.purge_not_before > clock_timestamp()
               OR v_detail.archived_at IS DISTINCT FROM OLD.archived_at
               OR v_detail.expected_lifecycle_version <> OLD.lifecycle_version
               OR v_detail.expected_ownership_version <> OLD.ownership_version
               OR v_detail.expected_dependency_version <> OLD.dependency_version
               OR v_detail.retention_policy_version <> OLD.retention_policy_version
               OR v_detail.storage_manifest_version <> OLD.storage_manifest_version
               OR v_detail.storage_manifest_digest IS DISTINCT FROM OLD.storage_manifest_digest THEN
                RAISE EXCEPTION 'workspace purge guard: lifecycle or retention mismatch'
                    USING ERRCODE = '23514';
            END IF;

            IF v_job.state <> 'running'
               OR v_job.lease_expires_at IS NULL
               OR v_job.lease_expires_at <= clock_timestamp()
               OR v_job.lease_generation <> OLD.purge_fence_generation
               OR v_job.request_version_snapshot <> v_request.request_version
               OR v_job.lifecycle_version_snapshot <> OLD.lifecycle_version
               OR v_job.ownership_version_snapshot <> OLD.ownership_version
               OR v_job.impact_version_snapshot IS DISTINCT FROM v_request.impact_version
               OR v_job.retention_not_before IS NULL
               OR v_job.retention_not_before > clock_timestamp()
               OR v_job.manifest_version <> OLD.storage_manifest_version
               OR v_job.manifest_digest IS DISTINCT FROM OLD.storage_manifest_digest THEN
                RAISE EXCEPTION 'workspace purge guard: job fence mismatch'
                    USING ERRCODE = '23514';
            END IF;

            v_fence := v_job.session_fence_token::text || ':' || v_job.lease_generation::text;
            IF COALESCE(current_setting('knowpilot.purge_fence', true), '') <> v_fence THEN
                RAISE EXCEPTION 'workspace purge guard: session fence mismatch'
                    USING ERRCODE = '23514';
            END IF;

            IF v_tombstone.request_uuid IS DISTINCT FROM v_request.id
               OR v_tombstone.organization_uuid IS DISTINCT FROM OLD.organization_id
               OR v_tombstone.locator_reservation_id IS DISTINCT FROM v_locator.id
               OR v_tombstone.locator_digest IS DISTINCT FROM v_detail.confirmation_digest
               OR v_tombstone.normalized_locator IS DISTINCT FROM v_detail.locator
               OR v_tombstone.purged_at IS NOT NULL
               OR v_locator.organization_id IS DISTINCT FROM OLD.organization_id
               OR v_locator.state <> 'tombstoned'
               OR v_locator.live_space_id IS NOT NULL
               OR v_locator.active_request_id IS NOT NULL
               OR v_locator.tombstone_id IS DISTINCT FROM v_tombstone.id THEN
                RAISE EXCEPTION 'workspace purge guard: tombstone mismatch'
                    USING ERRCODE = '23514';
            END IF;

            SELECT COUNT(*),
                   COUNT(*) FILTER (
                       WHERE store_code IN ('blob', 'search', 'vector', 'replay')
                         AND batch_key = 'manifest'
                         AND status = 'acked'
                         AND expected_digest = v_job.manifest_digest
                         AND acknowledged_digest = v_job.manifest_digest
                         AND lease_generation = v_job.lease_generation
                         AND acknowledged_at IS NOT NULL
                   ),
                   COUNT(*) FILTER (
                       WHERE store_code = 'database'
                         AND batch_key = 'manifest'
                         AND status = 'running'
                         AND expected_digest = v_job.manifest_digest
                         AND lease_generation = v_job.lease_generation
                   )
              INTO v_count, v_external, v_database
              FROM spaces_workspacepurgecheckpoint
             WHERE job_id = v_job.id;
            IF v_count <> 5 OR v_external <> 4 OR v_database <> 1 THEN
                RAISE EXCEPTION 'workspace purge guard: checkpoint mismatch'
                    USING ERRCODE = '23514';
            END IF;

            IF EXISTS (
                SELECT 1 FROM spaces_workspaceretentionhold
                 WHERE space_uuid = OLD.id
                   AND status = 'active'
                   AND (release_not_before IS NULL OR release_not_before > clock_timestamp())
            ) THEN
                RAISE EXCEPTION 'workspace purge guard: active retention hold'
                    USING ERRCODE = '23514';
            END IF;

            SELECT COUNT(*) INTO v_count
              FROM spaces_workspacepurgedependency
             WHERE required = TRUE AND active = TRUE;
            IF v_count <> {REGISTRY_ROW_COUNT}
               OR EXISTS (
                    SELECT 1 FROM spaces_workspacepurgedependency
                     WHERE required = TRUE
                       AND active = TRUE
                       AND (registration_state <> 'ready' OR schema_revision < 1)
               ) THEN
                RAISE EXCEPTION 'workspace purge guard: registry incomplete'
                    USING ERRCODE = '23514';
            END IF;

            SELECT COUNT(*) INTO v_count
              FROM pg_constraint
             WHERE contype = 'f'
               AND confrelid = 'spaces_knowledgespace'::regclass;
            IF v_count <> {DIRECT_SPACE_FK_COUNT} THEN
                RAISE EXCEPTION 'workspace purge guard: workspace FK oracle changed'
                    USING ERRCODE = '23514';
            END IF;
            RETURN OLD;
        EXCEPTION
            WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN
                RAISE EXCEPTION 'workspace purge guard: required lineage missing'
                    USING ERRCODE = '23514';
        END;
        $$;

        DROP TRIGGER IF EXISTS spaces_workspace_delete_guard
            ON spaces_knowledgespace;
        CREATE TRIGGER spaces_workspace_delete_guard
            BEFORE DELETE ON spaces_knowledgespace
            FOR EACH ROW EXECUTE FUNCTION spaces_guard_workspace_delete();
        """
    )


def remove_postgresql_purge_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS spaces_workspace_delete_guard ON spaces_knowledgespace;"
    )
    schema_editor.execute("DROP FUNCTION IF EXISTS spaces_guard_workspace_delete();")
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS spaces_locator_tombstone_guard "
        "ON spaces_workspacelocatorreservation;"
    )
    schema_editor.execute("DROP FUNCTION IF EXISTS spaces_guard_tombstoned_locator();")


class Migration(migrations.Migration):
    dependencies = [
        ("spaces", "0015_workspace_deletion_stage_a"),
        ("audit", "0015_workspace_retention_contract"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="governancepolicy",
            name="locator_digest",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=64
            ),
        ),
        migrations.AddField(
            model_name="ownershiptransfer",
            name="locator_digest",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=64
            ),
        ),
        migrations.AddField(
            model_name="ownershiptransfer",
            name="organization_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="ownershiptransfer",
            name="space_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="ownershiptransfer",
            name="tombstone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ownership_transfers",
                to="spaces.workspacetombstone",
            ),
        ),
        migrations.RunPython(
            backfill_stage_c_snapshots,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="ownershiptransfer",
            name="space",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ownership_transfers",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AddConstraint(
            model_name="governancepolicy",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(space_uuid__isnull=True, locator_digest="")
                    | models.Q(
                        space_uuid__isnull=False,
                        organization_uuid__isnull=False,
                        locator_digest__regex="^[0-9a-f]{64}$",
                    )
                ),
                name="spaces_governance_scope_evidence",
            ),
        ),
        migrations.AddConstraint(
            model_name="ownershiptransfer",
            constraint=models.CheckConstraint(
                check=models.Q(
                    space_uuid__isnull=False,
                    organization_uuid__isnull=False,
                    locator_digest__regex="^[0-9a-f]{64}$",
                ),
                name="spaces_owner_transfer_space_evidence",
            ),
        ),
        migrations.AddConstraint(
            model_name="workspacelocatorreservation",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(
                        state="request_reserved",
                        active_request__isnull=False,
                        live_space__isnull=True,
                        tombstone__isnull=True,
                    )
                    | models.Q(
                        state="live",
                        live_space__isnull=False,
                        active_request__isnull=True,
                        tombstone__isnull=True,
                    )
                    | models.Q(
                        state="tombstoned",
                        tombstone__isnull=False,
                        live_space__isnull=True,
                        active_request__isnull=True,
                    )
                    | models.Q(
                        state="released",
                        live_space__isnull=True,
                        active_request__isnull=True,
                        tombstone__isnull=True,
                    )
                ),
                name="spaces_locator_state_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="workspacetombstone",
            constraint=models.CheckConstraint(
                check=(
                    ~models.Q(normalized_locator="")
                    & ~models.Q(normalized_org_slug="")
                    & ~models.Q(normalized_space_code="")
                    & models.Q(request_uuid=models.F("request"))
                ),
                name="spaces_tombstone_identity_shape",
            ),
        ),
        migrations.RunPython(
            finalize_and_validate_registry,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            install_postgresql_purge_guards,
            remove_postgresql_purge_guards,
        ),
    ]
