import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.chat.models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0015_message_versions_and_session_branches"),
        ("spaces", "0008_organizationmembership_effectiveness"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConversationShare",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("client_request_id", models.UUIDField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(db_index=True, default=apps.chat.models.default_share_expiry)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversation_shares",
                        to="spaces.organization",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversation_shares",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="shares", to="chat.chatsession"
                    ),
                ),
            ],
            options={
                "db_table": "chat_conversationshare",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="conversationshare",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_request_id__isnull", False)),
                fields=("owner", "client_request_id"),
                name="chat_share_owner_request_uniq",
            ),
        ),
    ]
