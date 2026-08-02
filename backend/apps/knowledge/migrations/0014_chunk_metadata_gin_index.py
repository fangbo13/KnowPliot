# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §4 L4: GIN index on DocumentChunk.metadata so
`metadata @> '{"terms": [...]}'` term filters stay fast at scale.

PostgreSQL only — SQLite (dev) stores metadata as TEXT and the retriever
falls back to Python-side filtering, so no index is needed there.
"""

from django.conf import settings
from django.db import connection, migrations


def create_gin_index(apps, schema_editor):
    is_postgres = "postgresql" in settings.DATABASES["default"]["ENGINE"]
    if not is_postgres:
        print("[Taxonomy L4] Skipping metadata GIN index — not running on PostgreSQL")
        return

    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS documentchunk_metadata_gin_idx
            ON knowledge_documentchunk
            USING gin ((metadata) jsonb_path_ops);
        """)
    print("[Taxonomy L4] Created GIN index on documentchunk.metadata")


def drop_gin_index(apps, schema_editor):
    is_postgres = "postgresql" in settings.DATABASES["default"]["ENGINE"]
    if not is_postgres:
        return
    with connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS documentchunk_metadata_gin_idx;")


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0013_document_last_reviewed_at_document_updated_by_and_more"),
    ]

    operations = [
        migrations.RunPython(create_gin_index, drop_gin_index),
    ]
