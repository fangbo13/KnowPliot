from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat", "0011_ragevaluationrun")]

    operations = [
        migrations.AddField(
            model_name="chatsession",
            name="is_pinned",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
