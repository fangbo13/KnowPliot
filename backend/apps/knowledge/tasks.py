# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §4 L3 — freshness automation.

Nightly scan: active documents not reviewed within the space's
``stale_after_days`` window automatically become ``stale``. Stale documents
stay retrievable but are downweighted (HybridRetriever) and their citations
carry a "内容可能过期" badge. Term owners are notified so the L6 loop
(提问暴露缺口 → 负责人补充 → 审批入库) can close.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="apps.knowledge.tasks.scan_stale_documents")
def scan_stale_documents() -> dict:
    """Mark overdue active documents stale + notify term owners.

    P1 §B4: batched — one filtered query + bulk ``update()`` per space and
    one merged notification per owner, replacing the per-document
    ``save()``/``notify()`` loop. The bulk update also fixes a freshness bug:
    the old ``save(update_fields=[..., "updated_at"])`` refreshed the
    auto_now clock, making just-marked stale documents look newly edited.
    """
    from django.db.models import Q

    from apps.notifications.services import notify
    from apps.spaces.models import KnowledgeSpace

    from .freshness import space_stale_after_days
    from .models import Document, DocumentTag, TermOwnership

    now = timezone.now()
    scanned = 0
    marked = 0
    for space in KnowledgeSpace.objects.filter(status="active"):
        stale_after = space_stale_after_days(space)
        cutoff = now - timedelta(days=stale_after)
        overdue_qs = Document.objects.filter(
            space=space, status="active", updated_at__lt=cutoff
        ).filter(
            # last_reviewed_at (confirm-fresh) resets the clock without a new version.
            Q(last_reviewed_at__isnull=True) | Q(last_reviewed_at__lt=cutoff)
        )
        overdue = list(overdue_qs.only("id", "title"))
        scanned += len(overdue)
        if not overdue:
            continue
        overdue_ids = [doc.id for doc in overdue]
        marked += Document.objects.filter(id__in=overdue_ids).update(status="stale")

        # Merge notifications: one message per owner covering all their docs.
        titles_by_id = {doc.id: doc.title for doc in overdue}
        docs_by_owner: dict = {}
        owner_by_id: dict = {}
        tag_rows = DocumentTag.objects.filter(
            document_id__in=overdue_ids
        ).values_list("document_id", "term_id")
        term_ids = {term_id for _, term_id in tag_rows}
        owners_by_term: dict = {}
        for ownership in TermOwnership.objects.filter(
            space=space, term_id__in=term_ids
        ).select_related("owner"):
            owners_by_term.setdefault(ownership.term_id, []).append(ownership.owner)
        for document_id, term_id in tag_rows:
            for owner in owners_by_term.get(term_id, []):
                owner_by_id[owner.id] = owner
                docs_by_owner.setdefault(owner.id, set()).add(document_id)
        for owner_id, doc_ids in docs_by_owner.items():
            titles = [titles_by_id[d] for d in list(doc_ids)[:5]]
            listed = "、".join(f"《{t}》" for t in titles)
            extra = f" 等 {len(doc_ids)} 篇" if len(doc_ids) > len(titles) else ""
            notify(
                owner_by_id[owner_id],
                "document_stale",
                f"{len(doc_ids)} 篇文档已标记为陈旧",
                body=(
                    f"{listed}{extra}超过 {stale_after} 天未复核，已自动标记为 stale。"
                    "检索中将被降权，请复核内容或提交新版本。"
                ),
                level="warning",
                link="/knowledge?status=stale",
                metadata={"document_ids": [str(d) for d in doc_ids]},
            )
    logger.info(
        "[stale-scan] scanned=%d marked_stale=%d at=%s", scanned, marked, now
    )
    return {"scanned": scanned, "marked_stale": marked}


@shared_task(name="apps.knowledge.tasks.purge_superseded_chunks")
def purge_superseded_chunks() -> dict:
    """KB/RAG audit spec P3 §B4: reclaim chunks of long-dead document versions.

    Superseded/archived documents are excluded from retrieval but their
    chunks (and pgvector rows) linger forever. Rollback re-chunks from
    ``text_content``, so chunks of versions past the retention window can be
    dropped safely.
    """
    from django.conf import settings

    from .models import Document, DocumentChunk

    retention_days = int(
        getattr(settings, "KNOWLEDGE_SUPERSEDED_CHUNK_RETENTION_DAYS", 30)
    )
    cutoff = timezone.now() - timedelta(days=retention_days)
    doc_ids = list(
        Document.objects.filter(
            status__in=["superseded", "archived"], updated_at__lt=cutoff
        ).values_list("id", flat=True)
    )
    deleted = 0
    if doc_ids:
        from apps.chat.models import Citation
        # Detach Citation references before deleting chunks to avoid
        # ProtectedError from Citation.chunk (on_delete=PROTECT).
        Citation.objects.filter(chunk__document_id__in=doc_ids).update(chunk=None)
        deleted, _ = DocumentChunk.objects.filter(document_id__in=doc_ids).delete()
    logger.info(
        "[chunk-purge] documents=%d chunks_deleted=%d retention_days=%d",
        len(doc_ids), deleted, retention_days,
    )
    return {"documents": len(doc_ids), "chunks_deleted": deleted}


@shared_task(name="apps.knowledge.tasks.backfill_document_similarities")
def backfill_document_similarities(space_id: str | None = None) -> dict:
    """P1 §B2: backfill pooled embeddings + similarity edges for existing docs.

    Newly ingested documents refresh their own edges; this task covers the
    stock of documents ingested before the DocumentSimilarity table existed.
    Also backfills the CJK ``content_tokens`` column (P1 §A6) for old chunks.
    """
    from apps.rag.cjk import cjk_token_text

    from .models import Document, DocumentChunk
    from .similarity import refresh_document_similarity

    docs = Document.objects.filter(status__in=["active", "stale"])
    if space_id:
        docs = docs.filter(space_id=space_id)
    refreshed = 0
    edges = 0
    tokens_backfilled = 0
    for doc in docs.iterator():
        edges += refresh_document_similarity(doc)
        refreshed += 1
        pending_chunks = list(
            DocumentChunk.objects.filter(document=doc, content_tokens="")
            .only("id", "content")
        )
        for chunk in pending_chunks:
            chunk.content_tokens = cjk_token_text(f"{doc.title}\n{chunk.content}")
        if pending_chunks:
            DocumentChunk.objects.bulk_update(
                pending_chunks, ["content_tokens"], batch_size=200
            )
            tokens_backfilled += len(pending_chunks)
    logger.info(
        "[similarity-backfill] documents=%d edges=%d chunk_tokens=%d",
        refreshed, edges, tokens_backfilled,
    )
    return {
        "documents": refreshed,
        "edges": edges,
        "chunk_tokens": tokens_backfilled,
    }
