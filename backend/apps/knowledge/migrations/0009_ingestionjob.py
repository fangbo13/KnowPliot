import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0008_document_lifecycle_statuses"),
        ("spaces", "0004_adminregistrationcode_spaceemailinvite"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IngestionJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("trigger", models.CharField(choices=[("upload", "Upload"), ("batch", "Batch Upload"), ("reindex", "Reindex"), ("admin_retry", "Admin Retry")], default="upload", max_length=20)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("processing", "Processing"), ("retrying", "Retrying"), ("succeeded", "Succeeded"), ("failed", "Failed")], db_index=True, default="queued", max_length=20)),
                ("celery_task_id", models.CharField(blank=True, default="", max_length=255)),
                ("attempt", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=4)),
                ("last_error", models.CharField(blank=True, default="", max_length=1000)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ingestion_jobs", to="knowledge.document")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requested_ingestion_jobs", to=settings.AUTH_USER_MODEL)),
                ("retry_of", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="retries", to="knowledge.ingestionjob")),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ingestion_jobs", to="spaces.knowledgespace")),
            ],
            options={
                "db_table": "knowledge_ingestionjob",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="ingestionjob",
            index=models.Index(fields=["space", "status", "-created_at"], name="knowledge_i_space_i_658ba2_idx"),
        ),
        migrations.AddIndex(
            model_name="ingestionjob",
            index=models.Index(fields=["document", "status"], name="knowledge_i_documen_d529b8_idx"),
        ),
    ]
