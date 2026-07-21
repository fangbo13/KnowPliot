"""Migration contract for the governed-request foundation and locator backfill."""

from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class GovernedRequestMigrationContractTests(TransactionTestCase):
    migrate_from = ("spaces", "0012_internal_beta_taxonomy")
    migrate_to = ("spaces", "0013_governed_workspace_requests")
    users_target = ("users", "0005_test_principal_metadata")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from, self.users_target])
        self.old_apps = executor.loader.project_state(
            [self.migrate_from, self.users_target]
        ).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_space_gets_live_locator_and_initial_versions(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        SpaceMembership = self.old_apps.get_model("spaces", "SpaceMembership")
        user = User.objects.create(
            username="governed-migration-owner",
            email="governed-migration-owner@example.test",
            is_active=True,
            test_run_id="",
        )
        organization = Organization.objects.create(
            name="Governed migration org",
            slug="Migration_Org",
            status="active",
        )
        # The 0011 owner-mirror deferred constraint trigger fires at commit and
        # requires a matching active owner membership; wrap the space + mirror
        # insert in one atomic block so the trigger fires after both rows exist.
        with transaction.atomic():
            space = KnowledgeSpace.objects.create(
                organization=organization,
                name="Legacy locator space",
                code="Legacy_Code",
                owner=user,
                status="active",
            )
            SpaceMembership.objects.create(
                space=space,
                user=user,
                role="owner",
                status="active",
                expires_at=None,
            )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to, self.users_target])
        migrated_apps = executor.loader.project_state(
            [self.migrate_to, self.users_target]
        ).apps
        migrated_space = migrated_apps.get_model(
            "spaces", "KnowledgeSpace"
        ).objects.get(pk=space.pk)
        locator = migrated_apps.get_model(
            "spaces", "WorkspaceLocatorReservation"
        ).objects.get(live_space_id=space.pk)

        self.assertEqual(migrated_space.lifecycle_version, 1)
        self.assertEqual(migrated_space.dependency_version, 1)
        self.assertEqual(migrated_space.provisioning_status, "ready")
        self.assertEqual(locator.state, "live")
        self.assertEqual(locator.organization_id, organization.pk)
        self.assertEqual(locator.normalized_code, "legacy-code")
        self.assertEqual(locator.normalized_locator, "migration-org/legacy-code")

