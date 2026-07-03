# Generated for Phase 8A / V10.0.

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0010_message_quality_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RAGEvaluationRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed")], default="running", max_length=20)),
                ("dataset_version", models.CharField(max_length=80)),
                ("config_fingerprint", models.CharField(blank=True, default="", max_length=64)),
                ("metrics", models.JSONField(default=dict)),
                ("report", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rag_evaluation_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "chat_ragevaluationrun",
                "ordering": ["-created_at"],
            },
        ),
    ]
