from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat", "0013_chatturn")]

    operations = [
        migrations.AddField(
            model_name="chatturn",
            name="metrics",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="chatturn",
            name="model_id",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AlterField(
            model_name="message",
            name="model_used",
            field=models.CharField(blank=True, max_length=160, null=True),
        ),
        migrations.AlterField(
            model_name="modelinvocation",
            name="model",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
    ]
