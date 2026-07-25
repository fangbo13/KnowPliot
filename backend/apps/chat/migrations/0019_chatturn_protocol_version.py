from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0018_workspace_retention_contract"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatturn",
            name="protocol_version",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddConstraint(
            model_name="chatturn",
            constraint=models.CheckConstraint(
                check=models.Q(protocol_version__in=(1, 2, 3)),
                name="chat_turn_protocol_version_ck",
            ),
        ),
    ]
