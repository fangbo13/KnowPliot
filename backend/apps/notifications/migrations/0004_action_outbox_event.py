import django.utils.timezone
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0003_actionable_notification_contract")]

    operations = [
        migrations.CreateModel(
            name="ActionOutboxEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("aggregate_type", models.CharField(max_length=48)),
                ("aggregate_uuid", models.UUIDField()),
                ("transition", models.CharField(max_length=48)),
                ("transition_version", models.PositiveBigIntegerField()),
                ("recipient_key", models.CharField(max_length=96)),
                ("payload", models.JSONField(default=dict)),
                ("payload_digest", models.CharField(max_length=64)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("delivering", "Delivering"),
                            ("delivered", "Delivered"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                (
                    "next_attempt_at",
                    models.DateTimeField(
                        blank=True,
                        default=django.utils.timezone.now,
                        null=True,
                    ),
                ),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "notifications_actionoutboxevent",
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["state", "next_attempt_at", "created_at"],
                        name="notif_outbox_due_idx",
                    ),
                    models.Index(
                        fields=["aggregate_type", "aggregate_uuid"],
                        name="notif_outbox_aggregate_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "aggregate_type",
                            "aggregate_uuid",
                            "transition",
                            "transition_version",
                            "recipient_key",
                        ),
                        name="notif_outbox_transition_recipient_uniq",
                    ),
                    models.CheckConstraint(
                        check=models.Q(
                            ("state__in", ["pending", "delivering", "delivered", "failed"])
                        ),
                        name="notif_outbox_state_valid",
                    ),
                    models.CheckConstraint(
                        check=(
                            models.Q(("delivered_at__isnull", False), ("state", "delivered"))
                            | (
                                ~models.Q(("state", "delivered"))
                                & models.Q(("delivered_at__isnull", True))
                            )
                        ),
                        name="notif_outbox_delivered_has_time",
                    ),
                ],
            },
        )
    ]
