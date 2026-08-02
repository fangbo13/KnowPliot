# Session-level reference-library selection fields.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0021_purge_registry_session_memory"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatsession",
            name="reference_library_ids",
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="chatturn",
            name="reference_library_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
