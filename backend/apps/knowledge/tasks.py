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
    """Mark overdue active documents stale + notify term owners."""
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
        overdue = Document.objects.filter(
            space=space, status="active", updated_at__lt=cutoff
        )
        for doc in overdue:
            scanned += 1
            # last_reviewed_at (confirm-fresh) resets the clock without a new version.
            reviewed = getattr(doc, "last_reviewed_at", None)
            if reviewed is not None and reviewed >= cutoff:
                continue
            doc.status = "stale"
            doc.save(update_fields=["status", "updated_at"])
            marked += 1
            term_ids = list(
                DocumentTag.objects.filter(document=doc).values_list(
                    "term_id", flat=True
                )
            )
            owners = {
                o.owner.id: o.owner
                for o in TermOwnership.objects.filter(
                    space=space, term_id__in=term_ids
                ).select_related("owner")
            }
            for owner in owners.values():
                notify(
                    owner,
                    "document_stale",
                    f"文档已标记为陈旧：《{doc.title}》",
                    body=(
                        f"超过 {stale_after} 天未复核，已自动标记为 stale。"
                        "检索中将被降权，请复核内容或提交新版本。"
                    ),
                    level="warning",
                    link=f"/knowledge?document={doc.id}",
                    metadata={"document_id": str(doc.id)},
                )
    logger.info(
        "[stale-scan] scanned=%d marked_stale=%d at=%s", scanned, marked, now
    )
    return {"scanned": scanned, "marked_stale": marked}
