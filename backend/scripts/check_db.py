"""Check embedding status and processing times directly from DB."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
sys.path.insert(0, '/app')
django.setup()

from apps.knowledge.models import Document, DocumentChunk

docs = Document.objects.filter(title__startswith='upload_test_').order_by('title')
print(f'Found {docs.count()} test documents')
print('=' * 120)

for doc in docs:
    chunks = DocumentChunk.objects.filter(document=doc)
    total = chunks.count()
    with_emb = chunks.exclude(embedding__isnull=True).exclude(embedding=[]).count()
    
    # Check sample embedding
    sample = chunks.first()
    emb_info = 'None'
    if sample and sample.embedding:
        try:
            emb_info = f'len={len(sample.embedding)}'
        except:
            emb_info = f'type={type(sample.embedding).__name__}'
    
    # Check processing time fields
    created = doc.created_at
    updated = doc.updated_at
    # Calculate parse time
    parse_time = (updated - created).total_seconds() if updated and created else -1
    
    # Check for processing_time field
    proc_time = getattr(doc, 'processing_time', None)
    parsed_at = getattr(doc, 'parsed_at', None)
    
    # Check content_parsed field
    content_parsed = getattr(doc, 'content_parsed', None)
    content_parsed_len = len(content_parsed) if content_parsed else 0
    
    print(f'\n--- {doc.title} ---')
    print(f'  file_type={doc.file_type} | file_size={doc.file_size} | status={doc.status}')
    print(f'  chunk_count={doc.chunk_count} | DB chunks={total}')
    print(f'  created_at={created} | updated_at={updated}')
    print(f'  parse_time (updated-created): {parse_time:.3f}s')
    print(f'  processing_time field: {proc_time}')
    print(f'  parsed_at field: {parsed_at}')
    print(f'  content_parsed length: {content_parsed_len}')
    print(f'  with_embedding: {with_emb}/{total} | sample_embedding: {emb_info}')
    
    # Check chunk content quality
    first_chunk = chunks.order_by('chunk_index').first()
    if first_chunk:
        print(f'  first_chunk content[:200]: {first_chunk.content[:200]}')
        print(f'  first_chunk metadata: {first_chunk.metadata}')
        print(f'  first_chunk chunk_index: {first_chunk.chunk_index}')
        print(f'  first_chunk page_number: {first_chunk.page_number}')
