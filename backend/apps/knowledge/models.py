# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge models.

V3.7 P0.2: DocumentChunk.embedding now uses pgvector VectorField in production
(PostgreSQL) with HNSW index, and JSONField fallback in development (SQLite).
The retriever automatically selects the appropriate search method.
"""

import uuid

from django.db import models
from django.conf import settings


class DocumentCategory(models.Model):
    """Category for knowledge documents."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_documentcategory"
        verbose_name_plural = "Document categories"

    def __str__(self):
        return self.name


class Document(models.Model):
    """A knowledge base document."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("uploading", "Uploading"),
        ("processing", "Processing"),
        ("active", "Active"),
        ("expired", "Expired"),
        ("failed", "Failed"),
    ]

    FILE_TYPE_CHOICES = [
        ("pdf", "PDF"),
        ("docx", "Word Document"),
        ("html", "HTML"),
        ("txt", "Plain Text"),
        ("md", "Markdown"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # V6.0: space isolation — every document belongs to one knowledge space.
    # Nullable so the additive migration is safe; a data migration backfills
    # existing rows to the default space, and the API always sets it on upload.
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/%Y/%m/")
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    file_size = models.IntegerField(help_text="File size in bytes")
    category = models.ForeignKey(
        DocumentCategory, null=True, blank=True, on_delete=models.SET_NULL
    )
    tags = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    version = models.IntegerField(default=1)
    parent_document = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="versions"
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    processing_error = models.TextField(blank=True, default="")
    # V4.2 KB-V4.2-BATCH-010: Content hash for deduplication — SHA256 of file content
    # Prevents duplicate documents from being uploaded (manual + batch uploads)
    content_hash = models.CharField(
        max_length=64, blank=True, default="",
        help_text="SHA256 hash of file content for deduplication",
    )
    chunk_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_document"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_hash"]),  # V4.2: Fast duplicate lookup
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"


class DocumentChunk(models.Model):
    """A chunk of a document with its embedding vector."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # V6.0: denormalized space FK (mirrors document.space) so vector retrieval
    # can filter by space directly without an extra join.
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="document_chunks",
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    content = models.TextField()
    chunk_index = models.IntegerField()
    page_number = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    # V3.7 P0.2: In production (PostgreSQL + pgvector), uses VectorField for native
    # cosine similarity search with HNSW index (<50ms for 100k vectors).
    # In development (SQLite), falls back to JSONField + Python cosine_similarity.
    embedding = models.JSONField(null=True, blank=True)
    # Production-only: pgvector vector column (created by migration 0004)
    # This column is only populated when running on PostgreSQL.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "knowledge_documentchunk"
        indexes = [
            models.Index(fields=["document", "chunk_index"]),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document.title}"


class AnswerTemplate(models.Model):
    """Manual override/fallback answer for specific questions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question_pattern = models.CharField(max_length=500)
    answer = models.TextField()
    language = models.CharField(max_length=2, default="en")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_answertemplate"

    def __str__(self):
        return f"Template: {self.question_pattern[:50]}"


class BatchImportResultRecord(models.Model):
    """V4.2 KB-V4.2-BATCH-011: Persistent record of batch import results.

    Tracks how many files were successfully imported, skipped as duplicates,
    or failed — providing the user with a clear batch report.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    total_files = models.IntegerField(default=0, help_text="Total valid files in ZIP")
    success_count = models.IntegerField(default=0, help_text="Files successfully imported")
    duplicate_skipped_count = models.IntegerField(default=0, help_text="Files skipped as duplicates")
    failed_count = models.IntegerField(default=0, help_text="Files that failed to import")
    source_tag = models.CharField(max_length=50, default="EY_Batch", help_text="Source label for batch")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error_message = models.TextField(blank=True, default="", help_text="Error details if batch failed")
    result_details = models.JSONField(default=list, blank=True, help_text="Per-file import results")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_batchimportresultrecord"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Batch {self.id}: {self.success_count}/{self.total_files} imported"
