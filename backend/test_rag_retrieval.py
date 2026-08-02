"""Test RAG retrieval from the audit knowledge base reference library.

This test uses explicit library selection (resolve_selected_libraries),
simulating what happens when a user selects the library in the chat UI.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from apps.rag.retriever import PgVectorRetriever
from apps.rag.embedding import EmbeddingService
from apps.rag.library_routing import resolve_selected_libraries
from apps.spaces.models import KnowledgeSpace

# 个人工作区 (active space)
space_id = "a5e80313-11a3-4e00-84a5-e64f3838d589"
space = KnowledgeSpace.objects.get(id=space_id)
print(f"Active space: {space.name}")

# Explicit library selection (simulates user selecting "审计知识库" in chat UI)
# This is the library_id (not space_id)
selected_library_ids = ["d68a76cb-10e1-4e37-8e56-188492e46a0f"]
lib_ids, name_map = resolve_selected_libraries(space, selected_library_ids, max_count=5)
print(f"Selected libraries resolved: {len(lib_ids)}")
for sid, name in name_map.items():
    print(f"  - {name} (space_id={sid})")

# Build search space list (main space + selected libraries)
all_space_ids = [space_id] + lib_ids
print(f"Search space_ids: {all_space_ids}")

# Create retriever with embedder
embedder = EmbeddingService()
retriever = PgVectorRetriever(embedder=embedder)

# Test 1: Query about audit principles
query = "审计的基本原则是什么？"
print(f"\n{'='*60}")
print(f"Query: {query}")
print("Searching...")
results = retriever.search(query, space_id=space_id, space_ids=all_space_ids, top_k=4)
print(f"\nFound {len(results)} results:")
for i, r in enumerate(results):
    print(f"\n--- Result {i+1} ---")
    print(f"Score: {r.get('score', 'N/A')}")
    print(f"Space ID: {r.get('space_id', 'N/A')}")
    print(f"Document ID: {r.get('document_id', 'N/A')}")
    content = r.get("content", r.get("text", ""))
    print(f"Content (first 300 chars): {content[:300]}")

# Test 2: Query about audit process
query2 = "审计流程包括哪些步骤？"
print(f"\n{'='*60}")
print(f"Query: {query2}")
print("Searching...")
results2 = retriever.search(query2, space_id=space_id, space_ids=all_space_ids, top_k=4)
print(f"\nFound {len(results2)} results:")
for i, r in enumerate(results2):
    print(f"\n--- Result {i+1} ---")
    print(f"Score: {r.get('score', 'N/A')}")
    print(f"Space ID: {r.get('space_id', 'N/A')}")
    content = r.get("content", r.get("text", ""))
    print(f"Content (first 300 chars): {content[:300]}")

# Test 3: Full RAG generation
print(f"\n{'='*60}")
print("Testing full RAG generation (retrieve_and_generate)...")
from apps.rag.pipeline import RAGPipeline

pipeline = RAGPipeline()
pipeline.selected_library_ids = selected_library_ids

class SimpleUser:
    id = "a564bc0c-ede9-471b-af02-791b411cd72a"
    email = "fath@ey.com"
    username = "fath@ey.com"
    language_preference = "zh"

query3 = "审计的基本原则是什么？"
print(f"Query: {query3}")
print("Generating response...")
response_chunks = []
for event in pipeline.retrieve_and_generate(
    query3,
    SimpleUser(),
    [],
    space_id=space_id,
    language="zh",
):
    response_chunks.append(event)
    if event.get("event") == "token":
        print(event.get("data", ""), end="")
    elif event.get("event") == "sources":
        print(f"\n\nSources: {event.get('data', '')}")
    elif event.get("event") == "error":
        print(f"\nERROR: {event.get('data', '')}")
    elif event.get("event") == "degraded":
        print(f"\nDEGRADED: {event.get('data', '')}")

print(f"\n\nTotal events: {len(response_chunks)}")
