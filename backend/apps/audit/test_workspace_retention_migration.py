"""Migration contract for immutable workspace-scoped audit evidence."""

import hashlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AuditWorkspaceRetentionMigrationTests(TransactionTestCase):
    serialized_rollback = True
    migrate_from = ("audit", "0014_alter_auditlog_action_and_more")
    migrate_to = ("audit", "0015_workspace_retention_contract")
    scenario_target = (
        "scenario_templates",
        "0007_workspace_retention_contract",
    )
    users_target = ("users", "0005_test_principal_metadata")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        targets = [self.migrate_from, self.scenario_target, self.users_target]
        executor.migrate(targets)
        self.old_apps = executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_actor_and_locator_snapshots_survive_live_rows(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        Locator = self.old_apps.get_model("spaces", "WorkspaceLocatorReservation")
        AuditLog = self.old_apps.get_model("audit", "AuditLog")

        owner = User.objects.create(
            username="audit-retention-owner",
            email="audit-retention-owner@example.test",
            is_active=True,
            test_run_id="",
        )
        organization = Organization.objects.create(
            name="Audit retention org",
            slug="audit-retention-org",
            status="active",
        )
        space = KnowledgeSpace.objects.create(
            organization=organization,
            owner=owner,
            name="Audit retention space",
            code="audit-retention-space",
            status="archived",
        )
        locator_text = "audit-retention-org/audit-retention-space"
        locator_digest = hashlib.sha256(locator_text.encode()).hexdigest()
        locator = Locator.objects.create(
            organization=organization,
            normalized_code="audit-retention-space",
            normalized_locator=locator_text,
            state="live",
            live_space=space,
        )
        event = AuditLog.objects.create(
            user=owner,
            action="space_archive",
            target_type="KnowledgeSpace",
            target_id=space.pk,
            organization_id=organization.pk,
            space_id=space.pk,
            details={"safe": True},
        )

        executor = MigrationExecutor(connection)
        targets = [self.migrate_to, self.scenario_target, self.users_target]
        executor.migrate(targets)
        migrated_apps = executor.loader.project_state(targets).apps
        MigratedAudit = migrated_apps.get_model("audit", "AuditLog")
        MigratedLocator = migrated_apps.get_model(
            "spaces", "WorkspaceLocatorReservation"
        )
        MigratedSpace = migrated_apps.get_model("spaces", "KnowledgeSpace")
        MigratedUser = migrated_apps.get_model("users", "User")
        Registry = migrated_apps.get_model("spaces", "WorkspacePurgeDependency")

        migrated = MigratedAudit.objects.get(pk=event.pk)
        self.assertEqual(migrated.actor_uuid, owner.pk)
        self.assertEqual(migrated.space_id, space.pk)
        self.assertEqual(migrated.organization_id, organization.pk)
        self.assertEqual(migrated.locator_digest, locator_digest)
        self.assertIsNone(migrated.tombstone_id)
        self.assertIsNone(migrated.governed_request_id)

        registry = Registry.objects.get(model_label="audit.AuditLog")
        self.assertEqual(registry.registration_state, "ready")
        self.assertEqual(registry.scrub_fields, [])
        self.assertIn("actor_uuid", registry.snapshot_fields)
        self.assertIn("governed_request_uuid", registry.snapshot_fields)

        MigratedLocator.objects.get(pk=locator.pk).delete()
        MigratedSpace.objects.get(pk=space.pk).delete()
        MigratedUser.objects.get(pk=owner.pk).delete()
        migrated.refresh_from_db()
        self.assertIsNone(migrated.user_id)
        self.assertEqual(migrated.actor_uuid, owner.pk)
        self.assertEqual(migrated.space_id, space.pk)
        self.assertEqual(migrated.locator_digest, locator_digest)
