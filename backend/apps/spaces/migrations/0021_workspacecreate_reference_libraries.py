# Creator-selected reference libraries for new workspaces (opt-in pool).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("spaces", "0020_knowledgespace_taxonomy_mode_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspacecreaterequestdetail",
            name="reference_library_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
