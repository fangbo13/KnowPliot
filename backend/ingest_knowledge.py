# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Bulk ingest crawled knowledge documents into RAG pipeline."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
django.setup()

from apps.knowledge.models import Document, DocumentCategory, DocumentChunk
from django.contrib.auth import get_user_model
from apps.rag.pipeline import RAGPipeline

# Get admin user
User = get_user_model()
admin_user = User.objects.get(username="admin")

# Create default category
cat, _ = DocumentCategory.objects.get_or_create(
    name='General',
    defaults={'description': 'EY onboarding knowledge'}
)

base_dir = '/app/crawled_knowledge/pages'
files = sorted([f for f in os.listdir(base_dir) if f.endswith('.md')])
print(f'Found {len(files)} markdown files to ingest')

pipeline = RAGPipeline()
total_chunks = 0
errors = []

for i, fname in enumerate(files):
    filepath = os.path.join(base_dir, fname)
    title = fname.replace('.md', '').replace('page_', 'Page ').replace('_', ' ')

    # Read file content first to get size
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    file_size = len(content.encode('utf-8'))

    # Create Document record with all required fields
    doc = Document.objects.create(
        title=title,
        category=cat,
        file_type='txt',
        file_size=file_size,
        uploaded_by=admin_user,
        status='pending',
    )

    # Write content to doc file path
    doc_dir = '/app/media/knowledge'
    os.makedirs(doc_dir, exist_ok=True)
    doc_path = os.path.join(doc_dir, f'{doc.id}.md')
    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(content)

    doc.file = f'knowledge/{doc.id}.md'
    doc.save(update_fields=['file'])

    # Ingest through RAG pipeline
    try:
        chunks = pipeline.ingest(doc)
        if chunks:
            doc.status = 'completed'
            doc.save(update_fields=['status'])
            total_chunks += len(chunks)
            print(f'  [{i+1}/{len(files)}] OK: {title} -> {len(chunks)} chunks')
        else:
            doc.status = 'failed'
            doc.save(update_fields=['status'])
            print(f'  [{i+1}/{len(files)}] FAIL: {title} -> 0 chunks')
    except Exception as e:
        doc.status = 'failed'
        doc.processing_error = str(e)[:200]
        doc.save(update_fields=['status', 'processing_error'])
        errors.append((title, str(e)[:100]))
        print(f'  [{i+1}/{len(files)}] ERROR: {title} -> {str(e)[:100]}')

print()
print('=== Summary ===')
print(f'Documents: {Document.objects.count()}')
print(f'Completed: {Document.objects.filter(status="completed").count()}')
print(f'Failed: {Document.objects.filter(status="failed").count()}')
print(f'Total chunks: {total_chunks}')
print(f'Chunk records: {DocumentChunk.objects.count()}')
if errors:
    print(f'Errors: {len(errors)}')
