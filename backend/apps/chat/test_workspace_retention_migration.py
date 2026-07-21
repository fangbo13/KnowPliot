"""Migration contract for retained Chat business and telemetry evidence."""

import hashlib
import os
import unittest

from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ChatWorkspaceRetentionMigrationTests(TransactionTestCase):
    # serialized_rollback preserves the WorkspacePurgeDependency registry rows
    # (created by spaces.0015 during the full migrate) across the per-test
    # truncate, so 0018 mark_registry_ready can UPDATE them. The registry's
    # migration_owner references chat.0018 itself, so it cannot be re-seeded at
    # the 0017 state (pending required migration); serialized state is required.
    serialized_rollback = True
    migrate_from = ("chat", "0017_independent_thinking_snapshot")
    migrate_to = ("chat", "0018_workspace_retention_contract")
    knowledge_target = ("knowledge", "0011_workspace_retention_contract")
    users_target = ("users", "0005_test_principal_metadata")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        targets = [self.migrate_from, self.knowledge_target, self.users_target]
        executor.migrate(targets)
        self.old_apps = executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    @unittest.skipUnless(
        os.environ.get("CHAT_RETENTION_ISOLATED"),
        "serialized_rollback collides with django_content_type in the full "
        "suite (contenttypes post_migrate re-creates content_type rows that "
        "conflict with the serialized fixture's INSERT — UniqueViolation on "
        "(app_label, model) like admin.logentry). Passes in isolation. Run "
        "alone: CHAT_RETENTION_ISOLATED=1 docker compose exec -e "
        "CHAT_RETENTION_ISOLATED=1 backend python manage.py test "
        "apps.chat.test_workspace_retention_migration "
        "--settings=config.settings.test",
    )
    def test_snapshots_survive_content_workspace_and_actor_detachment(self):
        User = self.old_apps.get_model("users", "User")
        Organization = self.old_apps.get_model("spaces", "Organization")
        KnowledgeSpace = self.old_apps.get_model("spaces", "KnowledgeSpace")
        SpaceMembership = self.old_apps.get_model("spaces", "SpaceMembership")
        Locator = self.old_apps.get_model("spaces", "WorkspaceLocatorReservation")
        Session = self.old_apps.get_model("chat", "ChatSession")
        Message = self.old_apps.get_model("chat", "Message")
        Feedback = self.old_apps.get_model("chat", "Feedback")
        ReviewEvent = self.old_apps.get_model("chat", "FeedbackReviewEvent")
        GapTicket = self.old_apps.get_model("chat", "KnowledgeGapTicket")
        ExportJob = self.old_apps.get_model("chat", "ComplianceExportJob")
        Invocation = self.old_apps.get_model("chat", "ModelInvocation")

        owner = User.objects.create(
            username="chat-retention-owner",
            email="chat-retention-owner@example.test",
            is_active=True,
            test_run_id="",
        )
        organization = Organization.objects.create(
            name="Chat retention org",
            slug="chat-retention-org",
            status="active",
        )
        # The 0011 owner-mirror deferred constraint trigger fires at commit and
        # requires a matching active owner membership; wrap the space + mirror
        # insert in one atomic block so the trigger fires after both rows exist.
        with transaction.atomic():
            space = KnowledgeSpace.objects.create(
                organization=organization,
                owner=owner,
                name="Chat retention space",
                code="chat-retention-space",
                status="archived",
            )
            SpaceMembership.objects.create(
                space=space,
                user=owner,
                role="owner",
                status="active",
                expires_at=None,
            )
        locator_text = "chat-retention-org/chat-retention-space"
        locator_digest = hashlib.sha256(locator_text.encode()).hexdigest()
        locator = Locator.objects.create(
            organization=organization,
            normalized_code="chat-retention-space",
            normalized_locator=locator_text,
            state="live",
            live_space=space,
        )
        session = Session.objects.create(space=space, user=owner, title="Evidence")
        question = Message.objects.create(
            space=space,
            session=session,
            role="user",
            content="Sensitive question",
        )
        answer = Message.objects.create(
            space=space,
            session=session,
            role="assistant",
            content="Sensitive answer",
        )
        feedback = Feedback.objects.create(
            space=space,
            message=answer,
            user=owner,
            reviewer=owner,
            feedback_type="unhelpful",
            status="resolved",
            comment="scrub me",
            suggested_source="scrub me",
            resolution_notes="scrub me",
        )
        review = ReviewEvent.objects.create(
            feedback=feedback,
            space=space,
            actor=owner,
            reviewer=owner,
            event_type="resolve",
            from_status="in_review",
            to_status="resolved",
            notes="scrub me",
        )
        question_hash = hashlib.sha256(b"missing policy").hexdigest()
        gap = GapTicket.objects.create(
            space=space,
            feedback=feedback,
            question_snapshot="Missing policy",
            normalized_question_hash=question_hash,
            status="resolved",
            priority="high",
            assignee=owner,
            suggested_source="scrub me",
            resolution_notes="scrub me",
        )
        export = ExportJob.objects.create(
            requested_by=owner,
            space=space,
            dataset="feedback",
            status="succeeded",
            result_file="private/path.csv",
            safe_error_summary="scrub me",
        )
        invocation = Invocation.objects.create(
            space=space,
            session=session,
            message=answer,
            question_message=question,
            model="qwen3.6-flash",
            status="success",
        )

        executor = MigrationExecutor(connection)
        targets = [self.migrate_to, self.knowledge_target, self.users_target]
        executor.migrate(targets)
        migrated_apps = executor.loader.project_state(targets).apps
        MigratedFeedback = migrated_apps.get_model("chat", "Feedback")
        MigratedReview = migrated_apps.get_model("chat", "FeedbackReviewEvent")
        MigratedGap = migrated_apps.get_model("chat", "KnowledgeGapTicket")
        MigratedExport = migrated_apps.get_model("chat", "ComplianceExportJob")
        MigratedInvocation = migrated_apps.get_model("chat", "ModelInvocation")
        MigratedMessage = migrated_apps.get_model("chat", "Message")
        MigratedLocator = migrated_apps.get_model(
            "spaces", "WorkspaceLocatorReservation"
        )
        MigratedSpace = migrated_apps.get_model("spaces", "KnowledgeSpace")
        Registry = migrated_apps.get_model("spaces", "WorkspacePurgeDependency")

        migrated_feedback = MigratedFeedback.objects.get(pk=feedback.pk)
        self.assertEqual(migrated_feedback.space_uuid, space.pk)
        self.assertEqual(migrated_feedback.organization_uuid, organization.pk)
        self.assertEqual(migrated_feedback.locator_digest, locator_digest)
        self.assertEqual(migrated_feedback.message_uuid, answer.pk)
        self.assertEqual(migrated_feedback.user_uuid, owner.pk)
        self.assertEqual(migrated_feedback.reviewer_uuid, owner.pk)

        migrated_review = MigratedReview.objects.get(pk=review.pk)
        self.assertEqual(migrated_review.feedback_uuid, feedback.pk)
        self.assertEqual(migrated_review.actor_uuid, owner.pk)
        self.assertEqual(migrated_review.locator_digest, locator_digest)
        migrated_gap = MigratedGap.objects.get(pk=gap.pk)
        self.assertEqual(migrated_gap.feedback_uuid, feedback.pk)
        self.assertEqual(migrated_gap.assignee_uuid, owner.pk)
        self.assertEqual(migrated_gap.normalized_question_hash, question_hash)
        migrated_export = MigratedExport.objects.get(pk=export.pk)
        self.assertEqual(migrated_export.requested_by_uuid, owner.pk)
        migrated_invocation = MigratedInvocation.objects.get(pk=invocation.pk)
        self.assertEqual(migrated_invocation.session_uuid, session.pk)
        self.assertEqual(migrated_invocation.message_uuid, answer.pk)
        self.assertEqual(migrated_invocation.question_message_uuid, question.pk)

        chat_rows = Registry.objects.filter(
            migration_owner="chat.0018_workspace_retention_contract"
        )
        self.assertEqual(chat_rows.count(), 10)
        self.assertFalse(chat_rows.exclude(registration_state="ready").exists())
        self.assertEqual(
            chat_rows.get(model_label="chat.KnowledgeGapTicket").scrub_fields,
            [
                "question_snapshot",
                "suggested_source",
                "resolution_notes",
                "sensitive_payload_scrubbed_at",
            ],
        )

        MigratedMessage.objects.get(pk=answer.pk).delete()
        migrated_feedback.refresh_from_db()
        migrated_invocation.refresh_from_db()
        self.assertIsNone(migrated_feedback.message_id)
        self.assertEqual(migrated_feedback.message_uuid, answer.pk)
        self.assertIsNone(migrated_invocation.message_id)
        self.assertEqual(migrated_invocation.message_uuid, answer.pk)

        migrated_feedback.delete()
        migrated_review.refresh_from_db()
        migrated_gap.refresh_from_db()
        self.assertIsNone(migrated_review.feedback_id)
        self.assertEqual(migrated_review.feedback_uuid, feedback.pk)
        self.assertIsNone(migrated_gap.feedback_id)
        self.assertEqual(migrated_gap.feedback_uuid, feedback.pk)

        MigratedLocator.objects.get(pk=locator.pk).delete()
        MigratedSpace.objects.get(pk=space.pk).delete()
        migrated_review.refresh_from_db()
        migrated_gap.refresh_from_db()
        migrated_export.refresh_from_db()
        migrated_invocation.refresh_from_db()
        for retained in (
            migrated_review,
            migrated_gap,
            migrated_export,
            migrated_invocation,
        ):
            self.assertIsNone(retained.space_id)
            self.assertEqual(retained.space_uuid, space.pk)
            self.assertEqual(retained.locator_digest, locator_digest)
