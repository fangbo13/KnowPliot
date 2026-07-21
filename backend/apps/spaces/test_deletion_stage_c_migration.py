"""Migration contract for final workspace-deletion Stage C invariants."""

import hashlib
import importlib
import uuid
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class WorkspaceDeletionStageCMigrationTests(TransactionTestCase):
    # MigrationExecutor already rebuilds the PostgreSQL schema in this class.
    # Restoring Django's serialized baseline as well duplicates content types;
    # SQLite still needs the snapshot because flush removes migration-owned
    # registry rows between migration-contract classes.
    serialized_rollback = connection.vendor != "postgresql"
    migrate_from = ("spaces", "0015_workspace_deletion_stage_a")
    migrate_to = ("spaces", "0016_workspace_deletion_stage_c")
    audit_target = ("audit", "0015_workspace_retention_contract")
    users_target = ("users", "0005_test_principal_metadata")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        targets = [self.migrate_from, self.audit_target, self.users_target]
        executor.migrate(targets)
        self.old_apps = executor.loader.project_state(targets).apps
        if connection.vendor == "postgresql":
            # TransactionTestCase.flush removes data seeded by migrations.
            # Replaying Django's serialized baseline duplicates content types
            # on PostgreSQL, so restore only the migration-owned registry that
            # Stage C is explicitly meant to validate.
            Registry = self.old_apps.get_model("spaces", "WorkspacePurgeDependency")
            if not Registry.objects.exists():
                stage_a = importlib.import_module(
                    "apps.spaces.migrations.0015_workspace_deletion_stage_a"
                )
                stage_a.seed_purge_registry(self.old_apps, None)
                for module_name in (
                    "apps.knowledge.migrations.0011_workspace_retention_contract",
                    "apps.chat.migrations.0018_workspace_retention_contract",
                    "apps.scenario_templates.migrations.0007_workspace_retention_contract",
                    "apps.audit.migrations.0015_workspace_retention_contract",
                ):
                    importlib.import_module(module_name).mark_registry_ready(
                        self.old_apps,
                        None,
                    )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_final_registry_and_retained_space_evidence_are_complete(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        SpaceMembership = self.old_apps.get_model("spaces", "SpaceMembership")
        Locator = self.old_apps.get_model("spaces", "WorkspaceLocatorReservation")
        OwnershipTransfer = self.old_apps.get_model("spaces", "OwnershipTransfer")
        GovernancePolicy = self.old_apps.get_model("spaces", "GovernancePolicy")

        owner = User.objects.create(
            username="stage-c-owner",
            email="stage-c-owner@example.test",
            is_active=True,
            test_run_id="",
        )
        successor = User.objects.create(
            username="stage-c-successor",
            email="stage-c-successor@example.test",
            is_active=True,
            test_run_id="",
        )
        organization = Organization.objects.create(
            name="Stage C org",
            slug="stage-c-org",
            status="active",
        )
        with transaction.atomic():
            space = KnowledgeSpace.objects.create(
                organization=organization,
                owner=owner,
                name="Stage C workspace",
                code="stage-c-workspace",
                status="archived",
            )
            SpaceMembership.objects.create(
                space=space,
                user=owner,
                role="owner",
                status="active",
                expires_at=None,
            )
        User.objects.filter(pk=successor.pk).update(default_space_id=space.pk)
        locator_text = "stage-c-org/stage-c-workspace"
        locator_digest = hashlib.sha256(locator_text.encode()).hexdigest()
        locator = Locator.objects.create(
            organization=organization,
            normalized_code="stage-c-workspace",
            normalized_locator=locator_text,
            state="live",
            live_space=space,
        )
        transfer = OwnershipTransfer.objects.create(
            space=space,
            from_owner=owner,
            to_owner=successor,
            requested_by=owner,
            accepted_by=successor,
            mode="voluntary",
            status="completed",
            expected_ownership_version=1,
            reason_code="voluntary",
            reason_note="scrub on purge",
            idempotency_key=uuid.uuid4(),
            completed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        policy = GovernancePolicy.objects.create(
            organization=organization,
            space=space,
            revision=1,
            values={"retention_days": 30},
        )

        executor = MigrationExecutor(connection)
        targets = [self.migrate_to, self.audit_target, self.users_target]
        executor.migrate(targets)
        migrated_apps = executor.loader.project_state(targets).apps
        MigratedTransfer = migrated_apps.get_model("spaces", "OwnershipTransfer")
        MigratedPolicy = migrated_apps.get_model("spaces", "GovernancePolicy")
        MigratedLocator = migrated_apps.get_model(
            "spaces", "WorkspaceLocatorReservation"
        )
        MigratedSpace = migrated_apps.get_model("spaces", "KnowledgeSpace")
        MigratedUser = migrated_apps.get_model("users", "User")
        Registry = migrated_apps.get_model("spaces", "WorkspacePurgeDependency")

        migrated_transfer = MigratedTransfer.objects.get(pk=transfer.pk)
        self.assertEqual(migrated_transfer.space_uuid, space.pk)
        self.assertEqual(migrated_transfer.organization_uuid, organization.pk)
        self.assertEqual(migrated_transfer.locator_digest, locator_digest)
        migrated_policy = MigratedPolicy.objects.get(pk=policy.pk)
        self.assertEqual(migrated_policy.space_uuid, space.pk)
        self.assertEqual(migrated_policy.organization_uuid, organization.pk)
        self.assertEqual(migrated_policy.locator_digest, locator_digest)

        rows = Registry.objects.filter(required=True, active=True)
        self.assertEqual(rows.count(), 36)
        self.assertFalse(rows.exclude(registration_state="ready").exists())
        user_row = rows.get(model_label="users.User", space_field="default_space")
        self.assertEqual(user_row.snapshot_fields, [])
        self.assertEqual(user_row.scrub_fields, [])
        ownership_row = rows.get(model_label="spaces.OwnershipTransfer")
        self.assertIn("locator_digest", ownership_row.snapshot_fields)
        self.assertEqual(ownership_row.scrub_fields, ["reason_note"])
        notification_row = rows.get(model_label="notifications.Notification")
        self.assertEqual(
            notification_row.snapshot_fields,
            ["resource_type", "resource_uuid", "resource_version"],
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MigratedLocator.objects.filter(pk=locator.pk).update(
                    state="released",
                    live_space_id=space.pk,
                )

        MigratedLocator.objects.filter(pk=locator.pk).update(
            state="released",
            live_space_id=None,
        )
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tgenabled
                      FROM pg_trigger
                     WHERE tgname = 'spaces_workspace_delete_guard'
                    """
                )
                self.assertEqual(cursor.fetchone(), ("O",))
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    MigratedSpace.objects.get(pk=space.pk).delete()
            migrated_transfer.refresh_from_db()
            migrated_policy.refresh_from_db()
            self.assertEqual(migrated_transfer.space_id, space.pk)
            self.assertEqual(migrated_policy.space_id, space.pk)
            return

        MigratedSpace.objects.get(pk=space.pk).delete()
        migrated_transfer.refresh_from_db()
        migrated_policy.refresh_from_db()
        successor_row = MigratedUser.objects.get(pk=successor.pk)
        self.assertIsNone(migrated_transfer.space_id)
        self.assertEqual(migrated_transfer.space_uuid, space.pk)
        self.assertIsNone(migrated_policy.space_id)
        self.assertEqual(migrated_policy.space_uuid, space.pk)
        self.assertIsNone(successor_row.default_space_id)
