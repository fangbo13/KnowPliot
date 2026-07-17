from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0007_alter_document_file_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("uploading", "Uploading"),
                    ("processing", "Processing"),
                    ("active", "Active"),
                    ("stale", "Stale"),
                    ("archived", "Archived"),
                    ("expired", "Expired"),
                    ("failed", "Failed"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
    ]
