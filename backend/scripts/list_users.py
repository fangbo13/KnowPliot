import os, sys, django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.docker')
django.setup()
from django.contrib.auth import get_user_model
U = get_user_model()
for u in U.objects.all()[:15]:
    print(f"email={u.email} active={u.is_active} super={u.is_superuser} staff={u.is_staff}")
