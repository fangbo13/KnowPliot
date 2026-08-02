import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

u = User.objects.get(email='fath@ey.com')
u.set_password('admin123')
u.save()
print(f'Password reset for {u.email} -> admin123')
print(f'Verify: {u.check_password("admin123")}')
