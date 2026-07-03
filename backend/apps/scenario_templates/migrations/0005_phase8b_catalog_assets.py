import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0010_ingestionjob_know_ing_st_sp_cr_idx"),
        ("scenario_templates", "0004_scenariotemplaterevision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TemplateCategory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=100, unique=True)),
            ],
            options={"db_table": "scenario_templates_category", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="TemplateTag",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=100, unique=True)),
            ],
            options={"db_table": "scenario_templates_tag", "ordering": ["name"]},
        ),
        migrations.AddField(model_name="scenariotemplate", name="category", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="templates", to="scenario_templates.templatecategory")),
        migrations.AddField(model_name="scenariotemplate", name="featured", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="scenariotemplate", name="tags", field=models.ManyToManyField(blank=True, related_name="templates", to="scenario_templates.templatetag")),
        migrations.AddField(model_name="scenariotemplateapplication", name="asset_total", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="scenariotemplateapplication", name="provisioning_status", field=models.CharField(choices=[("completed", "Completed"), ("processing", "Processing"), ("partial_failure", "Partial Failure")], default="completed", max_length=30)),
        migrations.AddField(model_name="scenariotemplateapplication", name="task_ids", field=models.JSONField(blank=True, default=list)),
        migrations.CreateModel(
            name="ScenarioTemplateAsset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="template_assets_created", to=settings.AUTH_USER_MODEL)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="template_assets", to="knowledge.document")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assets", to="scenario_templates.scenariotemplate")),
            ],
            options={"db_table": "scenario_templates_asset", "ordering": ["created_at"], "unique_together": {("template", "document")}},
        ),
        migrations.CreateModel(
            name="TemplateAssetApplication",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("failed", "Failed")], default="pending", max_length=20)),
                ("error_code", models.CharField(blank=True, default="", max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("application", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="asset_applications", to="scenario_templates.scenariotemplateapplication")),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applications", to="scenario_templates.scenariotemplateasset")),
                ("ingestion_job", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="template_asset_applications", to="knowledge.ingestionjob")),
                ("source_document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="template_copy_sources", to="knowledge.document")),
                ("target_document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="template_copy_targets", to="knowledge.document")),
            ],
            options={"db_table": "scenario_templates_asset_application", "unique_together": {("application", "asset")}},
        ),
    ]
