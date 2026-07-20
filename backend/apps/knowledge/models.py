# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge models.

V3.7 P0.2: DocumentChunk.embedding now uses pgvector VectorField in production
(PostgreSQL) with HNSW index, and JSONField fallback in development (SQLite).
The retriever automatically selects the appropriate search method.
"""

import hashlib
import unicodedata
import uuid

from django.db import models
from django.conf import settings


def _locator_digest(value):
    canonical = unicodedata.normalize("NFC", value or "")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DocumentCategory(models.Model):
    """Category for knowledge documents."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="document_categories",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
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
        ("stale", "Stale"),
        ("archived", "Archived"),
        ("expired", "Expired"),
        ("failed", "Failed"),
        # Part 1 (KB version化): superseded — old version replaced by a newer one.
        # Retrieval excludes superseded documents so stale/contradictory content
        # never pollutes answers (SPEC §1.5 key invariant).
        ("superseded", "Superseded"),
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
    # Part 1 (§1.14): file is nullable so documents created via the inline
    # text editor (input box) have no binary source. file-based uploads still
    # populate this field and retain it as a downloadable source.
    file = models.FileField(upload_to="documents/%Y/%m/", null=True, blank=True)
    # Part 1 (§1.2): editable canonical markdown text. For file uploads this is
    # extracted from the file during ingestion; for inline creation it is the
    # user-entered content. chunk+embed operate on text_content, not the file.
    text_content = models.TextField(blank=True, default="")
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    # Part 1 (§1.14): file_size is 0 for inline-created documents (no binary).
    file_size = models.IntegerField(help_text="File size in bytes", default=0)
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
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="batch_import_results",
    )
    space_uuid = models.UUIDField(null=True, blank=True, editable=False)
    organization_uuid = models.UUIDField(null=True, blank=True, editable=False)
    locator_digest = models.CharField(
        max_length=64, blank=True, default="", editable=False
    )
    tombstone = models.ForeignKey(
        "spaces.WorkspaceTombstone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="batch_import_results",
    )
    legacy_scope_unknown = models.BooleanField(default=False)
    total_files = models.IntegerField(default=0, help_text="Total valid files in ZIP")
    success_count = models.IntegerField(default=0, help_text="Files successfully imported")
    duplicate_skipped_count = models.IntegerField(default=0, help_text="Files skipped as duplicates")
    failed_count = models.IntegerField(default=0, help_text="Files that failed to import")
    source_tag = models.CharField(max_length=50, default="EY_Batch", help_text="Source label for batch")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error_message = models.TextField(blank=True, default="", help_text="Error details if batch failed")
    result_details = models.JSONField(default=list, blank=True, help_text="Per-file import results")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    uploaded_by_uuid = models.UUIDField(null=True, blank=True, editable=False)
    sensitive_payload_scrubbed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_batchimportresultrecord"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        legacy_scope_unknown=True,
                        space__isnull=True,
                        space_uuid__isnull=True,
                    )
                    | models.Q(
                        legacy_scope_unknown=False,
                        space_uuid__isnull=False,
                    )
                ),
                name="knowledge_batch_scope_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="knowledge_batch_locator_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.space_id:
            if not self.space_uuid:
                self.space_uuid = self.space_id
            if not self.organization_uuid:
                self.organization_uuid = self.space.organization_id
            if not self.locator_digest:
                locator = getattr(self.space, "locator_reservation", None)
                if locator is not None:
                    self.locator_digest = _locator_digest(
                        locator.normalized_locator
                    )
            self.legacy_scope_unknown = False
        if self.uploaded_by_id and not self.uploaded_by_uuid:
            self.uploaded_by_uuid = self.uploaded_by_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Batch {self.id}: {self.success_count}/{self.total_files} imported"


class IngestionJob(models.Model):
    """Durable, space-scoped record of one document ingestion attempt."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("processing", "Processing"),
        ("retrying", "Retrying"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]
    TRIGGER_CHOICES = [
        ("upload", "Upload"),
        ("batch", "Batch Upload"),
        ("reindex", "Reindex"),
        ("admin_retry", "Admin Retry"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingestion_jobs",
    )
    document_uuid = models.UUIDField(null=True, blank=True, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingestion_jobs",
    )
    space_uuid = models.UUIDField(null=True, blank=True, editable=False)
    organization_uuid = models.UUIDField(null=True, blank=True, editable=False)
    locator_digest = models.CharField(
        max_length=64, blank=True, default="", editable=False
    )
    tombstone = models.ForeignKey(
        "spaces.WorkspaceTombstone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ingestion_jobs",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="requested_ingestion_jobs",
    )
    requested_by_uuid = models.UUIDField(null=True, blank=True, editable=False)
    trigger = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        default="upload",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="queued",
        db_index=True,
    )
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    attempt = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=4)
    last_error = models.CharField(max_length=1000, blank=True, default="")
    sensitive_payload_scrubbed_at = models.DateTimeField(null=True, blank=True)
    retry_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retries",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_ingestionjob"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["space", "status", "-created_at"],
                name="knowledge_i_space_i_658ba2_idx",
            ),
            models.Index(
                fields=["document", "status"],
                name="knowledge_i_documen_d529b8_idx",
            ),
            models.Index(
                fields=["status", "space", "created_at"],
                name="know_ing_st_sp_cr_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(space__isnull=False)
                    | models.Q(space_uuid__isnull=False)
                ),
                name="knowledge_ingestion_space_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="knowledge_ingestion_locator_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.document_id and not self.document_uuid:
            self.document_uuid = self.document_id
        if self.space_id:
            if not self.space_uuid:
                self.space_uuid = self.space_id
            if not self.organization_uuid:
                self.organization_uuid = self.space.organization_id
            if not self.locator_digest:
                locator = getattr(self.space, "locator_reservation", None)
                if locator is not None:
                    self.locator_digest = _locator_digest(
                        locator.normalized_locator
                    )
        if self.requested_by_id and not self.requested_by_uuid:
            self.requested_by_uuid = self.requested_by_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_id}: {self.status}"
