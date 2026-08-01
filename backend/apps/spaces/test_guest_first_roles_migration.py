"""Migration contract for canonical guest-first workspace roles."""

from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class GuestFirstRolesMigrationContractTests(TransactionTestCase):
    migrate_from = ("spaces", "0023_alter_review_policy_default")
    migrate_to = ("spaces", "0024_guest_first_roles_and_onboarding")
    users_target = ("users", "0005_test_principal_metadata")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from, self.users_target])
        self.old_apps = executor.loader.project_state(
            [self.migrate_from, self.users_target]
        ).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
        super().tearDown()

    def test_migration_converges_legacy_roles_and_marks_preexisting_members(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        SpaceMembership = self.old_apps.get_model("spaces", "SpaceMembership")
        users = {
            role: User.objects.create(
                username=f"migration-{role}",
                email=f"migration-{role}@example.test",
                is_active=True,
                test_run_id="",
            )
            for role in ("owner", "reviewer", "knowledge_admin", "member", "guest")
        }
        organization = Organization.objects.create(
            name="Guest-first migration org", slug="guest-first-migration-org"
        )
        with transaction.atomic():
            space = KnowledgeSpace.objects.create(
                organization=organization,
                owner=users["owner"],
                name="Guest-first migration space",
                code="guest-first-migration-space",
                join_code="GUEST-FIRST-MIGRATION",
            )
            rows = {
                role: SpaceMembership.objects.create(
                    space=space,
                    user=user,
                    role=role,
                    status="active",
                )
                for role, user in users.items()
            }

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to, self.users_target])
        apps = executor.loader.project_state([self.migrate_to, self.users_target]).apps
        membership_model = apps.get_model("spaces", "SpaceMembership")

        self.assertEqual(membership_model.objects.get(pk=rows["reviewer"].pk).role, "space_admin")
        self.assertEqual(membership_model.objects.get(pk=rows["knowledge_admin"].pk).role, "space_admin")
        for role in ("owner", "reviewer", "knowledge_admin", "member"):
            with self.subTest(role=role):
                self.assertIsNotNone(
                    membership_model.objects.get(pk=rows[role].pk).onboarding_completed_at
                )
        self.assertIsNone(membership_model.objects.get(pk=rows["guest"].pk).onboarding_completed_at)
