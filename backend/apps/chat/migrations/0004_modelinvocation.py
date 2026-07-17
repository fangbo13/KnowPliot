import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0003_chatsession_space_citation_space_feedback_space_and_more"),
        ("spaces", "0004_adminregistrationcode_spaceemailinvite"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelInvocation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("model", models.CharField(blank=True, default="", max_length=100)),
                ("status", models.CharField(choices=[("success", "Success"), ("failure", "Failure"), ("timeout", "Timeout"), ("cancelled", "Cancelled")], db_index=True, max_length=20)),
                ("token_count", models.PositiveIntegerField(blank=True, null=True)),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, default="", max_length=50)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("message", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="model_invocation", to="chat.message")),
                ("session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="model_invocations", to="chat.chatsession")),
                ("space", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="model_invocations", to="spaces.knowledgespace")),
            ],
            options={
                "db_table": "chat_modelinvocation",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="modelinvocation",
            index=models.Index(fields=["space", "status", "-created_at"], name="chat_modeli_space_i_cf0e07_idx"),
        ),
        migrations.AddIndex(
            model_name="modelinvocation",
            index=models.Index(fields=["model", "-created_at"], name="chat_modeli_model_d5d3d4_idx"),
        ),
    ]
