from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.audit.views import create_audit_log
from apps.knowledge.models import Document


class Command(BaseCommand):
    help = "Mark active documents past effective_to as stale."

    def handle(self, *args, **options):
        documents = list(
            Document.objects.filter(
                status="active",
                effective_to__lt=timezone.localdate(),
            ).select_related("space")
        )
        for document in documents:
            create_audit_log(
                user=None,
                action="document_status_change",
                target_type="Document",
                target_id=document.id,
                details={
                    "from": "active",
                    "to": "stale",
                    "automatic": True,
                },
            )
            document.status = "stale"
            document.save(update_fields=["status", "updated_at"])
        self.stdout.write(str(len(documents)))
