# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat models."""

import uuid
import hashlib
import re

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class ChatSession(models.Model):
    """A chat session between a user and the AI assistant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # V6.0: space isolation — a session belongs to one knowledge space.
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_chatsession"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Session {self.id} - {self.user.email}"


class Message(models.Model):
    """A single message in a chat session."""

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]
    CONFIDENCE_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
        ("insufficient", "Insufficient"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # V6.0: denormalized space FK (mirrors session.space) for direct scoping.
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    token_count = models.IntegerField(null=True, blank=True)
    model_used = models.CharField(max_length=100, null=True, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    retrieval_count = models.IntegerField(null=True, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    confidence_label = models.CharField(
        max_length=20,
        choices=CONFIDENCE_CHOICES,
        blank=True,
        default="",
    )
    needs_human_review = models.BooleanField(default=False)
    retrieval_mode = models.CharField(max_length=20, blank=True, default="")
    retrieval_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_message"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class Citation(models.Model):
    """Source citation for an AI-generated answer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # V6.0: denormalized space FK — a citation always belongs to the same space
    # as its message; isolation guarantees citations never cross spaces.
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="citations",
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="citations",
    )
    document = models.ForeignKey(
        "knowledge.Document",
        on_delete=models.PROTECT,
    )
    chunk = models.ForeignKey(
        "knowledge.DocumentChunk",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    relevance_score = models.FloatField()
    page_number = models.IntegerField(null=True, blank=True)
    quoted_text = models.TextField(blank=True, default="")

    class Meta:
        db_table = "chat_citation"

    def __str__(self):
        return f"Citation: {self.document.title} (p.{self.page_number})"


class Feedback(models.Model):
    """User feedback on an AI response."""

    FEEDBACK_TYPE_HELPFUL = "helpful"
    FEEDBACK_TYPE_UNHELPFUL = "unhelpful"
    FEEDBACK_TYPE_INCORRECT = "incorrect"
    FEEDBACK_TYPE_OUTDATED = "outdated"
    FEEDBACK_TYPE_MISSING_SOURCE = "missing_source"
    FEEDBACK_TYPE_CHOICES = [
        (FEEDBACK_TYPE_HELPFUL, "Helpful"),
        (FEEDBACK_TYPE_UNHELPFUL, "Unhelpful"),
        (FEEDBACK_TYPE_INCORRECT, "Incorrect"),
        (FEEDBACK_TYPE_OUTDATED, "Outdated"),
        (FEEDBACK_TYPE_MISSING_SOURCE, "Missing Source"),
    ]

    STATUS_SUBMITTED = "submitted"
    STATUS_PENDING_REVIEW = "pending_review"
    STATUS_IN_REVIEW = "in_review"
    STATUS_RESOLVED = "resolved"
    STATUS_DISMISSED = "dismissed"
    STATUS_WITHDRAWN = "withdrawn"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_PENDING_REVIEW, "Pending Review"),
        (STATUS_IN_REVIEW, "In Review"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_DISMISSED, "Dismissed"),
        (STATUS_WITHDRAWN, "Withdrawn"),
    ]

    RATING_CHOICES = [
        (1, "Thumbs Down"),
        (2, "Thumbs Up"),
    ]

    REASON_CHOICES = [
        ("inaccurate", "Inaccurate"),
        ("irrelevant", "Irrelevant"),
        ("incomplete", "Incomplete"),
        ("outdated", "Outdated"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # V6.0: denormalized space FK (mirrors message.space).
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="feedbacks",
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="feedbacks",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_feedbacks",
    )
    feedback_type = models.CharField(
        max_length=30,
        choices=FEEDBACK_TYPE_CHOICES,
        default=FEEDBACK_TYPE_HELPFUL,
    )
    rating = models.IntegerField(choices=RATING_CHOICES, null=True, blank=True)
    reason = models.CharField(
        max_length=20, choices=REASON_CHOICES, null=True, blank=True
    )
    comment = models.TextField(blank=True, default="")
    suggested_source = models.TextField(blank=True, default="")
    flag_for_review = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SUBMITTED,
        db_index=True,
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_feedbacks",
    )
    resolution_code = models.CharField(max_length=50, blank=True, default="")
    resolution_notes = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    review_context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_feedback"
        unique_together = ["user", "message"]
        indexes = [
            models.Index(
                fields=["space", "status", "created_at"],
                name="chat_fb_sp_st_cr_idx",
            ),
        ]

    def __str__(self):
        return f"Feedback {self.rating} for message {self.message.id}"


class ModelInvocation(models.Model):
    """Operational telemetry for one model-backed answer attempt.

    Only safe aggregate metadata is stored; prompts, answers, raw exceptions,
    and credentials are deliberately excluded.
    """

    STATUS_CHOICES = [
        ("success", "Success"),
        ("failure", "Failure"),
        ("timeout", "Timeout"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="model_invocations",
    )
    session = models.ForeignKey(
        ChatSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_invocations",
    )
    message = models.OneToOneField(
        Message,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_invocation",
    )
    question_message = models.ForeignKey(
        Message,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_invocations_as_question",
    )
    model = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, db_index=True)
    token_count = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_modelinvocation"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["space", "status", "-created_at"],
                name="chat_modeli_space_i_cf0e07_idx",
            ),
            models.Index(
                fields=["model", "-created_at"],
                name="chat_modeli_model_d5d3d4_idx",
            ),
        ]

    def __str__(self):
        return f"{self.model or 'unknown'}: {self.status}"


class FeedbackReviewEvent(models.Model):
    """Immutable event history for feedback review workflow."""

    EVENT_ASSIGN = "assign"
    EVENT_CLAIM = "claim"
    EVENT_RESOLVE = "resolve"
    EVENT_DISMISS = "dismiss"
    EVENT_REOPEN = "reopen"
    EVENT_CHOICES = [
        (EVENT_ASSIGN, "Assign"),
        (EVENT_CLAIM, "Claim"),
        (EVENT_RESOLVE, "Resolve"),
        (EVENT_DISMISS, "Dismiss"),
        (EVENT_REOPEN, "Reopen"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feedback = models.ForeignKey(
        Feedback,
        on_delete=models.CASCADE,
        related_name="review_events",
    )
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="feedback_review_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_review_events",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_feedback_review_events",
    )
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_feedbackreviewevent"
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if self.pk and FeedbackReviewEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError("Feedback review events are immutable.")
        super().save(*args, **kwargs)


class KnowledgeGapTicket(models.Model):
    """Knowledge improvement ticket created from reviewed feedback."""

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_WONT_FIX = "wont_fix"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_WONT_FIX, "Won't Fix"),
    ]
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="knowledge_gap_tickets",
    )
    feedback = models.ForeignKey(
        Feedback,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_gap_tickets",
    )
    question_snapshot = models.TextField()
    normalized_question_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_gap_tickets",
    )
    suggested_source = models.TextField(blank=True, default="")
    resolution_notes = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_knowledgegapticket"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["space", "status", "priority"],
                name="chat_gap_space_status_idx",
            ),
            models.Index(
                fields=["space", "status", "created_at"],
                name="chat_gap_sp_st_cr_idx",
            ),
        ]

    @staticmethod
    def normalize_question(question: str) -> str:
        return re.sub(r"\s+", " ", (question or "").strip().lower())

    @classmethod
    def hash_question(cls, question: str) -> str:
        return hashlib.sha256(cls.normalize_question(question).encode("utf-8")).hexdigest()

    @property
    def is_open_lifecycle(self):
        return self.status in {self.STATUS_OPEN, self.STATUS_IN_PROGRESS}

    def mark_resolved(self, notes="", wont_fix=False):
        self.status = self.STATUS_WONT_FIX if wont_fix else self.STATUS_RESOLVED
        self.resolution_notes = notes
        self.resolved_at = timezone.now()


class ComplianceExportJob(models.Model):
    """Asynchronous compliance export job with scoped, audited downloads."""

    DATASET_FEEDBACK = "feedback"
    DATASET_REVIEWS = "reviews"
    DATASET_GAPS = "gaps"
    DATASET_UNANSWERED = "unanswered"
    DATASET_DOCUMENTS = "documents"
    DATASET_CHOICES = [
        (DATASET_FEEDBACK, "Feedback"),
        (DATASET_REVIEWS, "Reviews"),
        (DATASET_GAPS, "Knowledge Gaps"),
        (DATASET_UNANSWERED, "Unanswered Questions"),
        (DATASET_DOCUMENTS, "Documents"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_EXPIRED, "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="compliance_export_jobs",
    )
    retry_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retries",
    )
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="compliance_export_jobs",
    )
    dataset = models.CharField(max_length=20, choices=DATASET_CHOICES, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
    )
    date_from = models.DateTimeField(null=True, blank=True)
    date_to = models.DateTimeField(null=True, blank=True)
    result_file = models.CharField(max_length=500, blank=True, default="")
    row_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True, default="")
    safe_error_summary = models.CharField(max_length=500, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_complianceexportjob"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["requested_by", "status", "-created_at"],
                name="chat_export_request_status_idx",
            ),
            models.Index(
                fields=["space", "dataset", "-created_at"],
                name="chat_export_space_dataset_idx",
            ),
            models.Index(
                fields=["status", "requested_by", "created_at"],
                name="chat_exp_st_user_cr_idx",
            ),
        ]

    def __str__(self):
        return f"{self.dataset} export {self.id} ({self.status})"


class RAGEvaluationRun(models.Model):
    """Immutable summary of one versioned RAG quality evaluation."""

    STATUS_CHOICES = [
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rag_evaluation_runs",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="running")
    dataset_version = models.CharField(max_length=80)
    config_fingerprint = models.CharField(max_length=64, blank=True, default="")
    metrics = models.JSONField(default=dict)
    report = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_ragevaluationrun"
        ordering = ["-created_at"]
