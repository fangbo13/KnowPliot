from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0004_user_offboarding_metadata")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="account_purpose",
            field=models.CharField(
                blank=True,
                choices=[
                    ("test", "Automated test principal"),
                    ("service", "Service principal"),
                ],
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="test_principal_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="test_run_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
