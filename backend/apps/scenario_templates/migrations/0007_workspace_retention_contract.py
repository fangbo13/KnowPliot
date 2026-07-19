import hashlib
import unicodedata

import django.db.models.deletion
from django.db import migrations, models


MIGRATION_OWNER = "scenario_templates.0007_workspace_retention_contract"


def _locator_digest(value):
    canonical = unicodedata.normalize("NFC", value or "")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def backfill_application_snapshots(apps, schema_editor):
    Application = apps.get_model(
        "scenario_templates", "ScenarioTemplateApplication"
    )
    Locator = apps.get_model("spaces", "WorkspaceLocatorReservation")

    scope_by_space = {
        row[0]: (row[1], _locator_digest(row[2]))
        for row in Locator.objects.exclude(live_space_id__isnull=True).values_list(
            "live_space_id", "organization_id", "normalized_locator"
        )
    }
    for application in Application.objects.select_related(
        "template", "template_revision"
    ).order_by("pk"):
        organization_uuid = application.organization_id
        locator_digest = ""
        if application.space_id:
            scope = scope_by_space.get(application.space_id)
            if scope is None:
                raise RuntimeError(
                    "scenario retention migration requires a durable locator for "
                    f"ScenarioTemplateApplication {application.pk}"
                )
            organization_uuid = scope[0]
            locator_digest = scope[1]
        revision = application.template_revision
        Application.objects.filter(pk=application.pk).update(
            template_uuid=application.template_id,
            template_key_snapshot=application.template.code,
            space_uuid=application.space_id,
            organization_uuid=organization_uuid,
            locator_digest=locator_digest,
            created_by_uuid=application.created_by_id,
            template_revision_uuid=(revision.pk if revision else None),
            template_revision_hash=(revision.snapshot_hash if revision else ""),
        )


def mark_registry_ready(apps, schema_editor):
    Registry = apps.get_model("spaces", "WorkspacePurgeDependency")
    updated = Registry.objects.filter(
        model_label="scenario_templates.ScenarioTemplateApplication",
        migration_owner=MIGRATION_OWNER,
        required=True,
        active=True,
    ).update(
        snapshot_fields=[
            "space_uuid",
            "organization_uuid",
            "locator_digest",
            "tombstone_id",
            "template_uuid",
            "template_key_snapshot",
            "template_revision_uuid",
            "template_revision_hash",
            "created_by_uuid",
            "legacy_revision_unknown",
        ],
        scrub_fields=[
            "task_ids",
            "template_snapshot",
            "sensitive_payload_scrubbed_at",
        ],
        registration_state="ready",
        schema_revision=1,
    )
    if updated != 1:
        raise RuntimeError(
            "missing or duplicate purge registry row for "
            "scenario_templates.ScenarioTemplateApplication"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("scenario_templates", "0006_versioned_clone_contract"),
        ("chat", "0018_workspace_retention_contract"),
    ]

    operations = [
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="created_by_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="locator_digest",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=64
            ),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="organization_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="sensitive_payload_scrubbed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="space_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="template_key_snapshot",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=120
            ),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="template_revision_hash",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=64
            ),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="template_revision_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="template_uuid",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="scenariotemplateapplication",
            name="tombstone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scenario_template_applications",
                to="spaces.workspacetombstone",
            ),
        ),
        migrations.RunPython(
            backfill_application_snapshots,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="scenariotemplateapplication",
            name="template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="applications",
                to="scenario_templates.scenariotemplate",
            ),
        ),
        migrations.AddConstraint(
            model_name="scenariotemplateapplication",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(template__isnull=False)
                    | models.Q(template_uuid__isnull=False)
                ),
                name="scenario_app_template_evidence",
            ),
        ),
        migrations.AddConstraint(
            model_name="scenariotemplateapplication",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(
                        legacy_revision_unknown=True,
                        template_revision__isnull=True,
                    )
                    | models.Q(
                        legacy_revision_unknown=False,
                        template_revision__isnull=False,
                        template_revision_uuid__isnull=False,
                        template_revision_hash__regex="^[0-9a-f]{64}$",
                    )
                ),
                name="scenario_app_revision_evidence",
            ),
        ),
        migrations.AddConstraint(
            model_name="scenariotemplateapplication",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex="^[0-9a-f]{64}$")
                ),
                name="scenario_app_locator_shape",
            ),
        ),
        migrations.RunPython(
            mark_registry_ready,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
