import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("spaces", "0004_adminregistrationcode_spaceemailinvite"),
        ("users", "0002_alter_user_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="theme_preference",
            field=models.CharField(
                choices=[("system", "System"), ("light", "Light"), ("dark", "Dark")],
                default="system",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="default_space",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="default_for_users",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="notification_preferences",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="user",
            name="mfa_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="mfa_secret",
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="mfa_pending_secret",
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="mfa_recovery_codes",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="AuthSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("refresh_jti", models.CharField(max_length=255, unique=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="auth_sessions", to="users.user")),
            ],
            options={
                "db_table": "users_auth_session",
                "ordering": ["-last_seen_at"],
            },
        ),
        migrations.AddIndex(
            model_name="authsession",
            index=models.Index(fields=["user", "revoked_at", "-last_seen_at"], name="users_auth__user_id_e798d6_idx"),
        ),
    ]
