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
        # Knowledge iteration spec §3.2: review gate states. Documents in
        # pending_review / rejected NEVER have retrievable chunks — approval
        # is the only transition that triggers chunk+embed indexing.
        ("pending_review", "Pending Review"),
        ("rejected", "Rejected"),
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
    # RAG optimization spec Phase 7: aggregated user-feedback signal in
    # [-1, 1], recomputed daily from Feedback→Message→Citation links.
    # Applied as an ordering-only boost in retrieval (never rerank_score).
    feedback_score = models.FloatField(default=0.0)
    parent_document = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="versions"
    )
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    # Knowledge iteration spec §3.5: watermark — the author of THIS version row.
    # uploaded_by keeps its historical semantics (uploader of this version);
    # updated_by is set on every version creation for contributor tracing.
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_documents",
    )
    # Knowledge iteration spec §4 L3: owner "confirm still fresh" resets this
    # timestamp; the stale sweep uses max(updated_at, last_reviewed_at).
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True, default="")
    # V4.2 KB-V4.2-BATCH-010: Content hash for deduplication — SHA256 of file content
    # Prevents duplicate documents from being uploaded (manual + batch uploads)
    content_hash = models.CharField(
        max_length=64, blank=True, default="",
        help_text="SHA256 hash of file content for deduplication",
    )
    chunk_count = models.IntegerField(default=0)
    # KB/RAG audit spec P1 §B2: mean of the document's chunk embeddings,
    # refreshed on ingest. Powers precomputed graph similarity edges.
    pooled_embedding = models.JSONField(null=True, blank=True)
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
    # KB/RAG audit spec P1 §A6: CJK-bigram token text (title + content) so
    # PostgreSQL FTS with the simple config can match unspaced Chinese.
    content_tokens = models.TextField(blank=True, default="")
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


# ---------------------------------------------------------------------------
# Knowledge iteration spec §2 — controlled metadata taxonomy (tag dimensions,
# not a folder tree: one document can be FY26 + accounts_receivable + scot).
# ---------------------------------------------------------------------------


class TaxonomyDimension(models.Model):
    """A controlled metadata dimension (account / fiscal_year / audit_phase / scot)."""

    STATUS_CHOICES = [("active", "Active"), ("archived", "Archived")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "spaces.Organization",
        on_delete=models.CASCADE,
        related_name="taxonomy_dimensions",
    )
    # Null business_line = organization-wide dimension (e.g. fiscal_year).
    business_line = models.ForeignKey(
        "spaces.BusinessLine",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="taxonomy_dimensions",
    )
    # KB optimization spec §2.1: space-private dimensions. When set, the
    # dimension belongs to exactly one space (self-managed by that space's
    # owner/knowledge_admin). When null, the dimension is a shared
    # organization/business-line dimension (platform-managed, legacy behavior).
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="taxonomy_dimensions",
    )
    code = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    is_hierarchical = models.BooleanField(default=False)
    required = models.BooleanField(
        default=False, help_text="If true, uploads must carry at least one term."
    )
    sort_order = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_taxonomydimension"
        ordering = ["sort_order", "code"]
        constraints = [
            # Shared dimensions (space IS NULL) stay unique per organization.
            models.UniqueConstraint(
                fields=["organization", "code"],
                condition=models.Q(space__isnull=True),
                name="knowledge_taxdim_org_code_uniq",
            ),
            # Space-private dimensions are unique per space.
            models.UniqueConstraint(
                fields=["space", "code"],
                condition=models.Q(space__isnull=False),
                name="knowledge_taxdim_space_code_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.code} ({self.name})"


class TaxonomyTerm(models.Model):
    """A controlled vocabulary term within a dimension (e.g. fy26, accounts_receivable)."""

    STATUS_CHOICES = [("active", "Active"), ("archived", "Archived")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dimension = models.ForeignKey(
        TaxonomyDimension, on_delete=models.CASCADE, related_name="terms"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    code = models.SlugField(max_length=80)
    label = models.CharField(max_length=200)
    # KB/RAG audit spec P2 §A4: controlled synonym list — query understanding
    # matches these and expands the lexical query (e.g. 坏账准备 ↔ 信用减值损失).
    synonyms = models.JSONField(default=list, blank=True)
    sort_order = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_taxonomyterm"
        ordering = ["sort_order", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["dimension", "code"],
                name="knowledge_taxterm_dim_code_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.dimension.code}:{self.code}"


class DocumentTag(models.Model):
    """Document ↔ TaxonomyTerm many-to-many with attribution."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="taxonomy_tags"
    )
    term = models.ForeignKey(
        TaxonomyTerm, on_delete=models.CASCADE, related_name="document_tags"
    )
    tagged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tagged_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "knowledge_documenttag"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "term"],
                name="knowledge_doctag_doc_term_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.document_id} → {self.term_id}"


class TermOwnership(models.Model):
    """Account/term owner within a space — receives stale/review notifications."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="term_ownerships",
    )
    term = models.ForeignKey(
        TaxonomyTerm, on_delete=models.CASCADE, related_name="ownerships"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_terms",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "knowledge_termownership"
        constraints = [
            models.UniqueConstraint(
                fields=["space", "term", "owner"],
                name="knowledge_termown_space_term_owner_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.term_id} → {self.owner_id} @ {self.space_id}"


# ---------------------------------------------------------------------------
# Knowledge iteration spec §3.3 — review gate.
# ---------------------------------------------------------------------------


class ReviewRequest(models.Model):
    """One review request for a pending document version.

    Approval is the only transition that indexes the version (chunk+embed)
    and supersedes the previous active version.
    """

    DECISION_PENDING = "pending"
    DECISION_APPROVED = "approved"
    DECISION_REJECTED = "rejected"
    DECISION_CHOICES = [
        (DECISION_PENDING, "Pending"),
        (DECISION_APPROVED, "Approved"),
        (DECISION_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Denormalized space FK so the review queue filters per-space cheaply.
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="review_requests",
    )
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="review_requests"
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_reviews",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_reviews",
    )
    # Line-level diff snapshot captured at submit time (reuses preview-diff).
    diff_summary = models.JSONField(default=dict, blank=True)
    # L1 conflict detection output: [{document_id, title, score, chunk_index}].
    conflict_hints = models.JSONField(default=list, blank=True)
    decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES, default=DECISION_PENDING
    )
    comment = models.TextField(blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_reviewrequest"
        ordering = ["-created_at"]
        constraints = [
            # Separation of duties: submitter can never approve their own work.
            models.CheckConstraint(
                check=~models.Q(reviewer=models.F("submitted_by")),
                name="knowledge_review_reviewer_ne_submitter",
            ),
            # At most one pending request per document version.
            models.UniqueConstraint(
                fields=["document"],
                condition=models.Q(decision="pending"),
                name="knowledge_review_one_pending_per_doc",
            ),
        ]

    def __str__(self):
        return f"Review {self.document_id}: {self.decision}"


# ---------------------------------------------------------------------------
# Knowledge iteration spec §5.1 — explicit markdown links between documents
# (parsed at ingest; feeds the Local Graph "link" edges).
# ---------------------------------------------------------------------------


class DocumentLink(models.Model):
    """Explicit link from one document's markdown to another ([[wiki]] or md link).

    KB/RAG audit spec P3 §B1: a row with ``target=None`` records an
    *unresolved* wikilink (Obsidian semantics — the linked note does not
    exist yet). ``unresolved_title`` keeps the raw title so the link resolves
    automatically once a matching document appears.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="document_links",
    )
    source = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="outgoing_links"
    )
    target = models.ForeignKey(
        Document,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="incoming_links",
    )
    unresolved_title = models.CharField(max_length=255, blank=True, default="")
    anchor_text = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "knowledge_documentlink"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target"],
                name="knowledge_doclink_src_tgt_uniq",
            ),
            models.UniqueConstraint(
                fields=["source", "unresolved_title"],
                condition=models.Q(target__isnull=True),
                name="knowledge_doclink_src_unres_uniq",
            ),
        ]

    def __str__(self):
        if self.target_id is None:
            return f"{self.source_id} → [[{self.unresolved_title}]] (unresolved)"
        return f"{self.source_id} → {self.target_id}"


class DocumentSimilarity(models.Model):
    """Precomputed embedding-similarity edge between two documents.

    KB/RAG audit spec P1 §B2: the knowledge graph previously computed
    O(n²) cosine similarity per request. Edges are now refreshed at ingest
    time from pooled document embeddings; the graph endpoint only reads.
    ``source``/``target`` are ordered by id string so each pair is stored once.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="document_similarities",
    )
    source = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="similarity_edges_out"
    )
    target = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="similarity_edges_in"
    )
    score = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_documentsimilarity"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target"],
                name="knowledge_docsim_src_tgt_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["space", "-score"]),
        ]

    def __str__(self):
        return f"{self.source_id} ~ {self.target_id} ({self.score})"


# ---------------------------------------------------------------------------
# KB optimization spec §2.2 — platform-official reference libraries. A space
# can be certified as a shared reference library (IFRS / CAS / IPO cases);
# other spaces reference it so RAG retrieval reads across the isolation
# boundary for that library only (read-only, retrieval path only).
# ---------------------------------------------------------------------------


class ReferenceLibrary(models.Model):
    """A KnowledgeSpace certified by a platform admin as a shared reference library."""

    CATEGORY_CHOICES = [
        ("ifrs", "IFRS"),
        ("cas", "China Accounting Standards"),
        ("ipo_cases", "IPO Cases"),
        ("policy", "Company Policy"),
        ("other", "Other"),
    ]
    STATUS_PUBLISHED = "published"
    STATUS_UNPUBLISHED = "unpublished"
    STATUS_CHOICES = [
        (STATUS_PUBLISHED, "Published"),
        (STATUS_UNPUBLISHED, "Unpublished"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.OneToOneField(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="reference_library",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="other"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_UNPUBLISHED
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="published_reference_libraries",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_referencelibrary"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status", "category"], name="knowledge_reflib_status_cat"),
        ]

    def __str__(self):
        return f"{self.name} [{self.category}/{self.status}]"


class SpaceLibraryReference(models.Model):
    """A space's opt-in reference to a published :class:`ReferenceLibrary`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="library_references",
    )
    library = models.ForeignKey(
        ReferenceLibrary,
        on_delete=models.CASCADE,
        related_name="space_references",
    )
    enabled = models.BooleanField(default=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="added_library_references",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_spacelibraryreference"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["space", "library"],
                name="knowledge_spacelibref_space_lib_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.space_id} → {self.library_id}"
