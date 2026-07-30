"""Inventory all knowledge spaces with doc/link counts (read-only)."""
import os
import sys

sys.path.insert(0, "/app")

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from apps.knowledge.models import Document, DocumentLink, ReferenceLibrary
from apps.spaces.models import KnowledgeSpace

print(f"{'ID':38} {'NAME':32} {'CODE':30} {'STATUS':10} DOCS LINKS")
for s in KnowledgeSpace.objects.order_by("created_at"):
    docs = Document.objects.filter(space=s).count()
    links = DocumentLink.objects.filter(space=s).count()
    print(f"{s.id} {s.name[:30]:32} {(s.code or '')[:28]:30} {s.status:10} {docs:4} {links:5}")

print("\n-- Reference libraries --")
for lib in ReferenceLibrary.objects.select_related("space"):
    print(f"{lib.name} [{lib.category}/{lib.status}] space={lib.space.code}")

print("\n-- Documents per space (titles) --")
for s in KnowledgeSpace.objects.order_by("created_at"):
    titles = list(Document.objects.filter(space=s).values_list("title", "status")[:15])
    if titles:
        print(f"\n[{s.name} / {s.code}]")
        for t, st in titles:
            print(f"   - {t[:60]} ({st})")
