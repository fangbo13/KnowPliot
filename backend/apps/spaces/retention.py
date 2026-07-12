"""Safe retention execution for Phase 9C; destructive deletion is forbidden."""
from datetime import timedelta

from django.utils import timezone
from django.core.files.storage import default_storage


def run_retention(*, days: int, execute: bool = False):
    """Preview or apply safe retention. Never deletes audits, citations, or documents."""
    from apps.chat.models import ChatSession, ComplianceExportJob
    from apps.notifications.models import Notification
    cutoff = timezone.now() - timedelta(days=days)
    sessions = ChatSession.objects.filter(updated_at__lt=cutoff, is_active=True)
    notifications = Notification.objects.filter(created_at__lt=cutoff).exclude(body="")
    exports = ComplianceExportJob.objects.filter(created_at__lt=cutoff).exclude(result_file="")
    result = {"dry_run": not execute, "sessions_to_archive": sessions.count(), "notifications_to_redact": notifications.count(), "exports_to_remove": exports.count()}
    if execute:
        sessions.update(is_active=False)
        notifications.update(body="", metadata={})
        for job in exports:
            default_storage.delete(job.result_file)
            job.result_file = ""
            job.save(update_fields=["result_file", "updated_at"])
    return result
