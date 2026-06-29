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

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document(self, document_id: str) -> dict:
    """Full document ingestion pipeline.

    Steps: parse -> chunk -> embed -> store -> update status.

    V4.2 KB-V4.2-BATCH-010: Compute content_hash for deduplication.
    V4.2 KB-V4.2-BATCH-005: Extended timeout for large documents.

    Args:
        document_id: UUID of the Document to ingest.

    Returns:
        Dict with status and chunk count.
    """
    from apps.knowledge.models import Document
    from apps.rag.pipeline import RAGPipeline

    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
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
        pipeline = RAGPipeline()
        chunks = pipeline.ingest(doc)

        # Update document
        if chunks:
            doc.status = "active"
            doc.chunk_count = len(chunks)
            doc.save(update_fields=["status", "chunk_count"])
        # If chunks is empty, pipeline already set status to "failed" (BATCH-012)

        logger.info(f"Successfully ingested {document_id}: {len(chunks)} chunks")
        return {"status": "success", "chunks": len(chunks)}

    except Exception as exc:
        doc.status = "failed"
        doc.processing_error = str(exc)[:1000]
        doc.save(update_fields=["status", "processing_error"])

        logger.error(f"Failed to ingest {document_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
