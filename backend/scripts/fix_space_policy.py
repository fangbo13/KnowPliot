"""Fix space review policy to direct_publish and clean old test documents."""
import os, sys, django, json

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
django.setup()

from apps.spaces.models import KnowledgeSpace
from apps.knowledge.models import Document, DocumentChunk

SPACE_ID = "0cb246e8-c8a7-45eb-b70c-232e38e2bd04"

# 1) Change review policy to direct_publish
space = KnowledgeSpace.objects.get(pk=SPACE_ID)
print(f"Space: {space.name}")
print(f"  Current review_policy: {space.review_policy}")
space.review_policy = "direct_publish"
space.save(update_fields=["review_policy", "updated_at"])
print(f"  Updated review_policy: {space.review_policy}")

# 2) List current documents in this space
docs = Document.objects.filter(space_id=SPACE_ID)
print(f"\nDocuments in space: {docs.count()}")
for d in docs:
    print(f"  {d.title} | status={d.status} | type={d.file_type} | size={d.file_size} | chunks={d.chunk_count}")

# 3) Delete old test documents (upload_test_* and edge_test_* and security_test_*)
old_docs = Document.objects.filter(
    space_id=SPACE_ID,
    title__startswith="upload_test_"
) | Document.objects.filter(
    space_id=SPACE_ID,
    title__startswith="edge_test_"
) | Document.objects.filter(
    space_id=SPACE_ID,
    title__startswith="security_test_"
)
count = old_docs.count()
print(f"\nDeleting {count} old test documents...")
for d in old_docs:
    # Delete chunks first
    DocumentChunk.objects.filter(document=d).delete()
    d.delete()
print(f"Deleted {count} documents.")

# 4) Also delete any remaining pending_review documents
pending = Document.objects.filter(space_id=SPACE_ID, status="pending_review")
pcount = pending.count()
print(f"\nDeleting {pcount} remaining pending_review documents...")
for d in pending:
    DocumentChunk.objects.filter(document=d).delete()
    d.delete()
print(f"Deleted {pcount} documents.")

print("\nDone. Space is now ready for fresh test uploads.")
