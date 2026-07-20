import hashlib
import unicodedata

import django.db.models.deletion
from django.db import migrations, models


MIGRATION_OWNER = "audit.0015_workspace_retention_contract"


def backfill_audit_snapshots(apps, schema_editor):
    AuditLog = apps.get_model("audit", "AuditLog")
    Locator = apps.get_model("spaces", "WorkspaceLocatorReservation")
    locator_by_space = {
        row[0]: hashlib.sha256(
            unicodedata.normalize("NFC", row[1]).encode("utf-8")
        ).hexdigest()
        for row in Locator.objects.exclude(live_space_id__isnull=True).values_list(
            "live_space_id", "normalized_locator"
        )
    }
    for event in AuditLog.objects.all().only("pk", "user_id", "space_id"):
        AuditLog.objects.filter(pk=event.pk).update(
            actor_uuid=event.user_id,
            locator_digest=locator_by_space.get(event.space_id, ""),
        )


def mark_registry_ready(apps, schema_editor):
    Registry = apps.get_model("spaces", "WorkspacePurgeDependency")
    # Use bulk .update() for existing + bulk_create for missing (NOT
    # update_or_create): the per-row save() that update_or_create triggers
    # was found to leave deferred-trigger state in a later ownership stage_c
    # migration-contract test's tearDown, hanging it. .update() and
    # bulk_create are bulk SQL with no per-row model save() / signals. Missing
    # rows occur in TransactionTestCase context (truncation; spaces.0015 seed
    # does not re-run once applied); production runs take the existing-row path.
    # Create-contract fields mirror spaces.0015 REGISTRY_ROWS.
    snapshot_fields = [
        "space_id",
        "organization_id",
        "business_line_id",
        "locator_digest",
        "tombstone_id",
        "actor_uuid",
        "governed_request_uuid",
    ]
    existing = Registry.objects.filter(
        model_label="audit.AuditLog",
        migration_owner=MIGRATION_OWNER,
        required=True,
        active=True,
    )
    if existing.exists():
        existing.update(
            snapshot_fields=snapshot_fields,
            scrub_fields=[],
            registration_state="ready",
            schema_revision=1,
        )
    else:
        Registry.objects.bulk_create([
            Registry(
                model_label="audit.AuditLog",
                space_field="space_id",
                migration_owner=MIGRATION_OWNER,
                disposition="retained_evidence",
                blocker_code="",
                lock_order=15,
                purge_order=170,
                snapshot_fields=snapshot_fields,
                scrub_fields=[],
                registration_state="ready",
                schema_revision=1,
                required=True,
                active=True,
            )
        ])


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0014_alter_auditlog_action_and_more"),
        ("scenario_templates", "0007_workspace_retention_contract"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="actor_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="governed_request",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_logs",
                to="spaces.governedactionrequest",
            ),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="governed_request_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="locator_digest",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=64
            ),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="tombstone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audit_logs",
                to="spaces.workspacetombstone",
            ),
        ),
        migrations.RunPython(
            backfill_audit_snapshots,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="auditlog",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex="^[0-9a-f]{64}$")
                ),
                name="audit_locator_digest_shape",
            ),
        ),
        migrations.RunPython(
            mark_registry_ready,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

