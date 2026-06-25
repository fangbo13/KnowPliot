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
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    chunk_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_document"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"


class DocumentChunk(models.Model):
    """A chunk of a document with its embedding vector."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
