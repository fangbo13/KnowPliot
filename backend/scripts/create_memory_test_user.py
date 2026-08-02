"""Create the regular test user 徐明 (audit assistant) for the memory E2E test."""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from django.contrib.auth import get_user_model

from apps.spaces.models import KnowledgeSpace, SpaceMembership

User = get_user_model()

user = User.objects.filter(email="auditor.xu@test.ey.com").first()
if user is None:
    user = User.objects.create_user(
        username="auditor.xu",
        email="auditor.xu@test.ey.com",
        password="Auditor#2026",
        first_name="明",
        last_name="徐",
    )
    print("created user auditor.xu@test.ey.com")
else:
    user.set_password("Auditor#2026")
    user.is_active = True
    user.save(update_fields=["password", "is_active"])
    print("user exists — password reset")

for code in ("startech-audit-2026",):
    space = KnowledgeSpace.objects.get(code=code)
    membership, created = SpaceMembership.objects.get_or_create(
        space=space, user=user,
        defaults={"role": SpaceMembership.ROLE_MEMBER, "status": "active"},
    )
    if membership.status != "active":
        membership.status = "active"
        membership.save(update_fields=["status"])
    print(f"membership in {space.name}: {'created' if created else 'exists'} role={membership.role}")
print("DONE")
