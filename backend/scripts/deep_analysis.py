"""Deep analysis: check pagination, embedding status, and PDF raw content issue."""
import json, requests, time, sys, os

BASE = 'http://localhost:8000/api/v1'
SPACE_ID = '0cb246e8-c8a7-45eb-b70c-232e38e2bd04'

# Login
r = requests.post(f'{BASE}/auth/token/', json={'email': 'auditor.xu@test.ey.com', 'password': 'Auditor#2026'}, timeout=10)
token = r.json()['access']
headers = {'Authorization': f'Bearer {token}', 'X-Space-Id': SPACE_ID}

# Get all documents
r = requests.get(f'{BASE}/documents/', headers=headers, timeout=30)
docs = r.json()
if isinstance(docs, dict):
    docs = docs.get('results', docs.get('items', []))

test_docs = [d for d in docs if d.get('title', '').startswith('upload_test_')]
test_docs.sort(key=lambda x: x.get('title', ''))

print(f'Test documents: {len(test_docs)}')
print('=' * 100)

for doc in test_docs:
    doc_id = doc['id']
    title = doc.get('title', '')
    file_type = doc.get('file_type', '')
    chunk_count = doc.get('chunk_count', 0)
    
    # Check pagination - get full chunk list
    all_chunks = []
    page = 1
    while True:
        r2 = requests.get(f'{BASE}/documents/{doc_id}/chunks/?page={page}', headers=headers, timeout=60)
        data = r2.json()
        if isinstance(data, dict):
            page_chunks = data.get('results', data.get('items', []))
            all_chunks.extend(page_chunks)
            # Check if there are more pages
            next_url = data.get('next')
            if not next_url or len(page_chunks) == 0:
                break
            page += 1
        else:
            all_chunks.extend(data)
            break
    
    # Check without pagination param
    r3 = requests.get(f'{BASE}/documents/{doc_id}/chunks/', headers=headers, timeout=60)
    no_page_data = r3.json()
    if isinstance(no_page_data, dict):
        no_page_chunks = no_page_data.get('results', no_page_data.get('items', []))
        no_page_count = len(no_page_chunks)
        has_next = no_page_data.get('next') is not None
        total_from_api = no_page_data.get('count', 'N/A')
    else:
        no_page_chunks = no_page_data
        no_page_count = len(no_page_chunks)
        has_next = False
        total_from_api = no_page_count
    
    print(f'\n--- {title} ---')
    print(f'  Document chunk_count field: {chunk_count}')
    print(f'  API chunks (no page param): {no_page_count}, has_next: {has_next}, total_from_api: {total_from_api}')
    print(f'  API chunks (all pages): {len(all_chunks)}')
    
    if len(all_chunks) != chunk_count:
        print(f'  *** MISMATCH: doc.chunk_count={chunk_count} vs api returned={len(all_chunks)}')
    
    # Check content of all chunks
    total_content = sum(len(c.get('content', '')) for c in all_chunks)
    print(f'  Total content chars (all chunks): {total_content}')
    
    # Check PDF raw content issue
    if file_type == 'pdf':
        first_content = all_chunks[0].get('content', '')[:200] if all_chunks else ''
        has_pdf_syntax = '%PDF' in first_content or 'endobj' in first_content or 'stream' in first_content
        print(f'  PDF raw syntax in content: {has_pdf_syntax}')
        print(f'  First 200 chars: {first_content}')
    
    # Check embedding via chunk metadata
    if all_chunks:
        chunk_keys = set(all_chunks[0].keys())
        print(f'  Chunk API keys: {sorted(chunk_keys)}')
        # Check if embedding exists in DB
        emb_count = sum(1 for c in all_chunks if c.get('embedding') is not None)
        print(f'  Chunks with embedding field non-null: {emb_count}/{len(all_chunks)}')
    
    # Check chunk metadata for quality
    if all_chunks:
        sample = all_chunks[0]
        chunk_type = sample.get('chunk_type', 'N/A')
        metadata = sample.get('metadata', {})
        print(f'  Sample chunk_type: {chunk_type}')
        print(f'  Sample metadata keys: {list(metadata.keys()) if isinstance(metadata, dict) else type(metadata).__name__}')
    
    print()

# Now check embeddings via Django ORM
print('\n' + '=' * 100)
print('EMBEDDING DATABASE CHECK')
print('=' * 100)

# Use Django shell to check embeddings directly
django_script = """
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
import sys
sys.path.insert(0, '/app')
django.setup()

from apps.knowledge.models import Document, DocumentChunk
from apps.workspaces.models import Workspace

# Get test documents
docs = Document.objects.filter(title__startswith='upload_test_').order_by('title')
for doc in docs:
    chunks = DocumentChunk.objects.filter(document=doc)
    total = chunks.count()
    with_emb = chunks.exclude(embedding__isnull=True).count()
    # Check if embedding column has actual values
    sample = chunks.first()
    has_emb = False
    emb_len = 0
    if sample and sample.embedding:
        has_emb = True
        emb_len = len(sample.embedding)
    print(f'{doc.title}: chunks={total}, with_embedding={with_emb}, sample_emb_len={emb_len}, has_emb={has_emb}')
"""
# Write to temp file and run
with open('/app/scripts/_check_emb.py', 'w') as f:
    f.write(django_script)
os.system('cd /app && python scripts/_check_emb.py')
