import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.spaces.models import KnowledgeSpace, SpaceMembership
from apps.knowledge.models import Document, DocumentChunk
from django.contrib.auth import get_user_model
User = get_user_model()

u = User.objects.get(email='fath@ey.com')
print('=== fath@ey.com memberships ===')
for m in SpaceMembership.objects.filter(user=u).select_related('space'):
    print(f'  space={m.space.name} | role={m.role} | space_id={m.space.id}')

print()
print('=== 审计知识库 document details ===')
sp = KnowledgeSpace.objects.get(name='审计知识库')
for d in Document.objects.filter(space=sp):
    print(f'  doc: {d.title} | id={d.id} | status={d.status}')
    chunks = DocumentChunk.objects.filter(document=d)
    print(f'    chunks: {chunks.count()}')
    for c in chunks[:3]:
        snippet = c.content[:120] if c.content else '(empty)'
        print(f'      chunk id={c.id} | content_len={len(c.content or "")} | snippet={snippet}')

print()
print('=== resolve_reference_space_ids for 测试自动编码工作区 ===')
from apps.knowledge.library_views import resolve_reference_space_ids
test_sp = KnowledgeSpace.objects.get(name='测试自动编码工作区')
ref_ids = resolve_reference_space_ids(test_sp)
print(f'  reference space ids: {ref_ids}')
