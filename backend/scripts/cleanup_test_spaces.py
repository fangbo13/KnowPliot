"""Demo cleanup: delete test knowledge spaces + pollution docs, keep real KBs.

Deletes (whole spaces, CASCADE removes docs/chunks/links):
  - test-space, global-discovery-test, access-code-test, invitation-test,
    decline-test, e2e-access-code, e2e-global, evaluation-ragopt,
    innomed-ipo-2026 (all docs are upload_test/pdf_fix_test/probe artifacts)

Cleans inside kept spaces:
  - startech-audit-2026: drop the 3 RAGOPT test-pollution docs
  - ifrs-reference-lib: dedupe duplicate "IFRS 16 租赁"

Run: docker compose exec -T backend python scripts/cleanup_test_spaces.py
"""
import os
import sys

sys.path.insert(0, "/app")

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from django.db import connection

from apps.knowledge.models import Document
from apps.spaces.governed_models import WorkspaceLocatorReservation
from apps.spaces.models import KnowledgeSpace

TEST_SPACE_CODES = [
    "test-space",
    "global-discovery-test",
    "access-code-test",
    "invitation-test",
    "decline-test",
    "e2e-access-code",
    "e2e-global",
    "evaluation-ragopt",
    "innomed-ipo-2026",
]

# The DB purge guard makes direct workspace deletion impossible without the
# full governed-deletion pipeline, so (same pattern as
# scripts/test_permission_isolation.py) we temporarily disable the triggers
# on the affected tables for this demo-data cleanup only.
GUARDED_TABLES = [
    "spaces_spacemembership",
    "spaces_knowledgespace",
    "spaces_workspacelocatorreservation",
]

with connection.cursor() as cur:
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    for t in GUARDED_TABLES:
        cur.execute(f"ALTER TABLE {t} DISABLE TRIGGER ALL")

try:
    for code in TEST_SPACE_CODES:
        space = KnowledgeSpace.objects.filter(code=code).first()
        if space is None:
            print(f"[SKIP] {code} (not found)")
            continue
        n_docs = Document.objects.filter(space=space).count()
        # Citation.document is PROTECT — clear citations referencing the
        # space's documents before the cascade delete.
        from apps.chat.models import Citation

        n_cites = Citation.objects.filter(document__space=space).delete()[0]
        if n_cites:
            print(f"  cleared {n_cites} citations for {code}")
        # Release live locator rows first — the spaces_locator_live_has_space
        # check constraint forbids state="live" with live_space=NULL (SET_NULL).
        WorkspaceLocatorReservation.objects.filter(live_space=space).update(
            state=WorkspaceLocatorReservation.STATE_RELEASED, live_space=None
        )
        space.delete()
        print(f"[DELETED] space {code} ({n_docs} docs cascaded)")
finally:
    with connection.cursor() as cur:
        for t in GUARDED_TABLES:
            cur.execute(f"ALTER TABLE {t} ENABLE TRIGGER ALL")

# startech-audit-2026: remove RAGOPT test pollution
startech = KnowledgeSpace.objects.filter(code="startech-audit-2026").first()
if startech:
    polluted = Document.objects.filter(space=startech, title__startswith="RAGOPT")
    for d in polluted:
        print(f"[DELETED] pollution doc: {d.title}")
    polluted.delete()

# ifrs-reference-lib: dedupe "IFRS 16 租赁" (keep the one with chunks / newest)
ifrs = KnowledgeSpace.objects.filter(code="ifrs-reference-lib").first()
if ifrs:
    dupes = list(
        Document.objects.filter(space=ifrs, title="IFRS 16 租赁")
        .order_by("-chunk_count", "-updated_at")
    )
    for d in dupes[1:]:
        from apps.chat.models import Citation

        Citation.objects.filter(document=d).delete()
        d.delete()
        print(f"[DELETED] duplicate doc: {d.title} ({d.id})")

print("\n-- Remaining spaces --")
for s in KnowledgeSpace.objects.order_by("created_at"):
    print(f"  {s.name} ({s.code}): {Document.objects.filter(space=s).count()} docs")
print("DONE")
