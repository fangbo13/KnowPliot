"""Check current taxonomy data and user profiles."""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from django.contrib.auth import get_user_model
from apps.spaces.models import (
    BusinessLine, OfficeLocation, WorkGroup,
    WorkspaceCreationPolicy, Organization,
)

User = get_user_model()

print("=== Users ===")
for u in User.objects.all():
    sl = getattr(u, "service_line", None)
    ol = getattr(u, "office_location", None)
    print(f"  email={u.email} service_line={sl} office_location={ol} "
          f"is_superuser={u.is_superuser} is_staff={u.is_staff}")

print("\n=== Organizations ===")
for org in Organization.objects.all():
    print(f"  id={org.id} name={org.name} slug={org.slug} status={org.status}")

print("\n=== BusinessLines ===")
for bl in BusinessLine.objects.all():
    print(f"  id={bl.id} org_id={bl.organization_id} name={bl.name} "
          f"code={bl.code} status={bl.status}")

print("\n=== OfficeLocations ===")
for ol in OfficeLocation.objects.all():
    print(f"  id={ol.id} org_id={ol.organization_id} code={ol.normalized_code} "
          f"name={ol.display_name} active={ol.active}")

print("\n=== WorkGroups ===")
for wg in WorkGroup.objects.all():
    print(f"  id={wg.id} bl_id={wg.business_line_id} code={wg.normalized_code} "
          f"name={wg.display_name} active={wg.active}")

print("\n=== WorkspaceCreationPolicies ===")
for p in WorkspaceCreationPolicy.objects.all():
    print(f"  id={p.id} bl_id={p.business_line_id} revision={p.revision} "
          f"status={p.status} audience={p.audience} route={p.review_route}")
