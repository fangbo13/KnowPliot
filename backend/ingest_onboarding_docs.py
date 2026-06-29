"""Bulk ingest knowledge documents (crawled + custom onboarding docs)."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
django.setup()

from apps.knowledge.models import Document, DocumentCategory, DocumentChunk
from django.contrib.auth import get_user_model
from apps.rag.pipeline import RAGPipeline

User = get_user_model()
admin_user = User.objects.get(username="admin")

cat, _ = DocumentCategory.objects.get_or_create(
    slug='general',
    defaults={'name': 'General', 'description': 'EY onboarding knowledge'}
)

# Also create specific categories for onboarding docs
it_cat, _ = DocumentCategory.objects.get_or_create(
    slug='it-setup',
    defaults={'name': 'IT Setup', 'description': 'IT setup and email configuration guides'}
)
hr_cat, _ = DocumentCategory.objects.get_or_create(
    slug='hr-policies',
    defaults={'name': 'HR Policies', 'description': 'HR policies: reimbursement, leave, training'}
)
office_cat, _ = DocumentCategory.objects.get_or_create(
    slug='office-team',
    defaults={'name': 'Office & Team', 'description': 'Office location, buddy/mentor guidance'}
)

# Map filenames to categories
category_map = {
    '01_IT_setup': it_cat,
    '02_reimbursement': hr_cat,
    '03_annual_leave': hr_cat,
    '04_training_courses': hr_cat,
    '05_office_location': office_cat,
    '06_buddy_mentor': office_cat,
}

base_dir = '/app/knowledge_docs'
if not os.path.exists(base_dir):
    print(f'Directory {base_dir} not found, skipping custom docs')
else:
    files = sorted([f for f in os.listdir(base_dir) if f.endswith('.md')])
    print(f'Found {len(files)} custom knowledge files to ingest')

    pipeline = RAGPipeline()
    total_chunks = 0
    errors = []

    for i, fname in enumerate(files):
        filepath = os.path.join(base_dir, fname)
        title = fname.replace('.md', '').replace('_', ' ')

        # Determine category
        prefix = fname.split('_')[0] + '_' + fname.split('_')[1]
        doc_cat = category_map.get(prefix, cat)

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        file_size = len(content.encode('utf-8'))

        doc = Document.objects.create(
            title=title,
            category=doc_cat,
            file_type='txt',
            file_size=file_size,
            uploaded_by=admin_user,
            status='pending',
        )

        doc_dir = '/app/media/knowledge'
        os.makedirs(doc_dir, exist_ok=True)
        doc_path = os.path.join(doc_dir, f'{doc.id}.md')
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(content)

        doc.file = f'knowledge/{doc.id}.md'
        doc.save(update_fields=['file'])

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
print('=== Final Knowledge Base Summary ===')
print(f'Documents: {Document.objects.count()}')
print(f'Completed: {Document.objects.filter(status="completed").count()}')
print(f'Failed: {Document.objects.filter(status="failed").count()}')
print(f'Chunks: {DocumentChunk.objects.count()}')
print(f'Categories: {DocumentCategory.objects.count()}')
