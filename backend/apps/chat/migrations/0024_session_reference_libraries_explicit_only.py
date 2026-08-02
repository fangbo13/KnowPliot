from django.db import migrations, models


def replace_legacy_null_selection(apps, schema_editor):
    ChatSession = apps.get_model("chat", "ChatSession")
    ChatSession.objects.filter(reference_library_ids__isnull=True).update(
        reference_library_ids=[]
    )


class Migration(migrations.Migration):
    dependencies = [("chat", "0023_alter_citation_options_citation_position")]

    operations = [
        migrations.RunPython(
            replace_legacy_null_selection,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="chatsession",
            name="reference_library_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
