# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §5.1 — explicit markdown link extraction.

Parses ``[[Wiki Title]]`` and ``[text](knowpilot://doc/<uuid>)`` /
``[text](/documents/<uuid>)`` references from a document's canonical
``text_content`` and syncs them into ``DocumentLink`` rows.

KB/RAG audit spec P3:
- §B1 unresolved links: wiki titles with no matching document are stored as
  ``target=None`` rows and auto-resolve when a matching document appears;
- §B1 rename propagation: ``propagate_title_rename`` rewrites ``[[old]]``
  references across the space when a document is renamed;
- §B1 cross-library links: titles also resolve (read-only) against the
  published reference libraries this space has opted into.
"""

from __future__ import annotations

import logging
import re
import uuid

logger = logging.getLogger(__name__)

WIKI_LINK_RE = re.compile(r"\[\[([^\[\]|]{1,255})(?:\|([^\[\]]*))?\]\]")
DOC_ID_LINK_RE = re.compile(
    r"\[([^\]]{0,255})\]\((?:knowpilot://doc/|/documents/)"
    r"([0-9a-fA-F-]{36})\)?[^)]*\)?"
)
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)


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


def extract_link_occurrences(text: str) -> list[dict]:
    """Return every concrete link occurrence, including repeated targets."""
    occurrences = []
    for match in WIKI_LINK_RE.finditer(text or ""):
        title = match.group(1).strip()
        if not title:
            continue
        occurrences.append(
            {
                "syntax": "wikilink",
                "title": title,
                "anchor_text": (match.group(2) or title).strip(),
                "char_start": match.start(),
                "char_end": match.end(),
            }
        )
    for match in DOC_ID_LINK_RE.finditer(text or ""):
        try:
            target_id = str(uuid.UUID(match.group(2)))
        except ValueError:
            continue
        occurrences.append(
            {
                "syntax": "markdown",
                "target_id": target_id,
                "anchor_text": match.group(1).strip(),
                "char_start": match.start(),
                "char_end": match.end(),
            }
        )
    occurrences = sorted(occurrences, key=lambda item: item["char_start"])
    headings = [
        (match.start(), len(match.group(1)), match.group(2).strip())
        for match in MARKDOWN_HEADING_RE.finditer(text or "")
    ]
    for occurrence in occurrences:
        path: list[str] = []
        for position, level, title in headings:
            if position >= occurrence["char_start"]:
                break
            path = path[: level - 1]
            while len(path) < level - 1:
                path.append("")
            path.append(title)
        occurrence["heading_path"] = [title for title in path if title]
    return occurrences


def _linkable_space_ids(document) -> list:
    """Own space + opted-in published reference library spaces (P3 §B1)."""
    space_ids = [document.space_id]
    try:
        from .library_views import resolve_reference_space_ids

        if document.space is not None:
            space_ids.extend(resolve_reference_space_ids(document.space))
    except Exception:  # library resolution must never break link sync
        pass
    return space_ids


def sync_document_links(document) -> int:
    """Rebuild DocumentLink rows for one source document. Best-effort."""
    from .models import Document, DocumentLink, DocumentLinkOccurrence

    try:
        occurrences = extract_link_occurrences(document.text_content or "")
        titles = [item["title"] for item in occurrences if item["syntax"] == "wikilink"]
        id_refs = [
            (item["anchor_text"], item["target_id"])
            for item in occurrences
            if item["syntax"] == "markdown"
        ]
        space_ids = _linkable_space_ids(document)
        targets: dict = {}
        matched_titles: set[str] = set()
        if titles:
            candidates = Document.objects.filter(
                space_id__in=space_ids,
                title__in=titles,
                status__in=["active", "pending_review", "stale"],
            ).exclude(id=document.id)
            # Own-space documents win title conflicts against library docs.
            for target in sorted(
                candidates, key=lambda d: 0 if d.space_id == document.space_id else 1
            ):
                if target.title in matched_titles:
                    continue
                matched_titles.add(target.title)
                targets[str(target.id)] = (target, target.title)
        if id_refs:
            by_id = {
                str(d.id): d
                for d in Document.objects.filter(
                    space_id__in=space_ids,
                    id__in=[ref for _, ref in id_refs],
                ).exclude(id=document.id)
            }
            for anchor, ref in id_refs:
                if ref in by_id:
                    targets[ref] = (by_id[ref], anchor or by_id[ref].title)

        DocumentLink.objects.filter(source=document).delete()
        created_by_key = {
            ("target", str(target.id)): DocumentLink(
                space_id=document.space_id,
                source=document,
                target=target,
                anchor_text=(anchor or "")[:255],
            )
            for target, anchor in targets.values()
        }
        # P3 §B1: record unresolved wiki titles (Obsidian gray links).
        unresolved = sorted(
            {t for t in titles if t not in matched_titles}
        )
        created_by_key.update(
            {
                ("unresolved", title): DocumentLink(
                space_id=document.space_id,
                source=document,
                target=None,
                unresolved_title=title[:255],
                anchor_text=title[:255],
            )
            for title in unresolved
            }
        )
        created = list(created_by_key.values())
        if created:
            DocumentLink.objects.bulk_create(created, ignore_conflicts=True)
        occurrence_rows = []
        target_by_title = {
            target.title: target for target, _anchor in targets.values()
        }
        for ordinal, occurrence in enumerate(occurrences):
            if occurrence["syntax"] == "wikilink":
                target = target_by_title.get(occurrence["title"])
                key = (
                    ("target", str(target.id))
                    if target is not None
                    else ("unresolved", occurrence["title"])
                )
            else:
                key = ("target", occurrence["target_id"])
            link = created_by_key.get(key)
            if link is None:
                continue
            occurrence_rows.append(
                DocumentLinkOccurrence(
                    link=link,
                    ordinal=ordinal,
                    syntax=occurrence["syntax"],
                    anchor_text=occurrence["anchor_text"][:255],
                    char_start=occurrence["char_start"],
                    char_end=occurrence["char_end"],
                    heading_path=occurrence.get("heading_path", []),
                )
            )
        if occurrence_rows:
            DocumentLinkOccurrence.objects.bulk_create(occurrence_rows)
        return len(created)
    except Exception as exc:  # pragma: no cover — link sync must never break ingest
        logger.warning("sync_document_links failed for %s: %s", document.id, exc)
        return 0


def resolve_unresolved_links_to(document) -> int:
    """P3 §B1: re-sync sources whose unresolved links now match ``document``.

    Called after a document is created/ingested so gray links pointing at its
    title turn into real edges. Best-effort.
    """
    from .models import DocumentLink

    try:
        if not document.title or document.space_id is None:
            return 0
        sources = list(
            DocumentLink.objects.filter(
                space_id=document.space_id,
                target__isnull=True,
                unresolved_title=document.title,
            )
            .exclude(source=document)
            .select_related("source")
        )
        for link in sources:
            sync_document_links(link.source)
        return len(sources)
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "resolve_unresolved_links_to failed for %s: %s", document.id, exc
        )
        return 0


def propagate_title_rename(document, old_title: str, new_title: str) -> int:
    """P3 §B1: rewrite ``[[old_title]]`` references after a rename.

    Scans same-space documents whose ``text_content`` references the old
    title (plain and aliased wikilinks), rewrites them to the new title and
    re-syncs their links. Returns the number of updated documents.
    """
    from .models import Document

    if not old_title or not new_title or old_title == new_title:
        return 0
    try:
        referers = Document.objects.filter(
            space_id=document.space_id,
            status__in=["active", "pending_review", "stale", "draft"],
            text_content__contains=f"[[{old_title}",
        ).exclude(id=document.id)
        updated = 0
        for referer in referers:
            text = referer.text_content or ""
            rewritten = text.replace(f"[[{old_title}]]", f"[[{new_title}]]").replace(
                f"[[{old_title}|", f"[[{new_title}|"
            )
            if rewritten == text:
                continue
            referer.text_content = rewritten
            referer.save(update_fields=["text_content", "updated_at"])
            sync_document_links(referer)
            updated += 1
        # Gray links typed as the NEW title now resolve to this document.
        resolve_unresolved_links_to(document)
        return updated
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "propagate_title_rename failed for %s: %s", document.id, exc
        )
        return 0
