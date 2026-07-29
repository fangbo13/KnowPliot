import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from django.contrib.auth import get_user_model

from apps.spaces.models import KnowledgeSpace, SpaceMembership

User = get_user_model()

user = User.objects.filter(email="auditor.li@test.ey.com").first()
if user is None:
    user = User.objects.create_user(
        username="auditor.li", email="auditor.li@test.ey.com",
        password="Auditor#2026", first_name="莉", last_name="李",
    )
    print("created auditor.li@test.ey.com")
else:
    user.set_password("Auditor#2026")
    user.is_active = True
    user.save(update_fields=["password", "is_active"])
    print("reset auditor.li password")

space = KnowledgeSpace.objects.get(code="innomed-ipo-2026")
SpaceMembership.objects.get_or_create(
    space=space, user=user,
    defaults={"role": SpaceMembership.ROLE_MEMBER, "status": "active"},
)
print(f"member of {space.name} id={space.id}")
print("DONE")
