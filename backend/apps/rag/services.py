# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Celery tasks for RAG document ingestion.

V4.2 KB-V4.2-BATCH-005: Extended task timeout for batch documents.
V4.2 KB-V4.2-BATCH-010: Content hash computation for deduplication.
"""

import hashlib
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document(self, document_id: str, job_id: str | None = None) -> dict:
    """Full document ingestion pipeline.

    Steps: parse -> chunk -> embed -> store -> update status.

    V4.2 KB-V4.2-BATCH-010: Compute content_hash for deduplication.
    V4.2 KB-V4.2-BATCH-005: Extended timeout for large documents.

    Args:
        document_id: UUID of the Document to ingest.

    Returns:
        Dict with status and chunk count.
    """
    from apps.knowledge.models import Document, IngestionJob
    from apps.rag.pipeline import RAGPipeline

    job = None
    if job_id:
        job = IngestionJob.objects.filter(id=job_id, document_id=document_id).first()
        if job:
            job.status = "processing"
            job.attempt = self.request.retries + 1
            job.started_at = job.started_at or timezone.now()
            job.last_error = ""
            job.save(
                update_fields=[
                    "status", "attempt", "started_at", "last_error", "updated_at"
                ]
            )

    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        if job:
            job.status = "failed"
            job.last_error = "document_not_found"
            job.completed_at = timezone.now()
            job.save(
                update_fields=[
                    "status", "last_error", "completed_at", "updated_at"
                ]
            )
        return {"status": "error", "message": "Document not found"}

    # V4.2 KB-V4.2-BATCH-010: Compute content hash for deduplication
    if not doc.content_hash:
        try:
            with doc.file.open("rb") as f:
                content_hash = hashlib.sha256(f.read()).hexdigest()
            doc.content_hash = content_hash
            doc.save(update_fields=["content_hash"])
            logger.info(f"[BATCH-010] Content hash computed for document {document_id}: {content_hash[:16]}...")
        except Exception as e:
            logger.warning(f"[BATCH-010] Could not compute content hash: {e}")

    # Update status to processing
    doc.status = "processing"
    doc.save(update_fields=["status"])

    try:
        pipeline = RAGPipeline(ingestion=True)
        chunks = pipeline.ingest(doc)

        # Update document
        if chunks:
            doc.status = "active"
            doc.chunk_count = len(chunks)
            doc.processing_error = ""
            doc.save(update_fields=["status", "chunk_count", "processing_error"])
        # If chunks is empty, pipeline already set status to "failed" (BATCH-012)

        if job:
            job.status = "succeeded" if chunks else "failed"
            job.last_error = "" if chunks else (doc.processing_error or "no_chunks")
            job.completed_at = timezone.now()
            job.save(
                update_fields=[
                    "status", "last_error", "completed_at", "updated_at"
                ]
            )

        if chunks:
            logger.info(f"Successfully ingested {document_id}: {len(chunks)} chunks")
            return {"status": "success", "chunks": len(chunks)}
        logger.error("Ingestion produced no usable chunks for %s", document_id)
        return {"status": "error", "message": "No usable chunks generated"}

    except Exception as exc:
        final_attempt = self.request.retries >= self.max_retries
        doc.status = "failed" if final_attempt else "processing"
        doc.processing_error = str(exc)[:1000]
        doc.save(update_fields=["status", "processing_error"])

        if job:
            job.status = "failed" if final_attempt else "retrying"
            job.last_error = exc.__class__.__name__
            job.completed_at = timezone.now() if final_attempt else None
            job.save(
                update_fields=[
                    "status", "last_error", "completed_at", "updated_at"
                ]
            )

        logger.error(f"Failed to ingest {document_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
