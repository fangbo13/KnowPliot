"""Scan answer-quality SLA breaches and create deduplicated notifications."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.audit.views import create_audit_log
from apps.chat.models import Feedback, KnowledgeGapTicket
from apps.notifications.models import Notification
from apps.spaces.models import SpaceMembership


PENDING_FEEDBACK_DAYS = 3
IN_REVIEW_FEEDBACK_DAYS = 5
OPEN_GAP_DAYS = 3


def _space_stewards(space):
    return {
        membership.user
        for membership in SpaceMembership.objects.filter(
            space=space,
            role__in=[
                SpaceMembership.ROLE_OWNER,
                SpaceMembership.ROLE_REVIEWER,
                SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
            ],
        ).select_related("user")
    }


def _create_once(*, recipient, dedupe_key, title, body, link, metadata):
    if Notification.objects.filter(
        recipient=recipient,
        type=Notification.TYPE_SYSTEM,
        metadata__dedupe_key=dedupe_key,
    ).exists():
        return None
    return Notification.objects.create(
        recipient=recipient,
        type=Notification.TYPE_SYSTEM,
        title=title,
        body=body,
        level="warning",
        link=link,
        metadata={"dedupe_key": dedupe_key, **metadata},
    )


class Command(BaseCommand):
    help = "Create quality SLA notifications for overdue feedback reviews and gaps."

    def handle(self, *args, **options):
        now = timezone.now()
        created = 0

        feedback_thresholds = [
            (
                Feedback.STATUS_PENDING_REVIEW,
                PENDING_FEEDBACK_DAYS,
                "pending_feedback_overdue",
                "Pending feedback review is overdue",
            ),
            (
                Feedback.STATUS_IN_REVIEW,
                IN_REVIEW_FEEDBACK_DAYS,
                "in_review_feedback_overdue",
                "In-review feedback is overdue",
            ),
        ]
        for status, days, alert_type, title in feedback_thresholds:
            threshold = now - timedelta(days=days)
            feedback_qs = Feedback.objects.filter(
                status=status,
                created_at__lt=threshold,
                space__isnull=False,
            ).select_related("space", "reviewer", "user")
            for feedback in feedback_qs:
                recipients = _space_stewards(feedback.space)
                if feedback.reviewer_id:
                    recipients.add(feedback.reviewer)
                for recipient in recipients:
                    dedupe_key = f"{alert_type}:{feedback.id}:{recipient.id}"
                    notification = _create_once(
                        recipient=recipient,
                        dedupe_key=dedupe_key,
                        title=title,
                        body=f"Feedback {feedback.id} has been waiting more than {days} days.",
                        link="/admin/quality",
                        metadata={
                            "alert_type": alert_type,
                            "feedback_id": str(feedback.id),
                            "space_id": str(feedback.space_id),
                            "sla_days": days,
                        },
                    )
                    if notification:
                        created += 1
                        create_audit_log(
                            user=None,
                            action="sla_alert_created",
                            target_type="Feedback",
                            target_id=feedback.id,
                            space_id=feedback.space_id,
                            details={
                                "dedupe_key": dedupe_key,
                                "recipient_id": str(recipient.id),
                                "alert_type": alert_type,
                            },
                        )

        gap_threshold = now - timedelta(days=OPEN_GAP_DAYS)
        gap_qs = KnowledgeGapTicket.objects.filter(
            status__in=[
                KnowledgeGapTicket.STATUS_OPEN,
                KnowledgeGapTicket.STATUS_IN_PROGRESS,
            ],
            created_at__lt=gap_threshold,
        ).select_related("space", "assignee")
        for gap in gap_qs:
            recipients = _space_stewards(gap.space)
            if gap.assignee_id:
                recipients.add(gap.assignee)
            for recipient in recipients:
                dedupe_key = f"gap_overdue:{gap.id}:{recipient.id}"
                notification = _create_once(
                    recipient=recipient,
                    dedupe_key=dedupe_key,
                    title="Knowledge gap SLA is overdue",
                    body=f"Knowledge gap {gap.id} has remained open more than {OPEN_GAP_DAYS} days.",
                    link="/admin/quality",
                    metadata={
                        "alert_type": "gap_overdue",
                        "gap_id": str(gap.id),
                        "space_id": str(gap.space_id),
                        "sla_days": OPEN_GAP_DAYS,
                    },
                )
                if notification:
                    created += 1
                    create_audit_log(
                        user=None,
                        action="sla_alert_created",
                        target_type="KnowledgeGapTicket",
                        target_id=gap.id,
                        space_id=gap.space_id,
                        details={
                            "dedupe_key": dedupe_key,
                            "recipient_id": str(recipient.id),
                            "alert_type": "gap_overdue",
                        },
                    )

        self.stdout.write(self.style.SUCCESS(f"Created {created} quality SLA notifications."))
