# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Lightweight reference-library routing (KB/RAG audit spec P2 §A1).

Previously every enabled reference library was searched on EVERY question,
letting large shared libraries (IFRS/CAS) inflate cost and crowd relevance.
This module decides which opted-in libraries a query should actually reach:

- the library NAME appears in the query, or
- the query hits the library's category keyword table.

Without any signal the query stays inside the primary space. The legacy
"search everything" behaviour remains available via the
``RAG_LIBRARY_ROUTING_ENABLED = False`` escape hatch.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Category → routing keywords (lowercase; CJK matched by substring).
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ifrs": (
        "ifrs", "ias", "ifric", "国际财务报告准则", "国际会计准则",
        "收入确认", "租赁", "金融工具", "减值", "合并报表", "准则",
    ),
    "cas": (
        "cas", "企业会计准则", "会计准则", "财会", "准则",
        "收入确认", "减值", "合并报表",
    ),
    "ipo_cases": (
        "ipo", "上市", "招股", "科创板", "创业板", "北交所", "案例",
    ),
    "other": (),
}


def route_reference_libraries(query: str, active_space) -> tuple[list[str], dict[str, str]]:
    """Return (library space ids, space_id → library name) for this query."""
    from apps.knowledge.models import ReferenceLibrary, SpaceLibraryReference

    references = list(
        SpaceLibraryReference.objects.filter(
            space=active_space,
            enabled=True,
            library__status=ReferenceLibrary.STATUS_PUBLISHED,
        ).select_related("library")
    )
    if not references:
        return [], {}

    routing_enabled = getattr(settings, "RAG_LIBRARY_ROUTING_ENABLED", True)
    query_lower = (query or "").lower()

    selected_ids: list[str] = []
    name_by_space: dict[str, str] = {}
    for reference in references:
        library = reference.library
        if routing_enabled:
            name_hit = bool(library.name) and library.name.lower() in query_lower
            keywords = CATEGORY_KEYWORDS.get(library.category, ())
            keyword_hit = any(keyword in query_lower for keyword in keywords)
            if not (name_hit or keyword_hit):
                continue
        space_id = str(library.space_id)
        selected_ids.append(space_id)
        name_by_space[space_id] = library.name

    if routing_enabled and len(selected_ids) < len(references):
        logger.info(
            "[library-routing] selected=%d/%d for query='%.40s'",
            len(selected_ids), len(references), query,
        )
    return selected_ids, name_by_space
