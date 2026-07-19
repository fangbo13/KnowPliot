import datetime

import apps.spaces.models
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


SOURCE_TRIGGER_FUNCTION = "spaces_check_access_request_source_shape"


def backfill_join_v2_provenance(apps, schema_editor):
    """Preserve legacy rows as discovery-origin requests without guessing a code."""

    SpaceAccessRequest = apps.get_model("spaces", "SpaceAccessRequest")
    SpaceMembership = apps.get_model("spaces", "SpaceMembership")
    rows = []
    for request in SpaceAccessRequest.objects.all().iterator(chunk_size=500):
        request.source_kind = "discovery"
        request.discovery_policy_version = 1
        request.access_code_id = None
        request.access_code_version = None
        request.role_ceiling = request.role
        request.request_version = 1
        request.expires_at = request.created_at + datetime.timedelta(days=14)
        rows.append(request)
        if len(rows) == 500:
            SpaceAccessRequest.objects.bulk_update(
                rows,
                [
                    "source_kind",
                    "discovery_policy_version",
                    "access_code",
                    "access_code_version",
                    "role_ceiling",
                    "request_version",
                    "expires_at",
                ],
            )
            rows = []
    if rows:
        SpaceAccessRequest.objects.bulk_update(
            rows,
            [
                "source_kind",
                "discovery_policy_version",
                "access_code",
                "access_code_version",
                "role_ceiling",
                "request_version",
                "expires_at",
            ],
        )

    SpaceMembership.objects.filter(role="owner").update(source_kind="ownership")
    SpaceMembership.objects.exclude(role="owner").update(source_kind="legacy")


def install_postgresql_source_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        f"""
        CREATE OR REPLACE FUNCTION {SOURCE_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.source_kind = 'access_code' THEN
                IF NEW.access_code_id IS NULL
                   OR NEW.access_code_version IS NULL
                   OR NEW.discovery_policy_version IS NOT NULL THEN
                    RAISE EXCEPTION USING ERRCODE = '23514',
                        MESSAGE = 'access-code request source shape is invalid for request ' || NEW.id::text;
                END IF;
            ELSIF NEW.source_kind = 'discovery' THEN
                IF NEW.access_code_id IS NOT NULL
                   OR NEW.access_code_version IS NOT NULL
                   OR NEW.discovery_policy_version IS NULL THEN
                    RAISE EXCEPTION USING ERRCODE = '23514',
                        MESSAGE = 'discovery request source shape is invalid for request ' || NEW.id::text;
                END IF;
            ELSE
                RAISE EXCEPTION USING ERRCODE = '23514',
                    MESSAGE = 'unknown access-request source for request ' || NEW.id::text;
            END IF;
            RETURN NULL;
        END;
        $$;
        """
    )
    schema_editor.execute(
        f"""
        CREATE CONSTRAINT TRIGGER spaces_access_request_source_guard
        AFTER INSERT OR UPDATE ON spaces_spaceaccessrequest
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION {SOURCE_TRIGGER_FUNCTION}();
        """
    )


def remove_postgresql_source_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS spaces_access_request_source_guard "
        "ON spaces_spaceaccessrequest;"
    )
    schema_editor.execute(f"DROP FUNCTION IF EXISTS {SOURCE_TRIGGER_FUNCTION}();")


class Migration(migrations.Migration):
    dependencies = [
        ("spaces", "0013_governed_workspace_requests"),
        ("users", "0005_test_principal_metadata"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SpaceAccessCode",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("secret_hash", models.CharField(max_length=64, unique=True)),
                ("pepper_version", models.PositiveSmallIntegerField(default=1)),
                ("display_prefix", models.CharField(max_length=12)),
                ("role_ceiling", models.CharField(choices=[("member", "Member"), ("guest", "Guest")], default="member", max_length=20)),
                ("max_uses", models.PositiveIntegerField()),
                ("used_count", models.PositiveIntegerField(default=0)),
                ("max_pending", models.PositiveIntegerField()),
                ("pending_count", models.PositiveIntegerField(default=0)),
                ("policy_version", models.PositiveBigIntegerField(default=1)),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("status", models.CharField(choices=[("active", "Active"), ("revoked", "Revoked"), ("expired", "Expired")], default="active", max_length=12)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="space_access_codes_created", to=settings.AUTH_USER_MODEL)),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="access_codes_v2", to="spaces.knowledgespace")),
            ],
            options={"db_table": "spaces_spaceaccesscode", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SpaceInvitation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("inviter_uuid", models.UUIDField()),
                ("target_user_uuid", models.UUIDField(blank=True, null=True)),
                ("target_email_hmac", models.CharField(blank=True, default="", max_length=64)),
                ("encrypted_delivery_address", models.TextField(blank=True, default="")),
                ("target_key", models.CharField(max_length=140)),
                ("role", models.CharField(choices=[("knowledge_admin", "Knowledge Admin"), ("reviewer", "Reviewer"), ("member", "Member"), ("guest", "Guest")], max_length=20)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("token_pepper_version", models.PositiveSmallIntegerField(default=1)),
                ("token_prefix", models.CharField(max_length=12)),
                ("policy_version", models.PositiveBigIntegerField(default=1)),
                ("ownership_version", models.PositiveBigIntegerField()),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("accepted", "Accepted"), ("declined", "Declined"), ("expired", "Expired"), ("revoked", "Revoked"), ("invalidated", "Invalidated")], default="pending", max_length=16)),
                ("expires_at", models.DateTimeField()),
                ("responded_at", models.DateTimeField(blank=True, null=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("resulting_membership_uuid", models.UUIDField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("inviter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="targeted_space_invitations_sent", to=settings.AUTH_USER_MODEL)),
                ("responded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="targeted_space_invitations_responded", to=settings.AUTH_USER_MODEL)),
                ("space", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="targeted_invitations", to="spaces.knowledgespace")),
                ("target_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="targeted_space_invitations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "spaces_spaceinvitation", "ordering": ["-created_at"]},
        ),
        migrations.RemoveConstraint(
            model_name="spaceaccessrequest",
            name="spaces_access_request_unique_status",
        ),
        migrations.AddField(
            model_name="invitecode",
            name="compatibility_kind",
            field=models.CharField(default="legacy_invitation_code", editable=False, max_length=32),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="access_code_version",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="decision_reason_code",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="decision_reason_text",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="discovery_policy_version",
            field=models.PositiveBigIntegerField(blank=True, default=1, null=True),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="request_version",
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="resulting_membership_uuid",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="role_ceiling",
            field=models.CharField(choices=[("member", "Member"), ("guest", "Guest")], default="member", max_length=20),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="source_kind",
            field=models.CharField(choices=[("access_code", "Access Code"), ("discovery", "Discovery")], default="discovery", max_length=20),
        ),
        migrations.AddField(
            model_name="spacemembership",
            name="membership_version",
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="spacemembership",
            name="source_kind",
            field=models.CharField(choices=[("legacy", "Legacy"), ("manual", "Manual"), ("access_request", "Access Request"), ("invitation", "Invitation"), ("ownership", "Ownership")], default="legacy", max_length=20),
        ),
        migrations.AlterField(
            model_name="invitecode",
            name="role",
            field=models.CharField(choices=[("member", "Member"), ("guest", "Guest")], default="member", max_length=20),
        ),
        migrations.AlterField(
            model_name="spaceaccessrequest",
            name="reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AlterField(
            model_name="spaceaccessrequest",
            name="rejection_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AlterField(
            model_name="spaceaccessrequest",
            name="status",
            field=models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled"), ("expired", "Expired"), ("invalidated", "Invalidated")], default="pending", max_length=20),
        ),
        migrations.AddField(
            model_name="spaceaccessrequest",
            name="access_code",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="access_requests", to="spaces.spaceaccesscode"),
        ),
        migrations.RunPython(backfill_join_v2_provenance, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="spaceaccessrequest",
            name="expires_at",
            field=models.DateTimeField(default=apps.spaces.models.default_access_request_expiry),
        ),
        migrations.AddConstraint(
            model_name="invitecode",
            constraint=models.CheckConstraint(check=models.Q(("role__in", ["member", "guest"])), name="spaces_legacy_invite_non_owner"),
        ),
        migrations.AddConstraint(
            model_name="spacemembership",
            constraint=models.CheckConstraint(check=models.Q(models.Q(("role", "owner"), _negated=True), ("invited_by__isnull", True), _connector="OR"), name="spaces_owner_membership_not_invited"),
        ),
        migrations.AddConstraint(
            model_name="spaceaccessrequest",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "pending")), fields=("space", "user"), name="spaces_one_pending_access_request"),
        ),
        migrations.AddConstraint(
            model_name="spaceaccessrequest",
            constraint=models.CheckConstraint(check=models.Q(("role__in", ["member", "guest"]), ("role_ceiling__in", ["member", "guest"]), models.Q(models.Q(("role_ceiling", "guest"), _negated=True), ("role", "guest"), _connector="OR")), name="spaces_access_request_role_ceiling"),
        ),
        migrations.AddConstraint(
            model_name="spaceaccessrequest",
            constraint=models.CheckConstraint(check=models.Q(models.Q(("source_kind", "access_code"), ("access_code__isnull", False), ("access_code_version__isnull", False), ("discovery_policy_version__isnull", True)), models.Q(("source_kind", "discovery"), ("access_code__isnull", True), ("access_code_version__isnull", True), ("discovery_policy_version__isnull", False)), _connector="OR"), name="spaces_access_request_source_shape"),
        ),
        migrations.AddIndex(
            model_name="spaceaccesscode",
            index=models.Index(fields=["space", "status", "expires_at"], name="spaces_access_code_state"),
        ),
        migrations.AddConstraint(
            model_name="spaceaccesscode",
            constraint=models.CheckConstraint(check=models.Q(("secret_hash__regex", "^[0-9a-f]{64}$")), name="spaces_access_code_hash_shape"),
        ),
        migrations.AddConstraint(
            model_name="spaceaccesscode",
            constraint=models.CheckConstraint(check=models.Q(("role_ceiling__in", ["member", "guest"])), name="spaces_access_code_role_ceiling"),
        ),
        migrations.AddConstraint(
            model_name="spaceaccesscode",
            constraint=models.CheckConstraint(check=models.Q(("pepper_version__gte", 1), models.Q(("display_prefix", ""), _negated=True)), name="spaces_access_code_key_evidence"),
        ),
        migrations.AddConstraint(
            model_name="spaceaccesscode",
            constraint=models.CheckConstraint(check=models.Q(("max_uses__gte", 1), ("used_count__lte", models.F("max_uses"))), name="spaces_access_code_use_ceiling"),
        ),
        migrations.AddConstraint(
            model_name="spaceaccesscode",
            constraint=models.CheckConstraint(check=models.Q(("max_pending__gte", 1), ("pending_count__lte", models.F("max_pending"))), name="spaces_access_code_pending_ceiling"),
        ),
        migrations.AddIndex(
            model_name="spaceinvitation",
            index=models.Index(fields=["space", "status", "expires_at"], name="spaces_invitation_state"),
        ),
        migrations.AddIndex(
            model_name="spaceinvitation",
            index=models.Index(fields=["target_key", "status"], name="spaces_invitation_target"),
        ),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "pending")), fields=("space", "target_key"), name="spaces_one_pending_target_invite"),
        ),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.CheckConstraint(check=models.Q(("token_hash__regex", "^[0-9a-f]{64}$")), name="spaces_invitation_token_hash_shape"),
        ),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.CheckConstraint(check=models.Q(("token_pepper_version__gte", 1), models.Q(("token_prefix", ""), _negated=True)), name="spaces_invitation_key_evidence"),
        ),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.CheckConstraint(check=models.Q(("role__in", ["knowledge_admin", "reviewer", "member", "guest"])), name="spaces_invitation_non_owner_role"),
        ),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.CheckConstraint(check=models.Q(models.Q(("target_user__isnull", False), ("target_user_uuid__isnull", False), ("target_user_uuid", models.F("target_user")), ("target_email_hmac", ""), ("encrypted_delivery_address", ""), ("target_key__startswith", "user:")), models.Q(("target_user__isnull", True), ("target_user_uuid__isnull", True), ("target_email_hmac__regex", "^[0-9a-f]{64}$"), models.Q(("encrypted_delivery_address", ""), _negated=True), ("target_key__startswith", "email:")), _connector="OR"), name="spaces_invitation_target_shape"),
        ),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.CheckConstraint(check=models.Q(("inviter__isnull", True), ("inviter_uuid", models.F("inviter")), _connector="OR"), name="spaces_invitation_inviter_snapshot"),
        ),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.CheckConstraint(check=models.Q(models.Q(("status__in", ["accepted", "declined"]), _negated=True), models.Q(("responded_at__isnull", False), ("consumed_at__isnull", False)), _connector="OR"), name="spaces_invitation_response_evidence"),
        ),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.CheckConstraint(check=models.Q(models.Q(("status", "accepted"), _negated=True), ("resulting_membership_uuid__isnull", False), _connector="OR"), name="spaces_invitation_accept_membership"),
        ),
        migrations.RunPython(
            install_postgresql_source_trigger,
            remove_postgresql_source_trigger,
        ),
    ]
