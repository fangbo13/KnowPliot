"""Fix review policy and trigger ingestion for uploaded test documents."""
import os, sys, django, json, time

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
django.setup()

from apps.spaces.models import KnowledgeSpace
from apps.knowledge.models import Document
from apps.knowledge.ingestion import enqueue_document_ingestion

SPACE_ID = "0cb246e8-c8a7-45eb-b70c-232e38e2bd04"

# 1) Change review policy to direct_publish
space = KnowledgeSpace.objects.get(pk=SPACE_ID)
print(f"Space: {space.name}")
print(f"  Current review_policy: {space.review_policy}")
space.review_policy = "direct_publish"
space.save(update_fields=["review_policy", "updated_at"])
print(f"  Updated review_policy: {space.review_policy}")

# 2) Find all pending_review documents in this space
pending_docs = Document.objects.filter(space=space, status="pending_review")
print(f"\nFound {pending_docs.count()} pending_review documents")

# 3) Trigger ingestion for each
doc_ids = []
for doc in pending_docs:
    print(f"\n  Triggering ingestion for: {doc.title} (id={doc.id})")
    print(f"    file_type={doc.file_type}, file_size={doc.file_size}")
    doc.status = "processing"
    doc.save(update_fields=["status", "updated_at"])
    try:
        enqueue_document_ingestion(doc, requested_by=doc.uploaded_by, trigger="test_reingest")
        print(f"    [OK] Ingestion enqueued")
        doc_ids.append(str(doc.id))
    except Exception as e:
        print(f"    [ERROR] {e}")
        doc.status = "failed"
        doc.processing_error = str(e)[:200]
        doc.save(update_fields=["status", "processing_error", "updated_at"])

print(f"\n--- Triggered ingestion for {len(doc_ids)} documents ---")
print(f"Doc IDs: {json.dumps(doc_ids)}")

# 4) Wait and poll status
print("\n--- Polling document statuses (max 5 minutes) ---")
start = time.time()
results = {}
while time.time() - start < 300:
    all_done = True
    for doc_id in doc_ids:
        if doc_id in results:
            continue
        doc = Document.objects.get(pk=doc_id)
        status = doc.status
        if status in ("active", "failed"):
            results[doc_id] = {
                "status": status,
                "chunk_count": doc.chunk_count,
                "processing_error": doc.processing_error or "",
                "elapsed": round(time.time() - start, 1),
            }
            print(f"  {doc.title}: {status} (chunks={doc.chunk_count}, elapsed={results[doc_id]['elapsed']}s)")
        else:
            all_done = False
    
    if all_done:
        break
    time.sleep(2)

# 5) Print final results
print("\n=== Final Results ===")
for doc_id in doc_ids:
    doc = Document.objects.get(pk=doc_id)
    r = results.get(doc_id, {})
    print(f"  {doc.title}")
    print(f"    id={doc.id}")
    print(f"    file_type={doc.file_type}, file_size={doc.file_size}")
    print(f"    status={doc.status}, chunk_count={doc.chunk_count}")
    print(f"    processing_error={doc.processing_error}")
    if doc_id in results:
        print(f"    elapsed={results[doc_id]['elapsed']}s")
    print()

print("Done.")
