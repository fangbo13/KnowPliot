import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

u = User.objects.get(email='fath@ey.com')
print(f'user: {u.email}')
print(f'has_usable_password: {u.has_usable_password()}')
print(f'check admin123: {u.check_password("admin123")}')
print(f'check Test123!: {u.check_password("Test123!")}')
print(f'check test123: {u.check_password("test123")}')
print(f'check Admin123!: {u.check_password("Admin123!")}')
print(f'check password: {u.check_password("password")}')

# Also check the admin
a = User.objects.get(email='admin@test.ey.com')
print(f'\nadmin: {a.email}')
print(f'check admin123: {a.check_password("admin123")}')
