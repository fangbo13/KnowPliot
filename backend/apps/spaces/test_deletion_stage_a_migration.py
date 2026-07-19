"""Migration contract for workspace-deletion Stage A persistence."""

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class WorkspaceDeletionStageAMigrationTests(TransactionTestCase):
    serialized_rollback = True
    migrate_from = ("spaces", "0014_workspace_join_v2")
    migrate_to = ("spaces", "0015_workspace_deletion_stage_a")
    users_target = ("users", "0005_test_principal_metadata")
    notifications_target = (
        "notifications",
        "0003_actionable_notification_contract",
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

    def test_stage_a_backfills_snapshots_and_seeds_fail_closed_registry(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        GovernancePolicy = self.old_apps.get_model("spaces", "GovernancePolicy")

        owner = User.objects.create(
            username="deletion-stage-a-owner",
            email="deletion-stage-a-owner@example.test",
            is_active=True,
            test_run_id="",
        )
        organization = Organization.objects.create(
            name="Deletion Stage A org",
            slug="deletion-stage-a-org",
            status="active",
        )
        space = KnowledgeSpace.objects.create(
            organization=organization,
            owner=owner,
            name="Historical archived workspace",
            code="historical-archived-workspace",
            status="archived",
        )
        policy = GovernancePolicy.objects.create(
            organization=organization,
            space=space,
            revision=1,
            values={"retention_days": 30},
        )
        archived_updated_at = space.updated_at

        executor = MigrationExecutor(connection)
        executor.migrate(
            [self.migrate_to, self.users_target, self.notifications_target]
        )
        migrated_apps = executor.loader.project_state(
            [self.migrate_to, self.users_target, self.notifications_target]
        ).apps
        MigratedSpace = migrated_apps.get_model("spaces", "KnowledgeSpace")
        MigratedPolicy = migrated_apps.get_model("spaces", "GovernancePolicy")
        Registry = migrated_apps.get_model("spaces", "WorkspacePurgeDependency")

        migrated_space = MigratedSpace.objects.get(pk=space.pk)
        self.assertEqual(migrated_space.archived_at, archived_updated_at)
        self.assertEqual(migrated_space.retention_policy_version, 1)
        self.assertEqual(migrated_space.storage_manifest_version, 0)
        self.assertEqual(migrated_space.storage_manifest_digest, "")
        self.assertEqual(migrated_space.purge_fence_generation, 0)

        migrated_policy = MigratedPolicy.objects.get(pk=policy.pk)
        self.assertEqual(migrated_policy.space_uuid, space.pk)
        self.assertEqual(migrated_policy.organization_uuid, organization.pk)

        self.assertEqual(Registry.objects.count(), 36)
        self.assertEqual(
            Registry.objects.filter(registration_state="ready").count(),
            16,
        )
        self.assertEqual(
            Registry.objects.filter(registration_state="pending").count(),
            20,
        )
        self.assertTrue(
            Registry.objects.filter(
                model_label="spaces.OwnershipTransfer",
                registration_state="pending",
                migration_owner="spaces.0016_workspace_deletion_stage_c",
            ).exists()
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MigratedSpace.objects.filter(pk=space.pk).update(
                    storage_manifest_version=1,
                    storage_manifest_digest="not-a-sha256",
                    storage_manifest_generated_at=timezone.now(),
                )

        migrated_space.delete()
        migrated_policy.refresh_from_db()
        self.assertIsNone(migrated_policy.space_id)
        self.assertEqual(migrated_policy.space_uuid, space.pk)
        self.assertEqual(migrated_policy.organization_uuid, organization.pk)
        # This test intentionally creates/deletes a post-0013 workspace without
        # its canonical locator to isolate the Stage-A SET_NULL behavior. Do not
        # leave that synthetic, unprovable row for tearDown's Stage-C forward
        # migration, whose strict locator-evidence constraint must reject it.
        migrated_policy.delete()
