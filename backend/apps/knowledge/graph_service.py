"""Typed, permission-scoped knowledge graph projection service."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.core import signing
from django.db.models import Count, Q
from django.utils import timezone

from .freshness import compute_freshness, space_half_life_days
from .models import (
    Document,
    DocumentLink,
    DocumentSimilarity,
    DocumentTag,
    KnowledgeGraphState,
)


DEFAULT_NODE_LIMIT = 300
DEFAULT_EDGE_LIMIT = 1500
ALLOWED_EDGE_KINDS = {"links_to", "tagged_with", "similar_to"}
ALLOWED_INSIGHT_PRESETS = {
    "isolated",
    "unclassified",
    "stale",
    "missing_sources_or_approval",
}
GLOBAL_OVERVIEW_THRESHOLD = 300
GLOBAL_OVERVIEW_NODE_LIMIT = 150
GLOBAL_OVERVIEW_EDGE_LIMIT = 600


@dataclass(frozen=True)
class GraphQueryError(Exception):
    code: str
    detail: str
    position: int | None = None
    hint: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "detail": self.detail}
        if self.position is not None:
            payload["position"] = self.position
        if self.hint:
            payload["hint"] = self.hint
        return payload


def _document_node_id(document: Document) -> str:
    return f"doc:{document.lineage_id}"


def _term_node_id(term_id) -> str:
    return f"term:{term_id}"


def _ghost_node_id(link: DocumentLink) -> str:
    return f"ghost:{link.id}"


def _current_revision(space) -> int:
    state, _ = KnowledgeGraphState.objects.get_or_create(space=space)
    return int(state.revision)


def _normalize_query(payload: dict[str, Any], *, internal_raw: bool = False) -> dict[str, Any]:
    if payload.get("schema_version") != "graph.query.v1":
        raise GraphQueryError(
            "unsupported_schema_version",
            "schema_version must be graph.query.v1",
        )
    scope = payload.get("scope") or {"mode": "global"}
    if not isinstance(scope, dict):
        raise GraphQueryError("invalid_scope", "scope must be an object")
    mode = scope.get("mode", "global")
    if mode not in {"global", "local"}:
        raise GraphQueryError("invalid_scope", "scope.mode must be global or local")
    direction = scope.get("direction", "both")
    if direction not in {"in", "out", "both"}:
        raise GraphQueryError("invalid_direction", "scope.direction must be in, out, or both")
    try:
        depth = max(1, min(int(scope.get("depth", 1)), 3))
    except (TypeError, ValueError):
        raise GraphQueryError("invalid_depth", "scope.depth must be an integer from 1 to 3")
    edge_kinds = payload.get("edge_kinds") or ["links_to"]
    if not isinstance(edge_kinds, list) or not set(edge_kinds) <= ALLOWED_EDGE_KINDS:
        raise GraphQueryError("invalid_edge_kinds", "edge_kinds contains an unsupported relationship")
    limits = payload.get("limits") or {}
    try:
        max_nodes = 5000 if internal_raw else DEFAULT_NODE_LIMIT
        max_edges = 20000 if internal_raw else DEFAULT_EDGE_LIMIT
        node_limit = max(1, min(int(limits.get("nodes", DEFAULT_NODE_LIMIT)), max_nodes))
        edge_limit = max(1, min(int(limits.get("edges", DEFAULT_EDGE_LIMIT)), max_edges))
    except (TypeError, ValueError):
        raise GraphQueryError("invalid_limits", "limits.nodes and limits.edges must be integers")
    raw_groups = payload.get("groups") or []
    if not isinstance(raw_groups, list) or len(raw_groups) > 20:
        raise GraphQueryError("invalid_groups", "groups must be a list of at most 20 entries")
    groups = []
    for index, group in enumerate(raw_groups):
        if not isinstance(group, dict):
            raise GraphQueryError("invalid_groups", f"groups[{index}] must be an object")
        group_id = str(group.get("id") or "").strip()
        name = str(group.get("name") or "").strip()
        query = str(group.get("query") or "").strip()
        color = str(group.get("color") or "").strip()
        if not group_id or not name or not query or not color:
            raise GraphQueryError(
                "invalid_groups",
                f"groups[{index}] requires id, name, query, and color",
            )
        groups.append({"id": group_id, "name": name, "query": query, "color": color})
    insight_preset = str(payload.get("insight_preset") or "").strip()
    if insight_preset and insight_preset not in ALLOWED_INSIGHT_PRESETS:
        raise GraphQueryError("invalid_insight_preset", "insight_preset is not supported")
    return {
        "mode": mode,
        "center_id": scope.get("center_id"),
        "depth": depth,
        "direction": direction,
        "edge_kinds": list(dict.fromkeys(edge_kinds)),
        "include_ghosts": bool(payload.get("include_ghosts", False)),
        "node_limit": node_limit,
        "edge_limit": edge_limit,
        "query": str(payload.get("query") or "").strip(),
        "cursor": payload.get("cursor"),
        "groups": groups,
        "insight_preset": insight_preset,
    }


def _resolve_center(center_id: str | None, documents: list[Document]) -> str | None:
    if not center_id:
        return None
    raw = str(center_id)
    for document in documents:
        if raw in {str(document.id), str(document.lineage_id), _document_node_id(document)}:
            return _document_node_id(document)
    return None


def _query_overview(*, space, documents_qs, options, revision):
    """Return a bounded taxonomy overview for spaces too large to render raw."""
    document_ids = list(documents_qs.values_list("id", flat=True))
    total_documents = len(document_ids)
    term_rows = list(
        DocumentTag.objects.filter(document_id__in=document_ids, term__status="active")
        .values("term_id", "term__label", "term__code")
        .annotate(document_count=Count("document_id", distinct=True))
        .order_by("-document_count", "term__code")[: GLOBAL_OVERVIEW_NODE_LIMIT - 1]
    )
    selected_terms = {row["term_id"] for row in term_rows}
    cluster_by_document = {}
    for document_id, term_id in (
        DocumentTag.objects.filter(document_id__in=document_ids, term_id__in=selected_terms)
        .order_by("document_id", "term__code")
        .values_list("document_id", "term_id")
    ):
        cluster_by_document.setdefault(document_id, f"cluster:term:{term_id}")

    nodes = [
        {
            "id": f"cluster:term:{row['term_id']}",
            "type": "cluster",
            "label": row["term__label"],
            "resource_id": str(row["term_id"]),
            "properties": {"code": row["term__code"], "cluster_kind": "taxonomy"},
            "metrics": {"document_count": int(row["document_count"])},
        }
        for row in term_rows
    ]
    unclustered = total_documents - len(cluster_by_document)
    if unclustered or not nodes:
        nodes.append(
            {
                "id": "cluster:uncategorized",
                "type": "cluster",
                "label": "Uncategorized",
                "properties": {"cluster_kind": "uncategorized"},
                "metrics": {"document_count": max(unclustered, total_documents if not nodes else 0)},
            }
        )
        for document_id in document_ids:
            cluster_by_document.setdefault(document_id, "cluster:uncategorized")

    aggregate: dict[tuple[str, str, str, bool, str], int] = defaultdict(int)
    if "links_to" in options["edge_kinds"]:
        for source_id, target_id in DocumentLink.objects.filter(
            space=space, source_id__in=document_ids, target_id__in=document_ids
        ).values_list("source_id", "target_id"):
            source = cluster_by_document[source_id]
            target = cluster_by_document[target_id]
            if source != target:
                aggregate[(source, target, "links_to", True, "explicit")] += 1
    if "similar_to" in options["edge_kinds"]:
        for source_id, target_id in DocumentSimilarity.objects.filter(
            space=space, source_id__in=document_ids, target_id__in=document_ids
        ).values_list("source_id", "target_id"):
            source, target = sorted((cluster_by_document[source_id], cluster_by_document[target_id]))
            if source != target:
                aggregate[(source, target, "similar_to", False, "inferred")] += 1

    aggregate_items = sorted(aggregate.items(), key=lambda item: (-item[1], item[0]))
    edges = []
    for index, ((source, target, kind, directed, provenance), count) in enumerate(
        aggregate_items[:GLOBAL_OVERVIEW_EDGE_LIMIT]
    ):
        edges.append(
            {
                "id": f"aggregate:{kind}:{index}:{source}:{target}",
                "kind": kind,
                "source": source,
                "target": target,
                "directed": directed,
                "weight": float(count),
                "provenance": provenance,
                "evidence": {
                    "ref": f"aggregate:{kind}:{source}:{target}",
                    "summary": f"{count} relationships",
                    "count": count,
                },
            }
        )
    return {
        "schema_version": "graph.response.v1",
        "scope": {"mode": "global", "center_id": None, "depth": None, "direction": None},
        "nodes": nodes[:GLOBAL_OVERVIEW_NODE_LIMIT],
        "edges": edges,
        "meta": {
            "revision": revision,
            "overview": True,
            "total_documents": total_documents,
            "total_nodes": len(nodes),
            "total_edges": len(aggregate_items),
            "returned_nodes": min(len(nodes), GLOBAL_OVERVIEW_NODE_LIMIT),
            "returned_edges": len(edges),
            "truncated": True,
            "reasons": ["overview_aggregation"],
            "continuations": {},
            "missing_node_ids": [],
        },
    }


def query_graph(*, space, payload: dict[str, Any], internal_raw: bool = False) -> dict[str, Any]:
    options = _normalize_query(payload, internal_raw=internal_raw)
    revision = _current_revision(space)
    offset = 0
    if options["cursor"]:
        try:
            cursor_data = signing.loads(
                str(options["cursor"]), salt="knowledge.graph.cursor.v1"
            )
            offset = max(0, int(cursor_data.get("offset", 0)))
        except (signing.BadSignature, TypeError, ValueError):
            raise GraphQueryError("invalid_cursor", "The graph cursor is invalid")
        if int(cursor_data.get("revision", -1)) != revision:
            raise GraphQueryError(
                "graph_cursor_stale",
                "The graph changed while paging; refresh the scene before continuing",
            )
    half_life = space_half_life_days(space)
    documents_qs = Document.objects.filter(space=space, status__in=["active", "stale"])
    if options["query"]:
        from .graph_dsl import parse_graph_query

        documents_qs = documents_qs.filter(parse_graph_query(options["query"]))
    if options["insight_preset"] == "unclassified":
        documents_qs = documents_qs.filter(taxonomy_tags__isnull=True)
    elif options["insight_preset"] == "stale":
        stale_before = timezone.now() - timedelta(days=365)
        documents_qs = documents_qs.filter(Q(status="stale") | Q(updated_at__lt=stale_before))
    elif options["insight_preset"] == "missing_sources_or_approval":
        documents_qs = documents_qs.filter(
            Q(outgoing_links__isnull=True) | Q(review_requests__decision="pending")
        )
    if (
        options["mode"] == "global"
        and not options["query"]
        and not options["groups"]
        and not options["insight_preset"]
        and not options["cursor"]
        and not internal_raw
        and documents_qs.count() > GLOBAL_OVERVIEW_THRESHOLD
    ):
        return _query_overview(
            space=space,
            documents_qs=documents_qs,
            options=options,
            revision=revision,
        )
    documents = list(
        documents_qs
        .select_related("uploaded_by", "updated_by")
        .order_by("-updated_at", "id")
        .distinct()
    )
    group_by_document: dict[Any, dict[str, str]] = {}
    if options["groups"]:
        from .graph_dsl import parse_graph_query

        for group in options["groups"]:
            matching_ids = documents_qs.filter(
                parse_graph_query(group["query"])
            ).values_list("id", flat=True)
            for document_id in matching_ids:
                group_by_document.setdefault(document_id, group)
    document_ids = [document.id for document in documents]
    document_by_id = {document.id: document for document in documents}
    graph_id_by_resource = {
        document.id: _document_node_id(document) for document in documents
    }
    incoming_counts = dict(
        DocumentLink.objects.filter(space=space, target_id__in=document_ids)
        .values_list("target_id")
        .annotate(total=Count("id"))
        .values_list("target_id", "total")
    )

    nodes: dict[str, dict[str, Any]] = {}
    for document in documents:
        graph_id = graph_id_by_resource[document.id]
        nodes[graph_id] = {
            "id": graph_id,
            "type": "document",
            "label": document.title,
            "resource_id": str(document.id),
            "version": document.version,
            "properties": {
                "status": document.status,
                "file_type": document.file_type,
                "updated_at": document.updated_at,
                "owner": (
                    document.updated_by.get_username()
                    if document.updated_by_id
                    else document.uploaded_by.get_username()
                ),
                "freshness": compute_freshness(document, half_life_days=half_life),
            },
            "metrics": {"incoming_links": int(incoming_counts.get(document.id, 0))},
        }
        group = group_by_document.get(document.id)
        if group:
            nodes[graph_id]["properties"].update(
                {
                    "group_id": group["id"],
                    "group_name": group["name"],
                    "group_color": group["color"],
                }
            )

    edges: list[dict[str, Any]] = []
    if "links_to" in options["edge_kinds"]:
        links = DocumentLink.objects.filter(space=space, source_id__in=document_ids).select_related(
            "source", "target"
        )
        for link in links:
            source = graph_id_by_resource.get(link.source_id)
            if source is None:
                continue
            if link.target_id is None:
                if not options["include_ghosts"] or not link.unresolved_title:
                    continue
                target = _ghost_node_id(link)
                nodes[target] = {
                    "id": target,
                    "type": "ghost",
                    "label": link.unresolved_title,
                    "properties": {"unresolved": True},
                    "metrics": {},
                }
            else:
                target = graph_id_by_resource.get(link.target_id)
                if target is None:
                    continue
            edges.append(
                {
                    "id": f"link:{link.id}",
                    "kind": "links_to",
                    "source": source,
                    "target": target,
                    "directed": True,
                    "weight": 1.0,
                    "provenance": "explicit",
                    "evidence": {
                        "ref": f"link:{link.id}",
                        "summary": link.anchor_text or link.unresolved_title,
                        "count": max(1, link.occurrences.count()),
                    },
                }
            )

    if "tagged_with" in options["edge_kinds"]:
        tags = DocumentTag.objects.filter(
            document_id__in=document_ids, term__status="active"
        ).select_related("term")
        for tag in tags:
            source = graph_id_by_resource[tag.document_id]
            target = _term_node_id(tag.term_id)
            nodes.setdefault(
                target,
                {
                    "id": target,
                    "type": "term",
                    "label": tag.term.label,
                    "resource_id": str(tag.term_id),
                    "properties": {"code": tag.term.code},
                    "metrics": {},
                },
            )
            edges.append(
                {
                    "id": f"tag:{tag.id}",
                    "kind": "tagged_with",
                    "source": source,
                    "target": target,
                    "directed": True,
                    "weight": 1.0,
                    "provenance": "taxonomy",
                    "evidence": {
                        "ref": f"tag:{tag.id}",
                        "summary": tag.term.label,
                        "count": 1,
                    },
                }
            )

    if "similar_to" in options["edge_kinds"]:
        for similarity in DocumentSimilarity.objects.filter(
            space=space,
            source_id__in=document_ids,
            target_id__in=document_ids,
        ).order_by("-score"):
            edges.append(
                {
                    "id": f"similarity:{similarity.id}",
                    "kind": "similar_to",
                    "source": graph_id_by_resource[similarity.source_id],
                    "target": graph_id_by_resource[similarity.target_id],
                    "directed": False,
                    "weight": round(float(similarity.score), 4),
                    "provenance": "inferred",
                    "evidence": {
                        "ref": f"similarity:{similarity.id}",
                        "summary": f"Similarity {similarity.score:.2f}",
                        "count": 1,
                    },
                }
            )

    if options["insight_preset"] == "isolated":
        explicit_links = DocumentLink.objects.filter(space=space).filter(
            Q(source_id__in=document_ids) | Q(target_id__in=document_ids)
        )
        connected_document_ids = set(explicit_links.values_list("source_id", flat=True))
        connected_document_ids.update(
            target_id
            for target_id in explicit_links.values_list("target_id", flat=True)
            if target_id is not None
        )
        isolated_ids = {
            graph_id_by_resource[document_id]
            for document_id in document_ids
            if document_id not in connected_document_ids
        }
        nodes = {node_id: node for node_id, node in nodes.items() if node_id in isolated_ids}
        edges = []

    ordered_ids = list(nodes)
    center = None
    if options["mode"] == "local":
        center = _resolve_center(options["center_id"], documents)
        if center is None:
            raise GraphQueryError("center_not_found", "The local graph center is not visible in this space")
        forward: dict[str, list[str]] = defaultdict(list)
        reverse: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            forward[edge["source"]].append(edge["target"])
            reverse[edge["target"]].append(edge["source"])
            if not edge["directed"]:
                forward[edge["target"]].append(edge["source"])
                reverse[edge["source"]].append(edge["target"])
        reachable = {center}
        traversal_order = [center]
        queue = deque([(center, 0)])
        while queue:
            current, level = queue.popleft()
            if level >= options["depth"]:
                continue
            neighbors: list[str] = []
            if options["direction"] in {"out", "both"}:
                neighbors.extend(forward[current])
            if options["direction"] in {"in", "both"}:
                neighbors.extend(reverse[current])
            for neighbor in neighbors:
                if neighbor in reachable:
                    continue
                reachable.add(neighbor)
                traversal_order.append(neighbor)
                queue.append((neighbor, level + 1))
        ordered_ids = traversal_order
        edges = [
            edge
            for edge in edges
            if edge["source"] in reachable and edge["target"] in reachable
        ]

    total_nodes = len(ordered_ids)
    total_edges = len(edges)
    visible_ids = ordered_ids[offset : offset + options["node_limit"]]
    visible_set = set(visible_ids)
    visible_edges = [
        edge
        for edge in edges
        if edge["source"] in visible_set and edge["target"] in visible_set
    ][: options["edge_limit"]]
    truncated = total_nodes > offset + len(visible_ids) or total_edges > len(visible_edges)
    reasons = []
    if total_nodes > offset + len(visible_ids):
        reasons.append("node_limit")
    if total_edges > len(visible_edges):
        reasons.append("edge_limit")
    return {
        "schema_version": "graph.response.v1",
        "scope": {
            "mode": options["mode"],
            "center_id": center,
            "depth": options["depth"] if options["mode"] == "local" else None,
            "direction": options["direction"] if options["mode"] == "local" else None,
        },
        "nodes": [nodes[node_id] for node_id in visible_ids],
        "edges": visible_edges,
        "meta": {
            "revision": revision,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "returned_nodes": len(visible_ids),
            "returned_edges": len(visible_edges),
            "truncated": truncated,
            "reasons": reasons,
            "continuations": (
                {
                    "nodes": signing.dumps(
                        {"revision": revision, "offset": offset + len(visible_ids)},
                        salt="knowledge.graph.cursor.v1",
                        compress=True,
                    )
                }
                if total_nodes > offset + len(visible_ids)
                else {}
            ),
            "missing_node_ids": [],
            "insight_preset": options["insight_preset"] or None,
        },
    }


def find_paths(*, space, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "graph.path.v1":
        raise GraphQueryError("unsupported_schema_version", "schema_version must be graph.path.v1")
    edge_kinds = payload.get("edge_kinds") or ["links_to", "tagged_with"]
    if "similar_to" in edge_kinds and not payload.get("include_inferred", False):
        raise GraphQueryError("inferred_edges_disabled", "Set include_inferred to use similarity paths")
    graph = query_graph(
        space=space,
        payload={
            "schema_version": "graph.query.v1",
            "scope": {"mode": "global"},
            "edge_kinds": edge_kinds,
            "limits": {"nodes": 5000, "edges": 20000},
        },
        internal_raw=True,
    )
    node_by_id = {node["id"]: node for node in graph["nodes"]}

    def resolve(raw):
        value = str(raw or "")
        for node in graph["nodes"]:
            if value in {node["id"], node.get("resource_id")}:
                return node["id"]
        return None

    source = resolve(payload.get("source_id"))
    target = resolve(payload.get("target_id"))
    if source is None or target is None:
        raise GraphQueryError("path_endpoint_not_found", "Both path endpoints must be visible")
    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for edge in graph["edges"]:
        adjacency[edge["source"]].append((edge["target"], edge))
        if not edge["directed"] or edge["kind"] == "tagged_with":
            adjacency[edge["target"]].append((edge["source"], edge))
    try:
        max_paths = max(1, min(int(payload.get("max_paths", 3)), 3))
        max_depth = max(1, min(int(payload.get("max_depth", 8)), 12))
    except (TypeError, ValueError):
        raise GraphQueryError("invalid_path_limits", "max_paths and max_depth must be integers")
    queue = deque([(source, [source], [])])
    found = []
    expansions = 0
    while queue and len(found) < max_paths and expansions < 50000:
        current, node_ids, path_edges = queue.popleft()
        expansions += 1
        if current == target:
            found.append((node_ids, path_edges))
            continue
        if len(path_edges) >= max_depth:
            continue
        for neighbor, edge in adjacency[current]:
            if neighbor in node_ids:
                continue
            queue.append((neighbor, [*node_ids, neighbor], [*path_edges, edge]))
    paths = []
    for node_ids, path_edges in found:
        paths.append({"nodes": [node_by_id[node_id] for node_id in node_ids], "edges": path_edges})
    return {
        "schema_version": "graph.path.response.v1",
        "paths": paths,
        "meta": {**graph["meta"], "search_truncated": expansions >= 50000},
    }
