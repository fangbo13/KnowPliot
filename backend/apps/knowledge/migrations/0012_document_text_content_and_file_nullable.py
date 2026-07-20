# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Part 1 (KB version化): Add Document.text_content, make file nullable,
add file_size default, add superseded status choice.

Migration dependency: after V3 migration sequence (0011).
All changes are additive — nullable fields, new choice value, default.
PostgreSQL verified (SPEC §13 additive + §1.11).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0011_workspace_retention_contract"),
    ]

    operations = [
        # §1.2: Add editable canonical text content (nullable for backward compat).
        migrations.AddField(
            model_name="document",
            name="text_content",
            field=models.TextField(blank=True, default=""),
        ),
        # §1.14: Make file nullable so inline text-created documents have no file.
        migrations.AlterField(
            model_name="document",
            name="file",
            field=models.FileField(
                blank=True, null=True, upload_to="documents/%Y/%m/"
            ),
        ),
        # §1.14: file_size default=0 for inline-created documents.
        migrations.AlterField(
            model_name="document",
            name="file_size",
            field=models.IntegerField(default=0, help_text="File size in bytes"),
        ),
        # §1.2: Add superseded status to choices (DB-level is varchar, no constraint change).
        migrations.AlterField(
            model_name="document",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("uploading", "Uploading"),
                    ("processing", "Processing"),
                    ("active", "Active"),
                    ("stale", "Stale"),
                    ("archived", "Archived"),
                    ("expired", "Expired"),
                    ("failed", "Failed"),
                    ("superseded", "Superseded"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
    ]
