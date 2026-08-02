"""One-off: drop a leftover Django test database (terminates its sessions)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
import psycopg  # noqa: E402

db = settings.DATABASES["default"]
conn = psycopg.connect(
    host=db["HOST"], port=db["PORT"], user=db["USER"],
    password=db["PASSWORD"], dbname=db["NAME"], autocommit=True,
)
with conn.cursor() as cur:
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = 'test_knowpilot' AND pid <> pg_backend_pid();"
    )
    cur.execute("DROP DATABASE IF EXISTS test_knowpilot;")
print("test database dropped")
