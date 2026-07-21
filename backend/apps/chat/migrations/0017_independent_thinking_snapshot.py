from django.db import migrations, models
from django.db.models import F, Q


def mark_historical_thinking_unknown(apps, schema_editor):
    ChatTurn = apps.get_model("chat", "ChatTurn")
    ChatTurn.objects.update(
        requested_answer_mode=F("answer_mode"),
        requested_thinking_enabled=False,
        thinking_enabled=False,
        thinking_snapshot_known=False,
        thinking_budget=None,
        policy_fallback_code="legacy_thinking_unknown",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0016_conversation_share"),
        ("spaces", "0011_ownership_invariant_hardening"),
        ("users", "0005_test_principal_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatturn",
            name="requested_answer_mode",
            field=models.CharField(
                choices=[("fast", "Fast"), ("deep", "Deep")],
                default="fast",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="chatturn",
            name="requested_thinking_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="chatturn",
            name="thinking_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="chatturn",
            name="thinking_snapshot_known",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="chatturn",
            name="thinking_budget",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="chatturn",
            name="policy_fallback_code",
            field=models.CharField(
                blank=True,
                default="legacy_thinking_unknown",
                max_length=64,
            ),
        ),
        migrations.RunPython(
            mark_historical_thinking_unknown,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="chatturn",
            name="thinking_snapshot_known",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="chatturn",
            name="policy_fallback_code",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddConstraint(
            model_name="chatturn",
            constraint=models.CheckConstraint(
                check=(
                    Q(
                        thinking_snapshot_known=False,
                        requested_thinking_enabled=False,
                        thinking_enabled=False,
                        thinking_budget__isnull=True,
                        policy_fallback_code="legacy_thinking_unknown",
                    )
                    | Q(
                        thinking_snapshot_known=True,
                        thinking_enabled=False,
                        thinking_budget__isnull=True,
                    )
                    | Q(
                        thinking_snapshot_known=True,
                        thinking_enabled=True,
                        thinking_budget__gte=1,
                        thinking_budget__lte=32768,
                    )
                ),
                name="chat_turn_thinking_snapshot_ck",
            ),
        ),
    ]
