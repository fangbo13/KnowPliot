
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
