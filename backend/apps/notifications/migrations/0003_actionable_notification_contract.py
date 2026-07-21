from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_notification_notif_rec_type_read_cr_idx"),
        ("spaces", "0014_workspace_join_v2"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="action_kind",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="notification",
            name="action_state",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("available", "Available"),
                    ("actioned", "Actioned"),
                    ("stale", "Stale"),
                ],
                default="none",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="actioned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="allowed_actions",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="notification",
            name="deep_link",
            field=models.CharField(blank=True, default="", max_length=300),
        ),
        migrations.AddField(
            model_name="notification",
            name="resource_type",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="notification",
            name="resource_uuid",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="resource_version",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="notification",
            name="type",
            field=models.CharField(
                choices=[
                    ("welcome", "Welcome"),
                    ("space_invite", "Space Invite"),
                    ("role_granted", "Role Granted"),
                    ("document_review", "Document Review"),
                    ("space_invitation", "Space Invitation"),
                    ("space_access_request", "Space Access Request"),
                    ("account", "Account"),
                    ("system_broadcast", "System"),
                ],
                default="account",
                max_length=30,
            ),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["recipient", "action_state", "created_at"],
                name="notif_rec_action_state_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["resource_type", "resource_uuid"],
                name="notif_resource_lookup_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("action_kind", ""),
                        ("resource_type", ""),
                        ("resource_uuid__isnull", True),
                        ("action_state", "none"),
                        ("deep_link", ""),
                    ),
                    models.Q(
                        models.Q(
                            ("action_kind__in", ["", "resource_deleted"]),
                            _negated=True,
                        ),
                        models.Q(("resource_type", ""), _negated=True),
                        ("resource_uuid__isnull", False),
                        ("action_state__in", ["available", "actioned", "stale"]),
                        ("deep_link__startswith", "/"),
                        models.Q(("deep_link__startswith", "//"), _negated=True),
                    ),
                    models.Q(
                        ("action_kind", "resource_deleted"),
                        models.Q(("resource_type", ""), _negated=True),
                        ("resource_uuid__isnull", False),
                        ("action_state", "stale"),
                        ("allowed_actions", []),
                        ("deep_link", ""),
                    ),
                    _connector="OR",
                ),
                name="notif_actionable_resource_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("action_state", "actioned"), _negated=True),
                    ("actioned_at__isnull", False),
                    _connector="OR",
                ),
                name="notif_actioned_has_timestamp",
            ),
        ),
    ]
