"""Celery tasks for RAG document ingestion."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_document(self, document_id: str) -> dict:
    """Full document ingestion pipeline.

    Steps: parse -> chunk -> embed -> store -> update status.

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

    # Update status to processing
    doc.status = "processing"
    doc.save(update_fields=["status"])

    try:
        pipeline = RAGPipeline()
        chunks = pipeline.ingest(doc)

        # Update document
        doc.status = "active"
        doc.chunk_count = len(chunks)
        doc.save(update_fields=["status", "chunk_count"])

        logger.info(f"Successfully ingested {document_id}: {len(chunks)} chunks")
        return {"status": "success", "chunks": len(chunks)}

    except Exception as exc:
        doc.status = "failed"
        doc.processing_error = str(exc)[:1000]
        doc.save(update_fields=["status", "processing_error"])

        logger.error(f"Failed to ingest {document_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
