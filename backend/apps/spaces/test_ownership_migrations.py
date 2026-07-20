import importlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class OwnershipStageCMigrationTests(TransactionTestCase):
    migrate_from = ("spaces", "0009_ownership_continuity_stage_a")
    migrate_to = ("spaces", "0010_ownership_continuity_stage_c")
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

    def _user(self, username):
        User = self.old_apps.get_model("users", "User")
        return User.objects.create(username=username, email=f"{username}@example.test", is_active=True)

    def _space(self, code):
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        organization, _ = Organization.objects.get_or_create(
            slug="migration-owner-org",
            defaults={"name": "Migration Owner Org", "status": "active"},
        )
        return KnowledgeSpace.objects.create(
            organization=organization,
            name=code,
            code=code,
            status="active",
            owner=None,
        )

    def _owner_mirror(self, space, user):
        SpaceMembership = self.old_apps.get_model("spaces", "SpaceMembership")
        return SpaceMembership.objects.create(
            space=space,
            user=user,
            role="owner",
            status="active",
            expires_at=None,
        )

    def test_stage_c_backfills_exactly_one_eligible_owner_before_non_null(self):
        owner = self._user("migration-owner")
        space = self._space("migration-owned")
        self._owner_mirror(space, owner)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to, self.users_target])
        migrated_apps = executor.loader.project_state(
            [self.migrate_to, self.users_target]
        ).apps
        migrated_space = migrated_apps.get_model("spaces", "KnowledgeSpace").objects.get(
            pk=space.pk
        )

        self.assertEqual(migrated_space.owner_id, owner.pk)

    def test_stage_c_fails_closed_for_zero_or_multiple_eligible_owners(self):
        zero_owner_space = self._space("migration-zero-owner")
        ambiguous_space = self._space("migration-two-owners")
        first = self._user("migration-first-owner")
        second = self._user("migration-second-owner")
        self._owner_mirror(ambiguous_space, first)
        second_mirror = self._owner_mirror(ambiguous_space, second)
        migration_module = importlib.import_module(
            "apps.spaces.migrations.0010_ownership_continuity_stage_c"
        )

        # backfill_canonical_owners only uses schema_editor.connection.alias
        # (it does data .update() only, NO DDL). connection.schema_editor()
        # inherits the connection's pending deferred-constraint state (left by
        # a prior app's TransactionTestCase in multi-app runs) and hangs.
        # Pass a minimal schema_editor-like object exposing .connection,
        # running backfill in autocommit (no schema_editor setup) to avoid
        # the inherited deferred-state hang.
        class _MinimalSchemaEditor:
            def __init__(self, conn):
                self.connection = conn

        with self.assertRaisesRegex(
            RuntimeError,
            "ownership_continuity_stage_c_blocked",
        ):
            migration_module.backfill_canonical_owners(
                self.old_apps, _MinimalSchemaEditor(connection)
            )

        zero_owner_space.refresh_from_db()
        ambiguous_space.refresh_from_db()
        self.assertIsNone(zero_owner_space.owner_id)
        self.assertIsNone(ambiguous_space.owner_id)

        # Restore an eligible migration state so tearDown can return the shared
        # test schema to the latest leaf migrations.
        zero_owner_space.delete()
        second_mirror.delete()

