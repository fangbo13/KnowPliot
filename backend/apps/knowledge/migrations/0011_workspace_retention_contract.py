import hashlib
import unicodedata

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


MIGRATION_OWNER = "knowledge.0011_workspace_retention_contract"


def backfill_retention_snapshots(apps, schema_editor):
    BatchResult = apps.get_model("knowledge", "BatchImportResultRecord")
    IngestionJob = apps.get_model("knowledge", "IngestionJob")
    Locator = apps.get_model("spaces", "WorkspaceLocatorReservation")

    locator_by_space = {
        row[0]: (
            row[1],
            hashlib.sha256(
                unicodedata.normalize("NFC", row[2]).encode("utf-8")
            ).hexdigest(),
        )
        for row in Locator.objects.exclude(live_space_id__isnull=True).values_list(
            "live_space_id", "organization_id", "normalized_locator"
        )
    }
    for job in IngestionJob.objects.all().only(
        "pk", "document_id", "space_id", "requested_by_id"
    ):
        scope = locator_by_space.get(job.space_id)
        if scope is None or not scope[1]:
            raise RuntimeError(
                "knowledge retention migration requires a durable locator for "
                f"IngestionJob {job.pk}"
            )
        IngestionJob.objects.filter(pk=job.pk).update(
            document_uuid=job.document_id,
            space_uuid=job.space_id,
            organization_uuid=scope[0],
            locator_digest=scope[1],
            requested_by_uuid=job.requested_by_id,
        )

    # These historical records pre-date workspace scoping.  Guessing from a
    # filename/tag/user would be unsafe, so keep the ambiguity explicit and
    # fail deletion readiness until an audited resolution exists.
    for result in BatchResult.objects.all().only("pk", "uploaded_by_id"):
        BatchResult.objects.filter(pk=result.pk).update(
            legacy_scope_unknown=True,
            uploaded_by_uuid=result.uploaded_by_id,
        )


def mark_registry_ready(apps, schema_editor):
    Registry = apps.get_model("spaces", "WorkspacePurgeDependency")
    # 7-tuple: (snapshot_fields, scrub_fields, space_field, disposition,
    # blocker_code, lock_order, purge_order). The create-contract fields
    # mirror spaces.0015 REGISTRY_ROWS for the knowledge.* models so this
    # migration is authoritative for the knowledge purge deps.
    contracts = {
        "knowledge.DocumentCategory": (
            [], [], "space", "eligible_content", "child_categories", 13, 10,
        ),
        "knowledge.DocumentChunk": (
            [], [], "space", "eligible_content", "", 12, 20,
        ),
        "knowledge.Document": (
            [], [], "space", "eligible_content", "", 12, 30,
        ),
        "knowledge.IngestionJob": (
            [
                "space_uuid",
                "organization_uuid",
                "locator_digest",
                "tombstone_id",
                "document_uuid",
                "requested_by_uuid",
            ],
            ["celery_task_id", "last_error", "sensitive_payload_scrubbed_at"],
            "space", "retained_evidence", "open_tasks", 13, 40,
        ),
        "knowledge.BatchImportResultRecord": (
            [
                "space_uuid",
                "organization_uuid",
                "locator_digest",
                "tombstone_id",
                "uploaded_by_uuid",
                "legacy_scope_unknown",
            ],
            ["error_message", "result_details", "sensitive_payload_scrubbed_at"],
            "space", "retained_evidence", "open_tasks", 13, 50,
        ),
    }
    # Use bulk .update() for existing rows + bulk_create for missing rows.
    # NOT update_or_create: the per-row save() that update_or_create triggers
    # was found to leave deferred-trigger state in a later ownership stage_c
    # migration-contract test's tearDown, hanging it. .update() and
    # bulk_create are bulk SQL with no per-row model save() / signals, so no
    # deferred-trigger side effects. Missing rows occur in TransactionTestCase
    # context (truncation between tests; spaces.0015 seed does not re-run once
    # applied); production runs always have the rows (seeded by spaces.0015),
    # so the existing-row path is taken there.
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


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0010_ingestionjob_know_ing_st_sp_cr_idx"),
        ("spaces", "0015_workspace_deletion_stage_a"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="batchimportresultrecord",
            name="legacy_scope_unknown",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="batchimportresultrecord",
            name="locator_digest",
            field=models.CharField(blank=True, default="", editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name="batchimportresultrecord",
            name="organization_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="batchimportresultrecord",
            name="sensitive_payload_scrubbed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="batchimportresultrecord",
            name="space",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="batch_import_results",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AddField(
            model_name="batchimportresultrecord",
            name="space_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="batchimportresultrecord",
            name="tombstone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="batch_import_results",
                to="spaces.workspacetombstone",
            ),
        ),
        migrations.AddField(
            model_name="batchimportresultrecord",
            name="uploaded_by_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="documentcategory",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="knowledge.documentcategory",
            ),
        ),
        migrations.AddField(
            model_name="documentcategory",
            name="space",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="document_categories",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="document_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="locator_digest",
            field=models.CharField(blank=True, default="", editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="organization_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="requested_by_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="sensitive_payload_scrubbed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="space_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="tombstone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ingestion_jobs",
                to="spaces.workspacetombstone",
            ),
        ),
        migrations.RunPython(
            backfill_retention_snapshots,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="batchimportresultrecord",
            name="uploaded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="ingestionjob",
            name="document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ingestion_jobs",
                to="knowledge.document",
            ),
        ),
        migrations.AlterField(
            model_name="ingestionjob",
            name="space",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ingestion_jobs",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AddConstraint(
            model_name="batchimportresultrecord",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("legacy_scope_unknown", True),
                        ("space__isnull", True),
                        ("space_uuid__isnull", True),
                    ),
                    models.Q(
                        ("legacy_scope_unknown", False),
                        ("space_uuid__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="knowledge_batch_scope_evidence",
            ),
        ),
        migrations.AddConstraint(
            model_name="batchimportresultrecord",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("locator_digest", ""),
                    ("locator_digest__regex", "^[0-9a-f]{64}$"),
                    _connector="OR",
                ),
                name="knowledge_batch_locator_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="ingestionjob",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("space__isnull", False),
                    ("space_uuid__isnull", False),
                    _connector="OR",
                ),
                name="knowledge_ingestion_space_evidence",
            ),
        ),
        migrations.AddConstraint(
            model_name="ingestionjob",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("locator_digest", ""),
                    ("locator_digest__regex", "^[0-9a-f]{64}$"),
                    _connector="OR",
                ),
                name="knowledge_ingestion_locator_shape",
            ),
        ),
        migrations.RunPython(
            mark_registry_ready,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
