import hashlib
import unicodedata

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


MIGRATION_OWNER = "chat.0018_workspace_retention_contract"


def _locator_digest(value):
    canonical = unicodedata.normalize("NFC", value or "")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def backfill_retention_snapshots(apps, schema_editor):
    Locator = apps.get_model("spaces", "WorkspaceLocatorReservation")
    Message = apps.get_model("chat", "Message")
    Session = apps.get_model("chat", "ChatSession")
    Feedback = apps.get_model("chat", "Feedback")
    ReviewEvent = apps.get_model("chat", "FeedbackReviewEvent")
    GapTicket = apps.get_model("chat", "KnowledgeGapTicket")
    ExportJob = apps.get_model("chat", "ComplianceExportJob")
    Invocation = apps.get_model("chat", "ModelInvocation")

    scope_by_space = {
        row[0]: (row[1], _locator_digest(row[2]))
        for row in Locator.objects.exclude(live_space_id__isnull=True).values_list(
            "live_space_id", "organization_id", "normalized_locator"
        )
    }
    message_space = dict(Message.objects.values_list("pk", "space_id"))
    session_space = dict(Session.objects.values_list("pk", "space_id"))

    def evidence(space_id, *, label, pk):
        if space_id is None:
            return None, None, ""
        scope = scope_by_space.get(space_id)
        if scope is None:
            raise RuntimeError(
                f"chat retention migration requires a durable locator for {label} {pk}"
            )
        return space_id, scope[0], scope[1]

    for row in Feedback.objects.all().only(
        "pk", "space_id", "message_id", "user_id", "reviewer_id"
    ):
        space_id = row.space_id or message_space.get(row.message_id)
        space_uuid, organization_uuid, locator_digest = evidence(
            space_id, label="Feedback", pk=row.pk
        )
        Feedback.objects.filter(pk=row.pk).update(
            space_uuid=space_uuid,
            organization_uuid=organization_uuid,
            locator_digest=locator_digest,
            message_uuid=row.message_id,
            user_uuid=row.user_id,
            reviewer_uuid=row.reviewer_id,
        )

    for row in ReviewEvent.objects.all().only(
        "pk", "space_id", "feedback_id", "actor_id", "reviewer_id"
    ):
        space_uuid, organization_uuid, locator_digest = evidence(
            row.space_id, label="FeedbackReviewEvent", pk=row.pk
        )
        ReviewEvent.objects.filter(pk=row.pk).update(
            space_uuid=space_uuid,
            organization_uuid=organization_uuid,
            locator_digest=locator_digest,
            feedback_uuid=row.feedback_id,
            actor_uuid=row.actor_id,
            reviewer_uuid=row.reviewer_id,
        )

    for row in GapTicket.objects.all().only(
        "pk", "space_id", "feedback_id", "assignee_id"
    ):
        space_uuid, organization_uuid, locator_digest = evidence(
            row.space_id, label="KnowledgeGapTicket", pk=row.pk
        )
        GapTicket.objects.filter(pk=row.pk).update(
            space_uuid=space_uuid,
            organization_uuid=organization_uuid,
            locator_digest=locator_digest,
            feedback_uuid=row.feedback_id,
            assignee_uuid=row.assignee_id,
        )

    for row in ExportJob.objects.all().only(
        "pk", "space_id", "requested_by_id"
    ):
        space_uuid, organization_uuid, locator_digest = evidence(
            row.space_id, label="ComplianceExportJob", pk=row.pk
        )
        ExportJob.objects.filter(pk=row.pk).update(
            space_uuid=space_uuid,
            organization_uuid=organization_uuid,
            locator_digest=locator_digest,
            requested_by_uuid=row.requested_by_id,
        )

    for row in Invocation.objects.all().only(
        "pk", "space_id", "session_id", "message_id", "question_message_id"
    ):
        space_id = (
            row.space_id
            or session_space.get(row.session_id)
            or message_space.get(row.message_id)
            or message_space.get(row.question_message_id)
        )
        space_uuid, organization_uuid, locator_digest = evidence(
            space_id, label="ModelInvocation", pk=row.pk
        )
        Invocation.objects.filter(pk=row.pk).update(
            space_uuid=space_uuid,
            organization_uuid=organization_uuid,
            locator_digest=locator_digest,
            session_uuid=row.session_id,
            message_uuid=row.message_id,
            question_message_uuid=row.question_message_id,
        )


def mark_registry_ready(apps, schema_editor):
    Registry = apps.get_model("spaces", "WorkspacePurgeDependency")
    contracts = {
        "chat.ConversationShare": ([], []),
        "chat.Citation": ([], []),
        "chat.Message": ([], []),
        "chat.ChatTurn": ([], []),
        "chat.ChatSession": ([], []),
        "chat.Feedback": (
            [
                "space_uuid",
                "organization_uuid",
                "locator_digest",
                "tombstone_id",
                "message_uuid",
                "user_uuid",
                "reviewer_uuid",
            ],
            [
                "comment",
                "suggested_source",
                "review_context",
                "resolution_notes",
                "sensitive_payload_scrubbed_at",
            ],
        ),
        "chat.FeedbackReviewEvent": (
            [
                "space_uuid",
                "organization_uuid",
                "locator_digest",
                "tombstone_id",
                "feedback_uuid",
                "actor_uuid",
                "reviewer_uuid",
            ],
            ["notes", "sensitive_payload_scrubbed_at"],
        ),
        "chat.KnowledgeGapTicket": (
            [
                "space_uuid",
                "organization_uuid",
                "locator_digest",
                "tombstone_id",
                "feedback_uuid",
                "assignee_uuid",
                "normalized_question_hash",
            ],
            [
                "question_snapshot",
                "suggested_source",
                "resolution_notes",
                "sensitive_payload_scrubbed_at",
            ],
        ),
        "chat.ComplianceExportJob": (
            [
                "space_uuid",
                "organization_uuid",
                "locator_digest",
                "tombstone_id",
                "requested_by_uuid",
            ],
            ["result_file", "safe_error_summary", "sensitive_payload_scrubbed_at"],
        ),
        "chat.ModelInvocation": (
            [
                "space_uuid",
                "organization_uuid",
                "locator_digest",
                "tombstone_id",
                "session_uuid",
                "message_uuid",
                "question_message_uuid",
            ],
            [],
        ),
    }
    for model_label, (snapshot_fields, scrub_fields) in contracts.items():
        updated = Registry.objects.filter(
            model_label=model_label,
            migration_owner=MIGRATION_OWNER,
            required=True,
            active=True,
        ).update(
            snapshot_fields=snapshot_fields,
            scrub_fields=scrub_fields,
            registration_state="ready",
            schema_revision=1,
        )
        if updated != 1:
            raise RuntimeError(
                f"missing or duplicate purge registry row for {model_label}"
            )


def _uuid_field():
    return models.UUIDField(blank=True, editable=False, null=True)


def _locator_field():
    return models.CharField(blank=True, default="", editable=False, max_length=64)


def _scrubbed_field():
    return models.DateTimeField(blank=True, null=True)


def _tombstone_field(related_name):
    return models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name=related_name,
        to="spaces.workspacetombstone",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("chat", "0017_independent_thinking_snapshot"),
        ("knowledge", "0011_workspace_retention_contract"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField("complianceexportjob", "locator_digest", _locator_field()),
        migrations.AddField("complianceexportjob", "organization_uuid", _uuid_field()),
        migrations.AddField("complianceexportjob", "requested_by_uuid", _uuid_field()),
        migrations.AddField("complianceexportjob", "sensitive_payload_scrubbed_at", _scrubbed_field()),
        migrations.AddField("complianceexportjob", "space_uuid", _uuid_field()),
        migrations.AddField("complianceexportjob", "tombstone", _tombstone_field("compliance_export_jobs")),
        migrations.AddField("feedback", "locator_digest", _locator_field()),
        migrations.AddField("feedback", "message_uuid", _uuid_field()),
        migrations.AddField("feedback", "organization_uuid", _uuid_field()),
        migrations.AddField("feedback", "reviewer_uuid", _uuid_field()),
        migrations.AddField("feedback", "sensitive_payload_scrubbed_at", _scrubbed_field()),
        migrations.AddField("feedback", "space_uuid", _uuid_field()),
        migrations.AddField("feedback", "tombstone", _tombstone_field("feedbacks")),
        migrations.AddField("feedback", "user_uuid", _uuid_field()),
        migrations.AddField("feedbackreviewevent", "actor_uuid", _uuid_field()),
        migrations.AddField("feedbackreviewevent", "feedback_uuid", _uuid_field()),
        migrations.AddField("feedbackreviewevent", "locator_digest", _locator_field()),
        migrations.AddField("feedbackreviewevent", "organization_uuid", _uuid_field()),
        migrations.AddField("feedbackreviewevent", "reviewer_uuid", _uuid_field()),
        migrations.AddField("feedbackreviewevent", "sensitive_payload_scrubbed_at", _scrubbed_field()),
        migrations.AddField("feedbackreviewevent", "space_uuid", _uuid_field()),
        migrations.AddField("feedbackreviewevent", "tombstone", _tombstone_field("feedback_review_events")),
        migrations.AddField("knowledgegapticket", "assignee_uuid", _uuid_field()),
        migrations.AddField("knowledgegapticket", "feedback_uuid", _uuid_field()),
        migrations.AddField("knowledgegapticket", "locator_digest", _locator_field()),
        migrations.AddField("knowledgegapticket", "organization_uuid", _uuid_field()),
        migrations.AddField("knowledgegapticket", "sensitive_payload_scrubbed_at", _scrubbed_field()),
        migrations.AddField("knowledgegapticket", "space_uuid", _uuid_field()),
        migrations.AddField("knowledgegapticket", "tombstone", _tombstone_field("knowledge_gap_tickets")),
        migrations.AddField("modelinvocation", "locator_digest", _locator_field()),
        migrations.AddField("modelinvocation", "message_uuid", _uuid_field()),
        migrations.AddField("modelinvocation", "organization_uuid", _uuid_field()),
        migrations.AddField("modelinvocation", "question_message_uuid", _uuid_field()),
        migrations.AddField("modelinvocation", "session_uuid", _uuid_field()),
        migrations.AddField("modelinvocation", "space_uuid", _uuid_field()),
        migrations.AddField("modelinvocation", "tombstone", _tombstone_field("model_invocations")),
        migrations.RunPython(backfill_retention_snapshots, migrations.RunPython.noop),
        migrations.AlterField(
            "complianceexportjob",
            "requested_by",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="compliance_export_jobs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            "complianceexportjob",
            "space",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="compliance_export_jobs",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AlterField(
            "feedback",
            "message",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="feedbacks",
                to="chat.message",
            ),
        ),
        migrations.AlterField(
            "feedback",
            "space",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="feedbacks",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AlterField(
            "feedback",
            "user",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="message_feedbacks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            "feedbackreviewevent",
            "feedback",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="review_events",
                to="chat.feedback",
            ),
        ),
        migrations.AlterField(
            "feedbackreviewevent",
            "space",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="feedback_review_events",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AlterField(
            "knowledgegapticket",
            "question_snapshot",
            models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            "knowledgegapticket",
            "space",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="knowledge_gap_tickets",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AlterField(
            "modelinvocation",
            "space",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="model_invocations",
                to="spaces.knowledgespace",
            ),
        ),
        migrations.AddConstraint(
            "complianceexportjob",
            models.CheckConstraint(
                check=(models.Q(requested_by__isnull=False) | models.Q(requested_by_uuid__isnull=False)),
                name="chat_export_actor_evidence",
            ),
        ),
        migrations.AddConstraint(
            "complianceexportjob",
            models.CheckConstraint(
                check=(models.Q(locator_digest="") | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")),
                name="chat_export_locator_shape",
            ),
        ),
        migrations.AddConstraint(
            "feedback",
            models.CheckConstraint(
                check=(models.Q(space__isnull=False) | models.Q(space_uuid__isnull=False)),
                name="chat_feedback_space_evidence",
            ),
        ),
        migrations.AddConstraint(
            "feedback",
            models.CheckConstraint(
                check=(models.Q(message__isnull=False) | models.Q(message_uuid__isnull=False)),
                name="chat_feedback_message_evidence",
            ),
        ),
        migrations.AddConstraint(
            "feedback",
            models.CheckConstraint(
                check=(models.Q(user__isnull=False) | models.Q(user_uuid__isnull=False)),
                name="chat_feedback_user_evidence",
            ),
        ),
        migrations.AddConstraint(
            "feedback",
            models.CheckConstraint(
                check=(models.Q(locator_digest="") | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")),
                name="chat_feedback_locator_shape",
            ),
        ),
        migrations.AddConstraint(
            "feedbackreviewevent",
            models.CheckConstraint(
                check=(models.Q(space__isnull=False) | models.Q(space_uuid__isnull=False)),
                name="chat_review_space_evidence",
            ),
        ),
        migrations.AddConstraint(
            "feedbackreviewevent",
            models.CheckConstraint(
                check=(models.Q(feedback__isnull=False) | models.Q(feedback_uuid__isnull=False)),
                name="chat_review_feedback_evidence",
            ),
        ),
        migrations.AddConstraint(
            "feedbackreviewevent",
            models.CheckConstraint(
                check=(models.Q(locator_digest="") | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")),
                name="chat_review_locator_shape",
            ),
        ),
        migrations.AddConstraint(
            "knowledgegapticket",
            models.CheckConstraint(
                check=(models.Q(space__isnull=False) | models.Q(space_uuid__isnull=False)),
                name="chat_gap_space_evidence",
            ),
        ),
        migrations.AddConstraint(
            "knowledgegapticket",
            models.CheckConstraint(
                check=(models.Q(locator_digest="") | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")),
                name="chat_gap_locator_shape",
            ),
        ),
        migrations.AddConstraint(
            "modelinvocation",
            models.CheckConstraint(
                check=(models.Q(locator_digest="") | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")),
                name="chat_invocation_locator_shape",
            ),
        ),
        migrations.RunPython(mark_registry_ready, migrations.RunPython.noop),
    ]
