from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0008_alter_auditlog_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="organization_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="business_line_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="space_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="auditlog",
            name="result",
            field=models.CharField(
                choices=[
                    ("success", "Success"),
                    ("denied", "Denied"),
                    ("failure", "Failure"),
                ],
                db_index=True,
                default="success",
                max_length=10,
            ),
        ),
    ]
