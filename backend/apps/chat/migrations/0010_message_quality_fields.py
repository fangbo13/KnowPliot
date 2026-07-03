# Generated for Phase 8A / V10.0.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0009_complianceexportjob_retry_of"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="confidence_label",
            field=models.CharField(
                blank=True,
                choices=[
                    ("high", "High"),
                    ("medium", "Medium"),
                    ("low", "Low"),
                    ("insufficient", "Insufficient"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="message",
            name="confidence_score",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="needs_human_review",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="message",
            name="retrieval_latency_ms",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="retrieval_mode",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
