# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §5.1 — explicit markdown link extraction.

Parses ``[[Wiki Title]]`` and ``[text](knowpilot://doc/<uuid>)`` /
``[text](/documents/<uuid>)`` references from a document's canonical
``text_content`` and syncs them into ``DocumentLink`` rows (same-space only,
so graph edges can never cross the space isolation boundary).
"""

from __future__ import annotations

import logging
import re
import uuid

logger = logging.getLogger(__name__)

WIKI_LINK_RE = re.compile(r"\[\[([^\[\]|]{1,255})(?:\|[^\[\]]*)?\]\]")
DOC_ID_LINK_RE = re.compile(
    r"\[([^\]]{0,255})\]\((?:knowpilot://doc/|/documents/)"
    r"([0-9a-fA-F-]{36})\)?[^)]*\)?"
)


def extract_link_targets(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Return ([wiki titles], [(anchor_text, document uuid)]) found in text."""
    if not text:
        return [], []
    titles = [m.group(1).strip() for m in WIKI_LINK_RE.finditer(text)]
    id_refs = []
    for m in DOC_ID_LINK_RE.finditer(text):
        try:
            id_refs.append((m.group(1).strip(), str(uuid.UUID(m.group(2)))))
        except ValueError:
            continue
    return [t for t in titles if t], id_refs


def sync_document_links(document) -> int:
    """Rebuild DocumentLink rows for one source document. Best-effort."""
    from .models import Document, DocumentLink

    try:
        titles, id_refs = extract_link_targets(document.text_content or "")
        targets: dict = {}
        if titles:
            for target in Document.objects.filter(
                space_id=document.space_id,
                title__in=titles,
                status__in=["active", "pending_review", "stale"],
            ).exclude(id=document.id):
                targets[str(target.id)] = (target, target.title)
        if id_refs:
            by_id = {
                str(d.id): d
                for d in Document.objects.filter(
                    space_id=document.space_id,
                    id__in=[ref for _, ref in id_refs],
                ).exclude(id=document.id)
            }
            for anchor, ref in id_refs:
                if ref in by_id:
                    targets[ref] = (by_id[ref], anchor or by_id[ref].title)

        DocumentLink.objects.filter(source=document).delete()
        created = [
            DocumentLink(
                space_id=document.space_id,
                source=document,
                target=target,
                anchor_text=(anchor or "")[:255],
            )
            for target, anchor in targets.values()
        ]
        if created:
            DocumentLink.objects.bulk_create(created, ignore_conflicts=True)
        return len(created)
    except Exception as exc:  # pragma: no cover — link sync must never break ingest
        logger.warning("sync_document_links failed for %s: %s", document.id, exc)
        return 0
