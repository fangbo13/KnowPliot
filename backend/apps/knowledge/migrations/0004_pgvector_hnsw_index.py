"""V3.7 P0.2: Add pgvector embedding_vector column + HNSW index.

In production (PostgreSQL), this migration:
1. Adds a new vector(1024) column for pgvector embedding storage
2. Migrates data from the old JSON embedding column to the new vector column
   (using a bulk SQL UPDATE for performance)
3. Creates an HNSW index for fast cosine similarity search (<50ms for 100k vectors)

In development (SQLite), the JSONField remains unchanged since pgvector
is not available — the retriever falls back to Python cosine_similarity.

NOTE: The old JSON embedding column is intentionally NOT dropped.
It continues to receive new writes from the Django ORM (since the model
still uses `embedding = JSONField`). A separate data-sync mechanism
should copy new embedding data to the vector column on insert/update.

This migration must be run AFTER PostgreSQL is configured as the default database.
"""

from django.db import migrations, connection
from django.conf import settings


def switch_to_pgvector(apps, schema_editor):
    """Migrate embedding data from JSON to pgvector VectorField + create HNSW index."""
    # Only run this migration on PostgreSQL
    is_postgres = "postgresql" in settings.DATABASES["default"]["ENGINE"]
    if not is_postgres:
        print("[V3.7 P0.2] Skipping pgvector migration — not running on PostgreSQL")
        return

    DocumentChunk = apps.get_model("knowledge", "DocumentChunk")

    # Step 1: Add the new vector column (if not already present)
    # pgvector extension should be enabled via a separate operation
    with connection.cursor() as cursor:
        # Ensure pgvector extension is installed
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # Add vector column if it doesn't exist
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'knowledge_documentchunk'
            AND column_name = 'embedding_vector';
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE knowledge_documentchunk
                ADD COLUMN embedding_vector vector(1024);
            """)
            print("[V3.7 P0.2] Added embedding_vector column (1024 dimensions)")

    # Step 2: Bulk migrate data from JSON to vector column using SQL
    # Much faster than row-by-row Python iteration for large datasets (10k+ chunks)
    with connection.cursor() as cursor:
        # Convert JSON array to pgvector format using PostgreSQL's jsonb functions
        # The embedding column stores a JSON array like [0.1, 0.2, ...]
        # We convert it to vector string format "[0.1,0.2,...]" then cast to vector type
        cursor.execute("""
            UPDATE knowledge_documentchunk
            SET embedding_vector = (
                REPLACE(
                    embedding::text,
                    ' ', ''
                )
            )::vector
            WHERE embedding IS NOT NULL
            AND embedding_vector IS NULL;
        """)
        migrated_count = cursor.rowcount

    print(f"[V3.7 P0.2] Migrated {migrated_count} chunk embeddings from JSON to vector")

    # Step 3: Create HNSW index for fast cosine similarity search
    # HNSW parameters:
    #   m = 16 (connections per layer — good balance of recall/speed)
    #   ef_construction = 64 (build-time search width — higher = better index quality)
    with connection.cursor() as cursor:
        # Check if index already exists
        cursor.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'knowledge_documentchunk'
            AND indexname = 'documentchunk_embedding_hnsw_idx';
        """)
        if not cursor.fetchone():
            cursor.execute("""
                CREATE INDEX documentchunk_embedding_hnsw_idx
                ON knowledge_documentchunk
                USING hnsw (embedding_vector vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """)
            print("[V3.7 P0.2] Created HNSW index on embedding_vector (m=16, ef_construction=64)")
        else:
            print("[V3.7 P0.2] HNSW index already exists — skipping creation")


def revert_to_json(apps, schema_editor):
    """Revert: drop vector column and HNSW index, keep JSON column."""
    is_postgres = "postgresql" in settings.DATABASES["default"]["ENGINE"]
    if not is_postgres:
        return

    with connection.cursor() as cursor:
        # Drop HNSW index
        cursor.execute("""
            DROP INDEX IF EXISTS documentchunk_embedding_hnsw_idx;
        """)
        # Drop vector column
        cursor.execute("""
            ALTER TABLE knowledge_documentchunk
            DROP COLUMN IF EXISTS embedding_vector;
        """)
    print("[V3.7 P0.2] Reverted pgvector migration — dropped vector column and HNSW index")


class Migration(migrations.Migration):

    dependencies = [
        ('knowledge', '0003_alter_documentchunk_embedding'),
    ]

    operations = [
        migrations.RunPython(switch_to_pgvector, revert_to_json),
    ]
