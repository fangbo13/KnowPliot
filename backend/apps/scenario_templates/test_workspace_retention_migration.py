"""Migration contract for retained scenario-template application evidence."""

import hashlib
from datetime import datetime, timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ScenarioWorkspaceRetentionMigrationTests(TransactionTestCase):
    serialized_rollback = True
    migrate_from = ("scenario_templates", "0006_versioned_clone_contract")
    migrate_to = ("scenario_templates", "0007_workspace_retention_contract")
    chat_target = ("chat", "0018_workspace_retention_contract")
    users_target = ("users", "0005_test_principal_metadata")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        targets = [self.migrate_from, self.chat_target, self.users_target]
        executor.migrate(targets)
        self.old_apps = executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_application_snapshots_survive_workspace_and_template_detachment(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        Locator = self.old_apps.get_model("spaces", "WorkspaceLocatorReservation")
        Template = self.old_apps.get_model(
            "scenario_templates", "ScenarioTemplate"
        )
        Revision = self.old_apps.get_model(
            "scenario_templates", "ScenarioTemplateRevision"
        )
        Application = self.old_apps.get_model(
            "scenario_templates", "ScenarioTemplateApplication"
        )

        owner = User.objects.create(
            username="scenario-retention-owner",
            email="scenario-retention-owner@example.test",
            is_active=True,
            test_run_id="",
        )
        organization = Organization.objects.create(
            name="Scenario retention org",
            slug="scenario-retention-org",
            status="active",
        )
        space = KnowledgeSpace.objects.create(
            organization=organization,
            owner=owner,
            name="Scenario retention space",
            code="scenario-retention-space",
            status="archived",
        )
        locator_text = "scenario-retention-org/scenario-retention-space"
        locator_digest = hashlib.sha256(locator_text.encode()).hexdigest()
        locator = Locator.objects.create(
            organization=organization,
            normalized_code="scenario-retention-space",
            normalized_locator=locator_text,
            state="live",
            live_space=space,
        )
        template = Template.objects.create(
            name="Retention blueprint",
            code="retention-blueprint",
            organization=organization,
            created_by=owner,
        )
        revision_hash = "a" * 64
        revision = Revision.objects.create(
            template=template,
            version=1,
            snapshot={"schema_version": 1, "components": {}},
            snapshot_hash=revision_hash,
            published_at=datetime.now(timezone.utc),
            created_by=owner,
        )
        Template.objects.filter(pk=template.pk).update(current_revision_id=revision.pk)
        application = Application.objects.create(
            template=template,
            template_revision=revision,
            legacy_revision_unknown=False,
            space=space,
            organization=organization,
            created_by=owner,
            task_ids=["sensitive-task-id"],
            template_snapshot={"private": "mutable"},
        )

        executor = MigrationExecutor(connection)
        targets = [self.migrate_to, self.chat_target, self.users_target]
        executor.migrate(targets)
        migrated_apps = executor.loader.project_state(targets).apps
        MigratedApplication = migrated_apps.get_model(
            "scenario_templates", "ScenarioTemplateApplication"
        )
        MigratedTemplate = migrated_apps.get_model(
            "scenario_templates", "ScenarioTemplate"
        )
        MigratedLocator = migrated_apps.get_model(
            "spaces", "WorkspaceLocatorReservation"
        )
        MigratedSpace = migrated_apps.get_model("spaces", "KnowledgeSpace")
        Registry = migrated_apps.get_model("spaces", "WorkspacePurgeDependency")

        migrated = MigratedApplication.objects.get(pk=application.pk)
        self.assertEqual(migrated.template_uuid, template.pk)
        self.assertEqual(migrated.template_key_snapshot, template.code)
        self.assertEqual(migrated.template_revision_uuid, revision.pk)
        self.assertEqual(migrated.template_revision_hash, revision_hash)
        self.assertEqual(migrated.space_uuid, space.pk)
        self.assertEqual(migrated.organization_uuid, organization.pk)
        self.assertEqual(migrated.locator_digest, locator_digest)
        self.assertEqual(migrated.created_by_uuid, owner.pk)

        registry = Registry.objects.get(
            model_label="scenario_templates.ScenarioTemplateApplication"
        )
        self.assertEqual(registry.registration_state, "ready")
        self.assertEqual(
            registry.scrub_fields,
            [
                "task_ids",
                "template_snapshot",
                "sensitive_payload_scrubbed_at",
            ],
        )
        self.assertIn("template_revision_hash", registry.snapshot_fields)

        # A legacy-unknown application may detach from a removed template while
        # retaining its immutable template identity evidence.
        MigratedApplication.objects.filter(pk=application.pk).update(
            template_revision_id=None,
            legacy_revision_unknown=True,
        )
        MigratedTemplate.objects.filter(pk=template.pk).update(current_revision_id=None)
        MigratedTemplate.objects.get(pk=template.pk).delete()
        migrated.refresh_from_db()
        self.assertIsNone(migrated.template_id)
        self.assertEqual(migrated.template_uuid, template.pk)
        self.assertEqual(migrated.template_key_snapshot, template.code)

        MigratedLocator.objects.get(pk=locator.pk).delete()
        MigratedSpace.objects.get(pk=space.pk).delete()
        migrated.refresh_from_db()
        self.assertIsNone(migrated.space_id)
        self.assertEqual(migrated.space_uuid, space.pk)
        self.assertEqual(migrated.locator_digest, locator_digest)
