"""Register the review/graph models with the workspace purge contract.

knowledge.0013 added three models with direct KnowledgeSpace FKs
(ReviewRequest, DocumentLink, TermOwnership).  The purge oracle installed by
spaces.0016 hard-codes the direct-FK count (30) and the registry row count
(36), so workspace deletion now fails closed with "workspace FK oracle
changed".  This migration restores the contract:

1. registers the three models in spaces_workspacepurgedependency
   (migration-owned rows, same pattern as knowledge.0011), and
2. reinstalls spaces_guard_workspace_delete() with the updated counts
   (FK 30 -> 33, registry 36 -> 39).
"""

import django.db.models.deletion  # noqa: F401  (kept for parity with sibling migrations)
from django.db import migrations


MIGRATION_OWNER = "knowledge.0015_purge_registry_review_models"

# Counts after this migration: 30 pre-existing direct space FKs + 3 new ones,
# 36 pre-existing registry rows + 3 new ones.
OLD_REGISTRY_ROW_COUNT = 36
OLD_DIRECT_SPACE_FK_COUNT = 30
NEW_REGISTRY_ROW_COUNT = 39
NEW_DIRECT_SPACE_FK_COUNT = 33


def register_review_models(apps, schema_editor):
    Registry = apps.get_model("spaces", "WorkspacePurgeDependency")
    # 7-tuple mirrors knowledge.0011: (snapshot_fields, scrub_fields,
    # space_field, disposition, blocker_code, lock_order, purge_order).
    # All three are eligible content rows purged before Document (30) and
    # after DocumentChunk (20).
    contracts = {
        "knowledge.ReviewRequest": ([], [], "space", "eligible_content", "", 12, 21),
        "knowledge.DocumentLink": ([], [], "space", "eligible_content", "", 12, 22),
        "knowledge.TermOwnership": ([], [], "space", "eligible_content", "", 12, 23),
    }
    # Use bulk .update() / bulk_create, NOT update_or_create — per-row save()
    # leaves deferred-trigger state that hangs a later migration-contract
    # test tearDown (see knowledge.0011 for the full rationale).
    for model_label, (
        snapshot_fields,
        scrub_fields,
        space_field,
        disposition,
        blocker_code,
        lock_order,
        purge_order,
    ) in contracts.items():
        existing = Registry.objects.filter(
            model_label=model_label,
            migration_owner=MIGRATION_OWNER,
            required=True,
            active=True,
        )
        if existing.exists():
            existing.update(
                snapshot_fields=snapshot_fields,
                scrub_fields=scrub_fields,
                registration_state="ready",
                schema_revision=1,
            )
        else:
            Registry.objects.bulk_create([
                Registry(
                    model_label=model_label,
                    space_field=space_field,
                    migration_owner=MIGRATION_OWNER,
                    disposition=disposition,
                    blocker_code=blocker_code,
                    lock_order=lock_order,
                    purge_order=purge_order,
                    snapshot_fields=snapshot_fields,
                    scrub_fields=scrub_fields,
                    registration_state="ready",
                    schema_revision=1,
                    required=True,
                    active=True,
                )
            ])


def unregister_review_models(apps, schema_editor):
    Registry = apps.get_model("spaces", "WorkspacePurgeDependency")
    Registry.objects.filter(migration_owner=MIGRATION_OWNER).delete()


def _workspace_delete_guard_sql(registry_row_count, direct_space_fk_count):
    # Verbatim copy of the guard installed by spaces.0016, with the two count
    # oracles parameterized so this migration (and its reverse) can reinstall
    # the exact same contract at either revision.
    return f"""
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
               AND target_space_uuid = OLD.id;
            IF v_count <> 1 THEN
                RAISE EXCEPTION 'workspace purge guard: executing request mismatch'
                    USING ERRCODE = '23514';
            END IF;

            SELECT * INTO STRICT v_request
              FROM spaces_governedactionrequest
             WHERE action_type = 'workspace_permanent_delete'
               AND status = 'executing'
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
            IF v_count <> {registry_row_count}
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
            IF v_count <> {direct_space_fk_count} THEN
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


def reinstall_workspace_delete_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        _workspace_delete_guard_sql(NEW_REGISTRY_ROW_COUNT, NEW_DIRECT_SPACE_FK_COUNT)
    )


def restore_previous_workspace_delete_guard(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        _workspace_delete_guard_sql(OLD_REGISTRY_ROW_COUNT, OLD_DIRECT_SPACE_FK_COUNT)
    )


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0014_chunk_metadata_gin_index"),
        # 0013 created ReviewRequest/DocumentLink/TermOwnership (the FKs the
        # new oracle counts); spaces.0016 installed the guard being replaced.
        ("spaces", "0016_workspace_deletion_stage_c"),
    ]

    operations = [
        migrations.RunPython(
            register_review_models,
            reverse_code=unregister_review_models,
        ),
        migrations.RunPython(
            reinstall_workspace_delete_guard,
            reverse_code=restore_previous_workspace_delete_guard,
        ),
    ]
