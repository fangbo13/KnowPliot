"""Check graph connectivity per space: BFS over link+term+similar edges."""
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/app")

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from apps.knowledge.models import Document, DocumentLink, DocumentSimilarity, DocumentTag
from apps.spaces.models import KnowledgeSpace

for space in KnowledgeSpace.objects.order_by("created_at"):
    docs = list(
        Document.objects.filter(space=space, status__in=["active", "stale"])
        .values_list("id", "title")
    )
    if not docs:
        continue
    ids = {str(i) for i, _ in docs}
    adj = defaultdict(set)

    for s, t in DocumentLink.objects.filter(
        space=space, source_id__in=[i for i, _ in docs], target__isnull=False
    ).values_list("source_id", "target_id"):
        adj[str(s)].add(str(t))
        adj[str(t)].add(str(s))
    for s, t in DocumentSimilarity.objects.filter(space=space).values_list(
        "source_id", "target_id"
    ):
        if str(s) in ids and str(t) in ids:
            adj[str(s)].add(str(t))
            adj[str(t)].add(str(s))
    by_term = defaultdict(list)
    for d, code in DocumentTag.objects.filter(
        document_id__in=[i for i, _ in docs], term__status="active"
    ).values_list("document_id", "term__code"):
        by_term[code].append(str(d))
    for members in by_term.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                adj[members[i]].add(members[j])
                adj[members[j]].add(members[i])

    # BFS components
    seen = set()
    components = []
    for node in ids:
        if node in seen:
            continue
        comp = {node}
        frontier = [node]
        while frontier:
            cur = frontier.pop()
            for nb in adj[cur]:
                if nb in ids and nb not in comp:
                    comp.add(nb)
                    frontier.append(nb)
        seen |= comp
        components.append(comp)
    components.sort(key=len, reverse=True)
    title_by_id = {str(i): t for i, t in docs}
    print(f"\n{space.name} ({space.code}): {len(docs)} nodes, "
          f"{len(components)} component(s), largest={len(components[0])}")
    for comp in components[1:]:
        for node in comp:
            print(f"   ISOLATED/small comp: {title_by_id[node]}")
