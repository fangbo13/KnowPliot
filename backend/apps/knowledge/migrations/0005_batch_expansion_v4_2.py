# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""V4.2 KB-V4.2-BATCH-010: Add content_hash to Document for deduplication.
V4.2 KB-V4.2-BATCH-011: Add BatchImportResultRecord model for batch tracking.
"""

from django.db import migrations, models
from django.conf import settings
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0004_pgvector_hnsw_index"),
    ]

    operations = [
        # BATCH-010: Add content_hash field to Document model
        migrations.AddField(
            model_name="document",
            name="content_hash",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SHA256 hash of file content for deduplication",
                max_length=64,
            ),
        ),
        # BATCH-010: Add index for fast duplicate lookup
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["content_hash"], name="knowledge_doc_content_hash_idx"),
        ),
        # BATCH-011: Add BatchImportResultRecord model
        migrations.CreateModel(
            name="BatchImportResultRecord",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "total_files",
                    models.IntegerField(
                        default=0,
                        help_text="Total valid files in ZIP",
                    ),
                ),
                (
                    "success_count",
                    models.IntegerField(
                        default=0,
                        help_text="Files successfully imported",
                    ),
                ),
                (
                    "duplicate_skipped_count",
                    models.IntegerField(
                        default=0,
                        help_text="Files skipped as duplicates",
                    ),
                ),
                (
                    "failed_count",
                    models.IntegerField(
                        default=0,
                        help_text="Files that failed to import",
                    ),
                ),
                (
                    "source_tag",
                    models.CharField(
                        default="EY_Batch",
                        help_text="Source label for batch",
                        max_length=50,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Error details if batch failed",
                    ),
                ),
                (
                    "result_details",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Per-file import results",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        on_delete=models.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "knowledge_batchimportresultrecord",
                "ordering": ["-created_at"],
            },
        ),
    ]
