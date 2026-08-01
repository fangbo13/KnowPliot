from django.db import migrations, models
from django.utils import timezone


def migrate_roles_and_onboarding(apps, schema_editor):
    SpaceMembership = apps.get_model("spaces", "SpaceMembership")
    SpaceInvitation = apps.get_model("spaces", "SpaceInvitation")
    SpaceEmailInvite = apps.get_model("spaces", "SpaceEmailInvite")
    InviteCode = apps.get_model("spaces", "InviteCode")
    SpaceAccessCode = apps.get_model("spaces", "SpaceAccessCode")
    SpaceAccessRequest = apps.get_model("spaces", "SpaceAccessRequest")

    SpaceMembership.objects.filter(role__in=["reviewer", "knowledge_admin"]).update(role="space_admin")
    SpaceMembership.objects.filter(role__in=["owner", "space_admin", "member"]).update(
        onboarding_completed_at=timezone.now()
    )
    # Credentials and pending entry offers are never a privilege-escalation
    # mechanism. Existing rows converge to the new guest-first contract.
    SpaceInvitation.objects.exclude(role="guest").update(role="guest")
    SpaceEmailInvite.objects.exclude(role="guest").update(role="guest")
    InviteCode.objects.exclude(role="guest").update(role="guest")
    SpaceAccessCode.objects.exclude(role_ceiling="guest").update(role_ceiling="guest")
    SpaceAccessRequest.objects.exclude(role="guest").update(role="guest")
    SpaceAccessRequest.objects.exclude(role_ceiling="guest").update(role_ceiling="guest")


class Migration(migrations.Migration):
    dependencies = [("spaces", "0023_alter_review_policy_default")]

    operations = [
        migrations.AddField(
            model_name="spacemembership",
            name="onboarding_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(migrate_roles_and_onboarding, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="spacemembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("owner", "Space Owner"),
                    ("space_admin", "Space Admin"),
                    ("member", "Member"),
                    ("guest", "Guest"),
                ],
                default="guest",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="spaceemailinvite",
            name="role",
            field=models.CharField(choices=[("guest", "Guest")], default="guest", max_length=20),
        ),
        migrations.AlterField(
            model_name="invitecode",
            name="role",
            field=models.CharField(choices=[("guest", "Guest")], default="guest", max_length=20),
        ),
        migrations.RemoveConstraint(model_name="invitecode", name="spaces_legacy_invite_non_owner"),
        migrations.AddConstraint(
            model_name="invitecode",
            constraint=models.CheckConstraint(check=models.Q(("role", "guest")), name="spaces_legacy_invite_non_owner"),
        ),
        migrations.AlterField(
            model_name="spaceaccesscode",
            name="role_ceiling",
            field=models.CharField(choices=[("guest", "Guest")], default="guest", max_length=20),
        ),
        migrations.RemoveConstraint(model_name="spaceaccesscode", name="spaces_access_code_role_ceiling"),
        migrations.AddConstraint(
            model_name="spaceaccesscode",
            constraint=models.CheckConstraint(
                check=models.Q(("role_ceiling", "guest")), name="spaces_access_code_role_ceiling"
            ),
        ),
        migrations.AlterField(
            model_name="spaceinvitation",
            name="role",
            field=models.CharField(choices=[("guest", "Guest")], max_length=20),
        ),
        migrations.RemoveConstraint(model_name="spaceinvitation", name="spaces_invitation_non_owner_role"),
        migrations.AddConstraint(
            model_name="spaceinvitation",
            constraint=models.CheckConstraint(
                check=models.Q(("role", "guest")), name="spaces_invitation_non_owner_role"
            ),
        ),
        migrations.AlterField(
            model_name="spaceaccessrequest",
            name="role",
            field=models.CharField(choices=[("guest", "Guest")], default="guest", max_length=20),
        ),
        migrations.AlterField(
            model_name="spaceaccessrequest",
            name="role_ceiling",
            field=models.CharField(choices=[("guest", "Guest")], default="guest", max_length=20),
        ),
        migrations.RemoveConstraint(model_name="spaceaccessrequest", name="spaces_access_request_role_ceiling"),
        migrations.AddConstraint(
            model_name="spaceaccessrequest",
            constraint=models.CheckConstraint(
                check=models.Q(("role", "guest"), ("role_ceiling", "guest")),
                name="spaces_access_request_role_ceiling",
            ),
        ),
    ]
