import uuid

import django.db.models.deletion
from django.db import migrations, models


def backfill_version_groups(apps, schema_editor):
    Message = apps.get_model("chat", "Message")
    batch = []
    for message in Message.objects.filter(version_group_id__isnull=True).iterator(
        chunk_size=1000
    ):
        message.version_group_id = uuid.uuid4()
        batch.append(message)
        if len(batch) == 1000:
            Message.objects.bulk_update(batch, ["version_group_id"], batch_size=1000)
            batch = []
    if batch:
        Message.objects.bulk_update(batch, ["version_group_id"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0014_chatturn_metrics_and_model_lengths"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="version_group_id",
            field=models.UUIDField(db_index=True, null=True),
        ),
        migrations.RunPython(backfill_version_groups, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="message",
            name="version_group_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4),
        ),
        migrations.AddField(
            model_name="message",
            name="version_number",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="message",
            name="is_current_version",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="message",
            name="supersedes_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="newer_versions",
                to="chat.message",
            ),
        ),
        migrations.AddField(
            model_name="chatsession",
            name="branch_request_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chatsession",
            name="branched_from_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="branched_sessions",
                to="chat.message",
            ),
        ),
        migrations.AlterField(
            model_name="chatturn",
            name="question_message",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="question_turns",
                to="chat.message",
            ),
        ),
        migrations.AddConstraint(
            model_name="chatsession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("branch_request_id__isnull", False)),
                fields=("user", "branch_request_id"),
                name="chat_session_user_branch_request_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="message",
            constraint=models.UniqueConstraint(
                fields=("version_group_id", "version_number"),
                name="chat_message_version_number_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="message",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_current_version", True)),
                fields=("version_group_id",),
                name="chat_message_one_current_version_uniq",
            ),
        ),
    ]
