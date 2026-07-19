"""Migration contract proving historical taxonomy is never guessed."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TaxonomyMigrationContractTests(TransactionTestCase):
    migrate_from = ("spaces", "0011_ownership_invariant_hardening")
    migrate_to = ("spaces", "0012_internal_beta_taxonomy")
    users_target = ("users", "0004_user_offboarding_metadata")

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

    def test_historical_space_is_marked_legacy_without_name_or_tag_inference(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        user = User.objects.create(
            username="taxonomy-migration-owner",
            email="taxonomy-migration-owner@example.test",
            is_active=True,
        )
        organization = Organization.objects.create(
            name="Migration taxonomy org",
            slug="migration-taxonomy-org",
            status="active",
        )
        space = KnowledgeSpace.objects.create(
            organization=organization,
            name="Assurance Group 12345 (legacy label)",
            code="taxonomy-migration-space",
            description="free-form group tag must not be parsed",
            owner=user,
            status="active",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        migrated_apps = executor.loader.project_state([self.migrate_to]).apps
        migrated_space = migrated_apps.get_model("spaces", "KnowledgeSpace").objects.get(
            pk=space.pk
        )

        self.assertEqual(migrated_space.classification_state, "legacy_unclassified")
        self.assertIsNone(migrated_space.work_group_id)
