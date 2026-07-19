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
    updated = Registry.objects.filter(
        model_label="audit.AuditLog",
        migration_owner=MIGRATION_OWNER,
        required=True,
        active=True,
    ).update(
        snapshot_fields=[
            "space_id",
            "organization_id",
            "business_line_id",
            "locator_digest",
            "tombstone_id",
            "actor_uuid",
            "governed_request_uuid",
        ],
        scrub_fields=[],
        registration_state="ready",
        schema_revision=1,
    )
    if updated != 1:
        raise RuntimeError("missing or duplicate purge registry row for audit.AuditLog")


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

