import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0012_chatsession_is_pinned"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatTurn",
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
                ("client_request_id", models.UUIDField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("accepted", "Accepted"),
                            ("retrieving", "Retrieving"),
                            ("reasoning", "Reasoning"),
                            ("answering", "Answering"),
                            ("saving", "Saving"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="accepted",
                        max_length=20,
                    ),
                ),
                (
                    "answer_mode",
                    models.CharField(
                        choices=[("fast", "Fast"), ("deep", "Deep")],
                        default="fast",
                        max_length=10,
                    ),
                ),
                ("model_id", models.CharField(blank=True, default="", max_length=100)),
                ("attempt_count", models.PositiveIntegerField(default=1)),
                ("last_event_seq", models.PositiveIntegerField(default=0)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assistant_message",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assistant_turn",
                        to="chat.message",
                    ),
                ),
                (
                    "question_message",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="question_turn",
                        to="chat.message",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="turns",
                        to="chat.chatsession",
                    ),
                ),
                (
                    "space",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_turns",
                        to="spaces.knowledgespace",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_turns",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "chat_chatturn",
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(
                        fields=["session", "status"],
                        name="chat_turn_session_status_idx",
                    ),
                    models.Index(
                        fields=["user", "-started_at"],
                        name="chat_turn_user_started_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "client_request_id"),
                        name="chat_turn_user_request_uniq",
                    )
                ],
            },
        )
    ]
