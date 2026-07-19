"""Migration evidence for normalized, pinned scenario-template revisions."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class VersionedCloneMigrationTests(TransactionTestCase):
    serialized_rollback = True
    migrate_from = ("scenario_templates", "0005_phase8b_catalog_assets")
    migrate_to = ("scenario_templates", "0006_versioned_clone_contract")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        self.old_apps = executor.loader.project_state([self.migrate_from]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_backfill_normalizes_hashes_current_pointer_and_application_pin(self):
        Template = self.old_apps.get_model(
            "scenario_templates", "ScenarioTemplate"
        )
        Revision = self.old_apps.get_model(
            "scenario_templates", "ScenarioTemplateRevision"
        )
        Application = self.old_apps.get_model(
            "scenario_templates", "ScenarioTemplateApplication"
        )

        template = Template.objects.create(
            name="Historical template",
            code="historical-template",
            scenario_type="audit",
            quick_questions=["Historical question"],
            prompt_policy={"system": "Historical prompt"},
        )
        first = Revision.objects.create(
            template=template,
            version=1,
            snapshot={
                "scenario_type": "audit",
                "quick_questions": ["v1"],
                "default_visibility": "private",
            },
        )
        second = Revision.objects.create(
            template=template,
            version=2,
            snapshot={
                "scenario_type": "audit",
                "quick_questions": ["v2"],
                "default_visibility": "private",
            },
        )
        exact_application = Application.objects.create(
            template=template,
            template_snapshot={"latest_version": 1},
        )
        unknown_application = Application.objects.create(
            template=template,
            template_snapshot={"template_code": template.code},
        )
        empty_template = Template.objects.create(
            name="No historical revision",
            code="no-historical-revision",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        apps = executor.loader.project_state([self.migrate_to]).apps
        MigratedTemplate = apps.get_model(
            "scenario_templates", "ScenarioTemplate"
        )
        MigratedRevision = apps.get_model(
            "scenario_templates", "ScenarioTemplateRevision"
        )
        MigratedApplication = apps.get_model(
            "scenario_templates", "ScenarioTemplateApplication"
        )

        migrated = MigratedTemplate.objects.get(pk=template.pk)
        migrated_first = MigratedRevision.objects.get(pk=first.pk)
        migrated_second = MigratedRevision.objects.get(pk=second.pk)
        self.assertEqual(migrated.current_revision_id, migrated_second.id)
        for revision in (migrated_first, migrated_second):
            self.assertEqual(revision.snapshot["schema_version"], 1)
            self.assertEqual(
                set(revision.snapshot["components"]),
                {
                    "category_tree",
                    "scenario_definitions",
                    "quality_rubric",
                    "workspace_defaults",
                    "model_policy_refs",
                },
            )
            self.assertRegex(revision.snapshot_hash, r"^[0-9a-f]{64}$")
            self.assertIsNotNone(revision.published_at)

        exact = MigratedApplication.objects.get(pk=exact_application.pk)
        unknown = MigratedApplication.objects.get(pk=unknown_application.pk)
        self.assertEqual(exact.template_revision_id, migrated_first.id)
        self.assertFalse(exact.legacy_revision_unknown)
        self.assertIsNone(unknown.template_revision_id)
        self.assertTrue(unknown.legacy_revision_unknown)

        empty = MigratedTemplate.objects.get(pk=empty_template.pk)
        self.assertIsNotNone(empty.current_revision_id)
        self.assertEqual(
            MigratedRevision.objects.get(pk=empty.current_revision_id).version,
            1,
        )
