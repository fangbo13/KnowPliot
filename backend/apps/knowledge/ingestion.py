"""Durable dispatch helpers for document ingestion."""

from django.db import transaction
from django.utils import timezone

from .models import IngestionJob


ACTIVE_JOB_STATUSES = ("queued", "processing", "retrying")


class IngestionAlreadyActive(Exception):
    """Raised when a document already has non-terminal ingestion work."""


def enqueue_document_ingestion(
    document,
    *,
    requested_by=None,
    trigger="upload",
    retry_of=None,
    prevent_duplicate=False,
):
    """Create a durable job before dispatching its Celery task."""
    if document.space_id is None:
        raise ValueError("Ingestion requires a space-scoped document.")

    with transaction.atomic():
        document.__class__.objects.select_for_update().get(pk=document.pk)
        if (
            prevent_duplicate
            and IngestionJob.objects.filter(
                document=document,
                status__in=ACTIVE_JOB_STATUSES,
            ).exists()
        ):
            raise IngestionAlreadyActive(
                "This document already has active ingestion work."
            )
        job = IngestionJob.objects.create(
            document=document,
            space_id=document.space_id,
            requested_by=requested_by,
            trigger=trigger,
            retry_of=retry_of,
            status="queued",
        )
        if document.status != "processing":
            document.status = "processing"
            document.processing_error = ""
            document.save(
                update_fields=["status", "processing_error", "updated_at"]
            )

    from apps.rag.services import ingest_document

    try:
        async_result = ingest_document.delay(str(document.id), str(job.id))
    except Exception as exc:
        job.status = "failed"
        job.last_error = "dispatch_failed"
        job.completed_at = timezone.now()
        job.save(
            update_fields=["status", "last_error", "completed_at", "updated_at"]
        )
        document.status = "failed"
        document.processing_error = f"Task dispatch failed: {exc.__class__.__name__}"
        document.save(
            update_fields=["status", "processing_error", "updated_at"]
        )
        raise

    task_id = getattr(async_result, "id", "")
    job.celery_task_id = task_id if isinstance(task_id, str) else ""
    job.save(update_fields=["celery_task_id", "updated_at"])
    return job
