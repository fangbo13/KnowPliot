import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.knowledge.models import ReferenceLibrary, SpaceLibraryReference, Document
from apps.spaces.models import KnowledgeSpace
from django.contrib.auth import get_user_model
User = get_user_model()

print('=== Space Library References ===')
for ref in SpaceLibraryReference.objects.select_related('space', 'library').all():
    print(f'  space={ref.space.name} -> library={ref.library.name} | enabled={ref.enabled}')

print()
print('=== User fath@ey.com ===')
try:
    u = User.objects.get(email='fath@ey.com')
    is_pa = getattr(u, 'is_platform_admin', 'N/A')
    print(f'  id={u.id} email={u.email} is_platform_admin={is_pa} is_staff={u.is_staff} is_superuser={u.is_superuser}')
except User.DoesNotExist:
    print('  NOT FOUND')

print()
print('=== Documents in 审计知识库 space ===')
try:
    sp = KnowledgeSpace.objects.get(name='审计知识库')
    docs = Document.objects.filter(space=sp)
    print(f'  space_id={sp.id} doc_count={docs.count()}')
    for d in docs[:15]:
        print(f'    {d.title} | status={d.status}')
except Exception as e:
    print(f'  Error: {e}')

print()
print('=== All Spaces ===')
for sp in KnowledgeSpace.objects.all():
    print(f'  {sp.name} | code={sp.code} | vis={sp.visibility} | id={sp.id}')
