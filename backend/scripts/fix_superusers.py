"""Fix superuser count: ensure exactly ONE super admin exists.

- Remove is_superuser from all non-admin accounts.
- Keep admin@test.ey.com as the sole super admin.
- Set username to 'admin' and password to 'admin123'.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.users.models import User

KEEP_EMAIL = 'admin@test.ey.com'

# 1. Demote all other superusers
others = User.objects.filter(is_superuser=True).exclude(email=KEEP_EMAIL)
for u in others:
    print(f"Demoting: {u.email} (username={u.username})")
    # Use .update() to bypass the save() uniqueness check
    User.objects.filter(pk=u.pk).update(is_superuser=False)

# 2. Ensure the keeper exists and is the sole superuser
keeper = User.objects.filter(email=KEEP_EMAIL).first()
if not keeper:
    print(f"ERROR: {KEEP_EMAIL} not found!")
else:
    print(f"Keeping: {keeper.email} (username={keeper.username})")
    # Set username to 'admin'
    if keeper.username != 'admin':
        keeper.username = 'admin'
        keeper.save(update_fields=['username'])
    # Ensure is_superuser=True via .update() to bypass save() check
    User.objects.filter(pk=keeper.pk).update(is_superuser=True)
    # Set password
    keeper.set_password('admin123')
    keeper.save(update_fields=['password'])
    print(f"  -> username set to 'admin', password set to 'admin123'")

# 3. Verify final state
final = User.objects.filter(is_superuser=True)
print(f"\nFinal superusers: {list(final.values_list('email', flat=True))}")
print(f"Final count: {final.count()}")
