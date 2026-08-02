# Session long/short-term memory: rolling summary + key facts per session.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0019_chatturn_protocol_version"),
        # The purge-registry validator in spaces.0016 snapshots the historical
        # direct-space-FK oracle (30) — this migration MUST order after it so
        # the new SessionMemory.space FK never leaks into that validation.
        ("spaces", "0016_workspace_deletion_stage_c"),
    ]

    operations = [
        migrations.CreateModel(
            name="SessionMemory",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("summary", models.TextField(blank=True, default="")),
                ("key_facts", models.JSONField(blank=True, default=list)),
                ("summarized_until", models.DateTimeField(blank=True, null=True)),
                ("summary_version", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memory",
                        to="chat.chatsession",
                    ),
                ),
                (
                    "space",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="session_memories",
                        to="spaces.knowledgespace",
                    ),
                ),
            ],
            options={
                "db_table": "chat_sessionmemory",
            },
        ),
    ]
