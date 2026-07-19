"""Migration contract for workspace-scoped Knowledge retention evidence."""

import hashlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class KnowledgeWorkspaceRetentionMigrationTests(TransactionTestCase):
    serialized_rollback = True
    migrate_from = ("knowledge", "0010_ingestionjob_know_ing_st_sp_cr_idx")
    migrate_to = ("knowledge", "0011_workspace_retention_contract")
    spaces_target = ("spaces", "0015_workspace_deletion_stage_a")
    users_target = ("users", "0005_test_principal_metadata")
    notifications_target = (
        "notifications",
        "0003_actionable_notification_contract",
    )

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        targets = [
            self.migrate_from,
            self.spaces_target,
            self.users_target,
            self.notifications_target,
        ]
        executor.migrate(targets)
        self.old_apps = executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_snapshots_detach_and_legacy_scope_remains_explicit(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        Locator = self.old_apps.get_model("spaces", "WorkspaceLocatorReservation")
        Document = self.old_apps.get_model("knowledge", "Document")
        IngestionJob = self.old_apps.get_model("knowledge", "IngestionJob")
        BatchResult = self.old_apps.get_model(
            "knowledge", "BatchImportResultRecord"
        )

        owner = User.objects.create(
            username="knowledge-retention-owner",
            email="knowledge-retention-owner@example.test",
            is_active=True,
            test_run_id="",
        )
        organization = Organization.objects.create(
            name="Knowledge retention org",
            slug="knowledge-retention-org",
            status="active",
        )
        space = KnowledgeSpace.objects.create(
            organization=organization,
            owner=owner,
            name="Knowledge retention space",
            code="knowledge-retention-space",
            status="archived",
        )
        locator_text = "knowledge-retention-org/knowledge-retention-space"
        locator_digest = hashlib.sha256(locator_text.encode()).hexdigest()
        locator = Locator.objects.create(
            organization=organization,
            normalized_code="knowledge-retention-space",
            normalized_locator=locator_text,
            state="live",
            live_space=space,
        )
        document = Document.objects.create(
            space=space,
            title="Migration evidence",
            file="documents/migration-evidence.txt",
            file_type="txt",
            file_size=10,
            uploaded_by=owner,
            status="active",
        )
        ingestion = IngestionJob.objects.create(
            document=document,
            space=space,
            requested_by=owner,
            status="succeeded",
            celery_task_id="must-be-scrubbable",
            last_error="must-be-scrubbable",
        )
        batch = BatchResult.objects.create(
            uploaded_by=owner,
            status="completed",
            error_message="legacy raw error",
            result_details=[{"filename": "private-name.txt"}],
        )

        executor = MigrationExecutor(connection)
        targets = [
            self.migrate_to,
            self.spaces_target,
            self.users_target,
            self.notifications_target,
        ]
        executor.migrate(targets)
        migrated_apps = executor.loader.project_state(targets).apps
        MigratedDocument = migrated_apps.get_model("knowledge", "Document")
        MigratedIngestion = migrated_apps.get_model("knowledge", "IngestionJob")
        MigratedBatch = migrated_apps.get_model(
            "knowledge", "BatchImportResultRecord"
        )
        MigratedLocator = migrated_apps.get_model(
            "spaces", "WorkspaceLocatorReservation"
        )
        MigratedSpace = migrated_apps.get_model("spaces", "KnowledgeSpace")
        Registry = migrated_apps.get_model("spaces", "WorkspacePurgeDependency")

        migrated_ingestion = MigratedIngestion.objects.get(pk=ingestion.pk)
        self.assertEqual(migrated_ingestion.document_uuid, document.pk)
        self.assertEqual(migrated_ingestion.space_uuid, space.pk)
        self.assertEqual(migrated_ingestion.organization_uuid, organization.pk)
        self.assertEqual(migrated_ingestion.locator_digest, locator_digest)
        self.assertEqual(migrated_ingestion.requested_by_uuid, owner.pk)

        migrated_batch = MigratedBatch.objects.get(pk=batch.pk)
        self.assertTrue(migrated_batch.legacy_scope_unknown)
        self.assertIsNone(migrated_batch.space_uuid)
        self.assertEqual(migrated_batch.uploaded_by_uuid, owner.pk)

        knowledge_rows = Registry.objects.filter(migration_owner=self.migrate_to[0] + ".0011_workspace_retention_contract")
        self.assertEqual(knowledge_rows.count(), 5)
        self.assertFalse(knowledge_rows.exclude(registration_state="ready").exists())
        ingestion_registry = knowledge_rows.get(model_label="knowledge.IngestionJob")
        self.assertEqual(
            ingestion_registry.scrub_fields,
            ["celery_task_id", "last_error", "sensitive_payload_scrubbed_at"],
        )
        self.assertIn("document_uuid", ingestion_registry.snapshot_fields)

        MigratedDocument.objects.get(pk=document.pk).delete()
        migrated_ingestion.refresh_from_db()
        self.assertIsNone(migrated_ingestion.document_id)
        self.assertEqual(migrated_ingestion.document_uuid, document.pk)

        MigratedLocator.objects.get(pk=locator.pk).delete()
        MigratedSpace.objects.get(pk=space.pk).delete()
        migrated_ingestion.refresh_from_db()
        self.assertIsNone(migrated_ingestion.space_id)
        self.assertEqual(migrated_ingestion.space_uuid, space.pk)
        self.assertEqual(migrated_ingestion.locator_digest, locator_digest)
