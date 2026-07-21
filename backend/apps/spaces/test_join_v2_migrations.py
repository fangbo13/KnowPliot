"""Migration contract for join-v2 compatibility provenance/backfills."""

from datetime import timedelta

from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class JoinV2MigrationContractTests(TransactionTestCase):
    migrate_from = ("spaces", "0013_governed_workspace_requests")
    migrate_to = ("spaces", "0014_workspace_join_v2")
    users_target = ("users", "0005_test_principal_metadata")
    notifications_target = (
        "notifications",
        "0002_notification_notif_rec_type_read_cr_idx",
    )

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(
            [self.migrate_from, self.users_target, self.notifications_target]
        )
        self.old_apps = executor.loader.project_state(
            [self.migrate_from, self.users_target, self.notifications_target]
        ).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_legacy_rows_receive_safe_join_v2_provenance_and_versions(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        SpaceMembership = self.old_apps.get_model("spaces", "SpaceMembership")
        SpaceAccessRequest = self.old_apps.get_model("spaces", "SpaceAccessRequest")
        InviteCode = self.old_apps.get_model("spaces", "InviteCode")

        owner = User.objects.create(
            username="join-migration-owner",
            email="join-migration-owner@example.test",
            is_active=True,
            test_run_id="",
        )
        member = User.objects.create(
            username="join-migration-member",
            email="join-migration-member@example.test",
            is_active=True,
            test_run_id="",
        )
        organization = Organization.objects.create(
            name="Join migration org",
            slug="join-migration-org",
            status="active",
        )
        # The 0011 owner-mirror deferred constraint trigger fires at commit and
        # requires a consistent owner mirror; wrap the full legacy-row seed
        # (space, memberships, access request, invite) in one atomic block so
        # the trigger fires once at commit after all rows exist, and the
        # subsequent forward migration's ALTER TABLE does not hit pending
        # deferred trigger events.
        with transaction.atomic():
            space = KnowledgeSpace.objects.create(
                organization=organization,
                owner=owner,
                name="Join migration space",
                code="join-migration-space",
                status="active",
            )
            owner_membership = SpaceMembership.objects.create(
                space=space,
                user=owner,
                role="owner",
                status="active",
                expires_at=None,
            )
            member_membership = SpaceMembership.objects.create(
                space=space,
                user=member,
                role="member",
                status="active",
            )
            access_request = SpaceAccessRequest.objects.create(
                space=space,
                user=member,
                role="guest",
                reason="legacy discovery request",
                status="pending",
            )
            invite = InviteCode.objects.create(
                space=space,
                code_hash="a" * 64,
                role="member",
                status="active",
            )

        executor = MigrationExecutor(connection)
        executor.migrate(
            [self.migrate_to, self.users_target, self.notifications_target]
        )
        migrated_apps = executor.loader.project_state(
            [self.migrate_to, self.users_target, self.notifications_target]
        ).apps
        MigratedRequest = migrated_apps.get_model("spaces", "SpaceAccessRequest")
        MigratedMembership = migrated_apps.get_model("spaces", "SpaceMembership")
        MigratedInviteCode = migrated_apps.get_model("spaces", "InviteCode")

        migrated_request = MigratedRequest.objects.get(pk=access_request.pk)
        self.assertEqual(migrated_request.source_kind, "discovery")
        self.assertEqual(migrated_request.discovery_policy_version, 1)
        self.assertIsNone(migrated_request.access_code_id)
        self.assertEqual(migrated_request.role_ceiling, "guest")
        self.assertEqual(migrated_request.request_version, 1)
        self.assertEqual(
            migrated_request.expires_at - migrated_request.created_at,
            timedelta(days=14),
        )

        self.assertEqual(
            MigratedMembership.objects.get(pk=owner_membership.pk).source_kind,
            "ownership",
        )
        self.assertEqual(
            MigratedMembership.objects.get(pk=member_membership.pk).source_kind,
            "legacy",
        )
        self.assertEqual(
            MigratedMembership.objects.get(pk=member_membership.pk).membership_version,
            1,
        )
        self.assertEqual(
            MigratedInviteCode.objects.get(pk=invite.pk).compatibility_kind,
            "legacy_invitation_code",
        )
