# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §5 — visualization APIs (Phase 3).

    GET /api/v1/documents/graph/      — Local Graph nodes + 3 edge types
    GET /api/v1/documents/timeline/   — monthly/FY version activity heat data
    GET /api/v1/documents/dashboard/  — admin quality dashboard (L6 loop)

All endpoints resolve the active space from X-Space-Id; graph edges can never
cross spaces because every source query is space-filtered.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.spaces.permissions import (
    effective_space_role,
    is_platform_admin,
    resolve_request_space,
)

from .freshness import compute_freshness, space_half_life_days
from .models import (
    Document,
    DocumentChunk,
    DocumentLink,
    DocumentTag,
    ReviewRequest,
    TaxonomyTerm,
)

GRAPH_NODE_LIMIT = 300
SIMILAR_EDGE_THRESHOLD = 0.8
SIMILAR_EDGES_PER_NODE = 3
DASHBOARD_ROLES = {"owner", "space_admin"}


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def knowledge_graph(request):
    """Local Graph: document nodes + shared-term / explicit-link / similar edges.

    KB optimization spec §3.4: when ``center=<doc_id>`` is supplied, the result
    is restricted to the center document's neighborhood within ``depth`` hops
    (Obsidian local-graph semantics). Without ``center`` the full space graph is
    returned (global mode).
    """
    space = resolve_request_space(request)
    half_life = space_half_life_days(space)

    docs_qs = Document.objects.filter(
        space=space, status__in=["active", "stale"]
    ).order_by("-updated_at")
    term_filter = request.query_params.get("term")
    if term_filter:
        docs_qs = docs_qs.filter(taxonomy_tags__term__code=term_filter).distinct()
    docs = list(docs_qs[:GRAPH_NODE_LIMIT])
    doc_ids = [d.id for d in docs]
    id_set = {str(d.id) for d in docs}

    # Terms per document (node labels + shared-term edges).
    terms_by_doc: dict[str, list[str]] = defaultdict(list)
    docs_by_term: dict[str, list[str]] = defaultdict(list)
    for tag in DocumentTag.objects.filter(
        document_id__in=doc_ids, term__status="active"
    ).select_related("term"):
        terms_by_doc[str(tag.document_id)].append(tag.term.code)
        docs_by_term[tag.term.code].append(str(tag.document_id))

    # Incoming explicit links drive node size (被引用次数).
    incoming_counts = dict(
        DocumentLink.objects.filter(target_id__in=doc_ids)
        .values_list("target_id")
        .annotate(n=Count("id"))
        .values_list("target_id", "n")
    )

    nodes = [
        {
            "id": str(d.id),
            "title": d.title,
            "status": d.status,
            "version": d.version,
            "terms": sorted(terms_by_doc.get(str(d.id), [])),
            "freshness": compute_freshness(d, half_life_days=half_life),
            "incoming_links": int(incoming_counts.get(d.id, 0)),
            "updated_at": d.updated_at,
        }
        for d in docs
    ]

    edges = []
    seen_pairs = set()

    def _add_edge(src: str, tgt: str, kind: str, **extra):
        key = (min(src, tgt), max(src, tgt), kind)
        if src == tgt or key in seen_pairs:
            return
        seen_pairs.add(key)
        edges.append({"source": src, "target": tgt, "kind": kind, **extra})

    # 1) Explicit markdown links.
    for link in DocumentLink.objects.filter(
        space=space, source_id__in=doc_ids, target_id__in=doc_ids
    ):
        _add_edge(str(link.source_id), str(link.target_id), "link",
                  anchor=link.anchor_text)

    # 2) Shared controlled terms.
    for code, members in docs_by_term.items():
        members = [m for m in members if m in id_set]
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                _add_edge(members[i], members[j], "term", term=code)

    # 3) Embedding similarity — P1 §B2: read precomputed DocumentSimilarity
    # edges (refreshed at ingest from pooled document embeddings) instead of
    # O(n²) request-time cosine. Spaces without precomputed rows fall back to
    # the legacy on-the-fly path until their documents are re-ingested.
    from .models import DocumentSimilarity

    sim_rows = list(
        DocumentSimilarity.objects.filter(
            space=space, source_id__in=doc_ids, target_id__in=doc_ids
        )
        .order_by("-score")
        .values_list("source_id", "target_id", "score")
    )
    if sim_rows:
        per_node: dict[str, int] = defaultdict(int)
        for source_id, target_id, score in sim_rows:
            src, tgt = str(source_id), str(target_id)
            if per_node[src] >= SIMILAR_EDGES_PER_NODE or per_node[tgt] >= SIMILAR_EDGES_PER_NODE:
                continue
            _add_edge(src, tgt, "similar", score=round(score, 4))
            per_node[src] += 1
            per_node[tgt] += 1
    else:
        lead_embeddings: dict[str, list[float]] = {}
        for chunk in DocumentChunk.objects.filter(
            document_id__in=doc_ids, chunk_index=0, embedding__isnull=False
        ).only("document_id", "embedding"):
            if isinstance(chunk.embedding, list) and chunk.embedding:
                lead_embeddings[str(chunk.document_id)] = chunk.embedding
        emb_ids = list(lead_embeddings)
        for i, src in enumerate(emb_ids):
            scored = []
            for tgt in emb_ids[i + 1:]:
                sim = _cosine(lead_embeddings[src], lead_embeddings[tgt])
                if sim >= SIMILAR_EDGE_THRESHOLD:
                    scored.append((sim, tgt))
            scored.sort(reverse=True)
            for sim, tgt in scored[:SIMILAR_EDGES_PER_NODE]:
                _add_edge(src, tgt, "similar", score=round(sim, 4))

    return Response(_maybe_localize_graph(request, nodes, edges, term_filter))


def _maybe_localize_graph(request, nodes, edges, term_filter):
    """KB spec §3.4: restrict to a center document's BFS neighborhood if asked."""
    center = request.query_params.get("center")
    payload = {"nodes": nodes, "edges": edges, "term_filter": term_filter or None}
    if not center:
        payload["mode"] = "global"
        return payload
    try:
        depth = max(1, min(int(request.query_params.get("depth", 1) or 1), 3))
    except (TypeError, ValueError):
        depth = 1
    node_ids = {n["id"] for n in nodes}
    if center not in node_ids:
        # Center is outside the loaded window; return just the center marker.
        return {"nodes": [n for n in nodes if n["id"] == center], "edges": [],
                "term_filter": term_filter or None, "mode": "local", "center": center, "depth": depth}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        adjacency[e["source"]].add(e["target"])
        adjacency[e["target"]].add(e["source"])
    reachable = {center}
    frontier = {center}
    for _ in range(depth):
        nxt: set[str] = set()
        for node in frontier:
            nxt |= adjacency[node] - reachable
        reachable |= nxt
        frontier = nxt
        if not frontier:
            break
    local_nodes = [n for n in nodes if n["id"] in reachable]
    local_edges = [
        e for e in edges if e["source"] in reachable and e["target"] in reachable
    ]
    return {"nodes": local_nodes, "edges": local_edges,
            "term_filter": term_filter or None, "mode": "local",
            "center": center, "depth": depth}


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def document_backlinks(request, pk):
    """KB spec §3.4: Obsidian-style backlinks — documents linking TO this one."""
    space = resolve_request_space(request)
    try:
        document = Document.objects.get(pk=pk, space=space)
    except Document.DoesNotExist:
        raise PermissionDenied("Document not found in this space.")
    links = (
        DocumentLink.objects.filter(space=space, target=document)
        .select_related("source")
        .order_by("-created_at")
    )
    backlinks = [
        {
            "id": str(link.source_id),
            "title": link.source.title,
            "anchor_text": link.anchor_text,
            "status": link.source.status,
            "updated_at": link.source.updated_at,
        }
        for link in links
        if link.source.status in ["active", "stale", "pending_review"]
    ]
    return Response({"document_id": str(document.id), "backlinks": backlinks})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def knowledge_timeline(request):
    """Space-level version activity: monthly heat + FY aggregation."""
    space = resolve_request_space(request)
    months_back = min(int(request.query_params.get("months", 24) or 24), 60)
    since = timezone.now() - timedelta(days=31 * months_back)

    versions = Document.objects.filter(
        space=space, created_at__gte=since
    ).exclude(status__in=["draft", "failed"]).only(
        "id", "created_at", "version", "status", "parent_document_id"
    )
    monthly: dict[str, dict] = defaultdict(lambda: {"versions": 0, "new_documents": 0})
    for doc in versions:
        key = doc.created_at.strftime("%Y-%m")
        monthly[key]["versions"] += 1
        if doc.parent_document_id is None:
            monthly[key]["new_documents"] += 1

    # FY aggregation via fiscal_year taxonomy tags.
    fy_counts = (
        DocumentTag.objects.filter(
            document__space=space,
            term__dimension__code="fiscal_year",
        )
        .values("term__code", "term__label")
        .annotate(documents=Count("document_id", distinct=True))
        .order_by("term__code")
    )

    return Response(
        {
            "months": [
                {"month": key, **value} for key, value in sorted(monthly.items())
            ],
            "fiscal_years": [
                {
                    "code": row["term__code"],
                    "label": row["term__label"],
                    "documents": row["documents"],
                }
                for row in fy_counts
            ],
        }
    )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def knowledge_dashboard(request):
    """Admin dashboard: review backlog, coverage matrix, stale alerts, L6 metrics."""
    space = resolve_request_space(request)
    role = effective_space_role(request.user, space)
    if not is_platform_admin(request.user) and role not in DASHBOARD_ROLES:
        raise PermissionDenied("Dashboard requires knowledge admin rights.")

    half_life = space_half_life_days(space)
    now = timezone.now()
    today = now.date()

    # 1) Review backlog.
    pending = (
        ReviewRequest.objects.filter(space=space, decision="pending")
        .select_related("document", "submitted_by")
        .order_by("created_at")
    )
    review_backlog = [
        {
            "review_id": str(r.id),
            "document_id": str(r.document_id),
            "title": r.document.title,
            "version": r.document.version,
            "submitted_by": r.submitted_by.username or r.submitted_by.email,
            "submitted_at": r.created_at,
            "conflicts": len(r.conflict_hints or []),
        }
        for r in pending[:20]
    ]

    # 2) Coverage matrix: term × document count / average freshness.
    live_docs = {
        str(d.id): d
        for d in Document.objects.filter(space=space, status__in=["active", "stale"])
    }
    freshness_cache = {
        doc_id: compute_freshness(d, half_life_days=half_life)
        for doc_id, d in live_docs.items()
    }
    coverage = []
    tag_rows = DocumentTag.objects.filter(
        document_id__in=[d.id for d in live_docs.values()],
        term__status="active",
    ).select_related("term", "term__dimension")
    per_term: dict = defaultdict(list)
    term_meta: dict = {}
    for tag in tag_rows:
        per_term[str(tag.term_id)].append(str(tag.document_id))
        term_meta[str(tag.term_id)] = tag.term
    for term_id, doc_ids in per_term.items():
        term = term_meta[term_id]
        scores = [freshness_cache[i] for i in doc_ids if i in freshness_cache]
        coverage.append(
            {
                "term_id": term_id,
                "code": term.code,
                "label": term.label,
                "dimension": term.dimension.code,
                "documents": len(doc_ids),
                "avg_freshness": round(sum(scores) / len(scores), 4) if scores else None,
            }
        )
    # Uncovered active terms (knowledge gaps by construction).
    covered_ids = set(per_term)
    uncovered_terms = [
        {"code": t.code, "label": t.label, "dimension": t.dimension.code}
        for t in TaxonomyTerm.objects.filter(
            dimension__organization_id=space.organization_id, status="active"
        ).select_related("dimension")
        if str(t.id) not in covered_ids
    ][:50]

    # 3) Stale alerts: stale docs + effective_to expiring within 30 days.
    stale_docs = [
        {
            "id": str(d.id),
            "title": d.title,
            "status": d.status,
            "updated_at": d.updated_at,
            "freshness": freshness_cache.get(str(d.id)),
        }
        for d in live_docs.values()
        if d.status == "stale"
    ]
    expiring = [
        {
            "id": str(d.id),
            "title": d.title,
            "effective_to": d.effective_to,
        }
        for d in Document.objects.filter(
            space=space,
            status="active",
            effective_to__isnull=False,
            effective_to__lte=today + timedelta(days=30),
            effective_to__gte=today,
        )
    ]

    # 4) L6 quality metrics (last 30 days of assistant answers).
    from apps.chat.models import Message

    window_start = now - timedelta(days=30)
    answers = Message.objects.filter(
        space=space,
        role="assistant",
        is_current_version=True,
        created_at__gte=window_start,
    )
    total_answers = answers.count()
    label_counts = dict(
        answers.exclude(confidence_label="")
        .values_list("confidence_label")
        .annotate(n=Count("id"))
        .values_list("confidence_label", "n")
    )
    refusals = int(label_counts.get("insufficient", 0))
    needs_review = answers.filter(needs_human_review=True).count()

    from apps.audit.models import AuditLog

    def _audit_count(*actions):
        return AuditLog.objects.filter(
            action__in=actions,
            created_at__gte=window_start,
        ).filter(
            Q(details__space_id=str(space.id)) | Q(details__space=str(space.id))
        ).count()

    quality = {
        "window_days": 30,
        "total_answers": total_answers,
        "refusals": refusals,
        "refusal_rate": round(refusals / total_answers, 4) if total_answers else None,
        "needs_human_review": needs_review,
        "confidence_distribution": label_counts,
        "feedback_submitted": _audit_count("feedback_submit"),
        "knowledge_gaps_created": _audit_count("knowledge_gap_create"),
        "knowledge_gaps_resolved": _audit_count("knowledge_gap_resolve"),
    }

    return Response(
        {
            "review_backlog": review_backlog,
            "review_pending_count": pending.count(),
            "coverage": sorted(coverage, key=lambda x: (x["dimension"], x["code"])),
            "uncovered_terms": uncovered_terms,
            "stale_documents": stale_docs,
            "expiring_documents": expiring,
            "quality": quality,
        }
    )
