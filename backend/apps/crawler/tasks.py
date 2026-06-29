"""Celery tasks for crawler — V4.1 KB-V4.1-011~017.

crawl_and_ingest: Full crawl + ingestion pipeline.
Steps: validate URL → fetch content → clean → create Document → chunk → embed → store.

Uses async httpx for fetching. Since Celery worker uses prefork pool by default,
we use asyncio.run() to bridge async code within sync Celery tasks.
Gevent pool will be enabled after installing gevent package.
"""

import asyncio
import logging
import tempfile
import os

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='critical')  # V4.2 SYS-V4.2-013: routed to critical queue
def crawl_and_ingest(self, crawled_document_id: str) -> dict:
    """Full crawl + ingestion pipeline for a CrawledDocument.

    Steps: validate URL → fetch content → clean → chunk → embed → store.

    Args:
        crawled_document_id: UUID of the CrawledDocument to process.

    Returns:
        Dict with status and document_id if successful.
    """
    from apps.crawler.models import CrawledDocument, CrawlTaskLog
    from apps.crawler.services import CrawlerService, CRAWL_USER_AGENT
    from apps.crawler.validators import CrawlURLValidator

    try:
        crawl_doc = CrawledDocument.objects.get(id=crawled_document_id)
    except CrawledDocument.DoesNotExist:
        logger.error("CrawledDocument %s not found", crawled_document_id)
        return {"status": "error", "message": "CrawledDocument not found"}

    # Update status: fetching
    crawl_doc.crawl_status = "fetching"
    crawl_doc.save(update_fields=["crawl_status", "updated_at"])

    start_time = timezone.now()

    try:
        # Run async crawl via asyncio.run (works in prefork pool)
        service = CrawlerService()
        result = asyncio.run(service.crawl_url(crawl_doc.source_url))

        # Update crawl metadata
        crawl_doc.crawl_status = "parsing"
        crawl_doc.title_extracted = result["title"]
        crawl_doc.content_hash = result["content_hash"]
        crawl_doc.raw_content_size = result["raw_content_size"]
        crawl_doc.cleaned_content_size = result["cleaned_content_size"]
        crawl_doc.crawled_at = timezone.now()
        crawl_doc.robots_txt_allowed = True  # validated by service
        crawl_doc.save()

        # V4.1: Check for SimHash dedup — skip if duplicate found
        existing = CrawledDocument.objects.filter(
            content_hash=result["content_hash"],
            crawl_status="active",
        ).exclude(id=crawl_doc.id).first()
        if existing:
            crawl_doc.crawl_status = "duplicate_skipped"
            crawl_doc.error_message = f"Duplicate of CrawledDocument {existing.id}"
            crawl_doc.save(update_fields=["crawl_status", "error_message", "updated_at"])
            logger.info("Skipping duplicate crawl: %s matches %s", crawl_doc.id, existing.id)
            return {"status": "duplicate_skipped", "existing_id": str(existing.id)}

        # Create Document from crawled content
        crawl_doc.crawl_status = "embedding"
        crawl_doc.save(update_fields=["crawl_status", "updated_at"])

        from apps.knowledge.models import Document
        doc = Document.objects.create(
            title=result["title"] or crawl_doc.source_url[:200],
            file_type="html",
            file_size=result["cleaned_content_size"],
            uploaded_by=crawl_doc.submitted_by,
            status="processing",
        )
        crawl_doc.document = doc
        crawl_doc.save(update_fields=["document", "updated_at"])

        # Store cleaned text as temporary file for RAG pipeline ingestion
        # Write to temp file, then trigger existing ingest_document task
        tmp_file = tempfile.NamedTemporaryFile(
            suffix=".txt",
            delete=False,
            mode="w",
            encoding="utf-8",
        )
        tmp_file.write(result["extracted_text"])
        tmp_file.close()

        # Update Document file path to the temp file
        # Note: The RAG pipeline expects a file path, we store content as .txt
        doc.file = tmp_file.name
        doc.save(update_fields=["file"])

        # Trigger async ingestion via existing RAG pipeline
        from apps.rag.services import ingest_document
        ingest_document.delay(str(doc.id))

        # Mark as active
        crawl_doc.crawl_status = "active"
        crawl_doc.save(update_fields=["crawl_status", "updated_at"])

        # Create CrawlTaskLog
        processing_time_ms = int((timezone.now() - start_time).total_seconds() * 1000)
        CrawlTaskLog.objects.create(
            crawled_document=crawl_doc,
            target_domain=urlparse(crawl_doc.source_url).hostname or "",
            redirect_count=result["redirect_count"],
            final_url=result["final_url"],
            user_agent_used=CRAWL_USER_AGENT,
            processing_time_ms=processing_time_ms,
        )

        logger.info("Crawl completed: %s → Document %s", crawl_doc.source_url, doc.id)

        # Audit log
        from apps.audit.views import create_audit_log
        create_audit_log(
            user=crawl_doc.submitted_by,
            action="document_crawl",
            target_type="CrawledDocument",
            target_id=str(crawl_doc.id),
            details={
                "url": crawl_doc.source_url,
                "document_id": str(doc.id),
                "title": result["title"],
                "content_hash": result["content_hash"],
            },
            role_used="hr" if crawl_doc.submitted_by.has_role("hr") else "admin",
        )

        return {"status": "success", "document_id": str(doc.id)}

    except Exception as exc:
        crawl_doc.crawl_status = "failed"
        crawl_doc.error_message = str(exc)[:1000]
        crawl_doc.save(update_fields=["crawl_status", "error_message", "updated_at"])

        logger.error("Crawl failed for %s: %s", crawl_doc.source_url, exc, exc_info=True)

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


from urllib.parse import urlparse
