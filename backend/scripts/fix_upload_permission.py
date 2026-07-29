"""Check and fix space membership for file upload testing."""
import os, sys, django

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
django.setup()

from django.contrib.auth import get_user_model
from apps.spaces.models import KnowledgeSpace, SpaceMembership

User = get_user_model()
SPACE_ID = "0cb246e8-c8a7-45eb-b70c-232e38e2bd04"

# 1) Show space info
try:
    space = KnowledgeSpace.objects.get(pk=SPACE_ID)
    print(f"Space: {space.name} (status={space.status}, owner_id={space.owner_id})")
    print(f"  Owner: {space.owner.email} (super={space.owner.is_superuser})")
except KnowledgeSpace.DoesNotExist:
    print(f"Space {SPACE_ID} not found!")
    sys.exit(1)

# 2) List all memberships
print("\n--- All memberships ---")
memberships = SpaceMembership.objects.filter(space=space).select_related("user")
for m in memberships:
    print(f"  user={m.user.email} role={m.role} status={m.status} expires={m.expires_at}")

# 3) Check auditor.xu
auditor = User.objects.filter(email="auditor.xu@test.ey.com").first()
if auditor:
    m = SpaceMembership.objects.filter(space=space, user=auditor).first()
    if m:
        print(f"\nAuditor current role: {m.role}")
        # Upgrade to knowledge_admin
        m.role = SpaceMembership.ROLE_KNOWLEDGE_ADMIN
        m.status = "active"
        m.expires_at = None
        m.save()
        print(f"Updated auditor.xu role to: {m.role}")
    else:
        # Create membership
        m = SpaceMembership.objects.create(
            space=space,
            user=auditor,
            role=SpaceMembership.ROLE_KNOWLEDGE_ADMIN,
            status="active",
            source_kind=SpaceMembership.SOURCE_MANUAL,
        )
        print(f"Created membership for auditor.xu as: {m.role}")
else:
    print("auditor.xu not found!")

# 4) Also check if any user is already owner/knowledge_admin
print("\n--- Users with upload permission ---")
admins = SpaceMembership.objects.filter(
    space=space,
    role__in=[SpaceMembership.ROLE_OWNER, SpaceMembership.ROLE_KNOWLEDGE_ADMIN],
    status="active",
).select_related("user")
for m in admins:
    print(f"  {m.user.email} — role={m.role}")

print("\nDone.")
