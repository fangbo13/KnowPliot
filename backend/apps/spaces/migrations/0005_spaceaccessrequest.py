import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("spaces", "0004_adminregistrationcode_spaceemailinvite")]

    operations = [
        migrations.CreateModel(
            name="SpaceAccessRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("role", models.CharField(choices=[("member", "Member"), ("guest", "Guest")], default="member", max_length=20)),
                ("reason", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending", max_length=20)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_space_access_requests", to=settings.AUTH_USER_MODEL)),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="access_requests", to="spaces.knowledgespace")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="space_access_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "spaces_spaceaccessrequest", "ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="spaceaccessrequest",
            constraint=models.UniqueConstraint(fields=("space", "user", "status"), name="spaces_access_request_unique_status"),
        ),
    ]
