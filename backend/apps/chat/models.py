# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat models."""

import hashlib
import re
import unicodedata
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def _capture_space_retention_evidence(instance):
    """Populate immutable, content-free workspace evidence for retained rows."""

    if not instance.space_id:
        return
    if not instance.space_uuid:
        instance.space_uuid = instance.space_id
    if not instance.organization_uuid:
        instance.organization_uuid = instance.space.organization_id
    if not instance.locator_digest:
        locator = getattr(instance.space, "locator_reservation", None)
        if locator is not None:
            canonical = unicodedata.normalize("NFC", locator.normalized_locator)
            instance.locator_digest = hashlib.sha256(
                canonical.encode("utf-8")
            ).hexdigest()


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
    is_pinned = models.BooleanField(default=False, db_index=True)
    # Session-level reference-library selection: null=never chosen (fall back to
    # keyword auto-routing), []=explicitly none (space-only), [uuid,...]=chosen.
    reference_library_ids = models.JSONField(null=True, blank=True, default=None)
    branch_request_id = models.UUIDField(null=True, blank=True)
    branched_from_message = models.ForeignKey(
        "chat.Message",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="branched_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_chatsession"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "branch_request_id"],
                condition=models.Q(branch_request_id__isnull=False),
                name="chat_session_user_branch_request_uniq",
            ),
        ]

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
    model_used = models.CharField(max_length=160, null=True, blank=True)
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
    version_group_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    version_number = models.PositiveIntegerField(default=1)
    is_current_version = models.BooleanField(default=True, db_index=True)
    supersedes_message = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="newer_versions",
    )
    retrieval_mode = models.CharField(max_length=20, blank=True, default="")
    retrieval_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_message"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["version_group_id", "version_number"],
                name="chat_message_version_number_uniq",
            ),
            models.UniqueConstraint(
                fields=["version_group_id"],
                condition=models.Q(is_current_version=True),
                name="chat_message_one_current_version_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class SessionMemory(models.Model):
    """Rolling long-term memory for one chat session.

    Messages evicted from the verbatim short-term window are condensed into
    ``summary`` + ``key_facts`` asynchronously (Celery), so the assistant
    still remembers early-session agreements after many rounds.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="memory",
    )
    # Mirrors session.space for direct scoping (same convention as Message).
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="session_memories",
    )
    summary = models.TextField(blank=True, default="")
    key_facts = models.JSONField(default=list, blank=True)
    # Watermark: created_at of the last message already folded into summary.
    summarized_until = models.DateTimeField(null=True, blank=True)
    summary_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_sessionmemory"

    def __str__(self):
        return f"Memory v{self.summary_version} for session {self.session_id}"


class ChatTurn(models.Model):
    """Durable identity and lifecycle for one user question/assistant answer."""

    STATUS_ACCEPTED = "accepted"
    STATUS_RETRIEVING = "retrieving"
    STATUS_REASONING = "reasoning"
    STATUS_ANSWERING = "answering"
    STATUS_SAVING = "saving"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_RETRIEVING, "Retrieving"),
        (STATUS_REASONING, "Reasoning"),
        (STATUS_ANSWERING, "Answering"),
        (STATUS_SAVING, "Saving"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    ANSWER_MODE_FAST = "fast"
    ANSWER_MODE_DEEP = "deep"
    ANSWER_MODE_CHOICES = [
        (ANSWER_MODE_FAST, "Fast"),
        (ANSWER_MODE_DEEP, "Deep"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_request_id = models.UUIDField()
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        on_delete=models.CASCADE,
        related_name="chat_turns",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_turns",
    )
    question_message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="question_turns",
    )
    assistant_message = models.OneToOneField(
        Message,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assistant_turn",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACCEPTED,
        db_index=True,
    )
    answer_mode = models.CharField(
        max_length=10,
        choices=ANSWER_MODE_CHOICES,
        default=ANSWER_MODE_FAST,
    )
    requested_answer_mode = models.CharField(
        max_length=10,
        choices=ANSWER_MODE_CHOICES,
        default=ANSWER_MODE_FAST,
    )
    requested_thinking_enabled = models.BooleanField(default=False)
    thinking_enabled = models.BooleanField(default=False)
    thinking_snapshot_known = models.BooleanField(default=True)
    thinking_budget = models.PositiveIntegerField(null=True, blank=True)
    # Reference libraries actually used for this turn (already capped by mode).
    reference_library_ids = models.JSONField(default=list, blank=True)
    policy_fallback_code = models.CharField(max_length=64, blank=True, default="")
    model_id = models.CharField(max_length=160, blank=True, default="")
    metrics = models.JSONField(default=dict)
    attempt_count = models.PositiveIntegerField(default=1)
    last_event_seq = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")
    protocol_version = models.PositiveSmallIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_chatturn"
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "client_request_id"],
                name="chat_turn_user_request_uniq",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(
                        thinking_snapshot_known=False,
                        requested_thinking_enabled=False,
                        thinking_enabled=False,
                        thinking_budget__isnull=True,
                        policy_fallback_code="legacy_thinking_unknown",
                    )
                    | models.Q(
                        thinking_snapshot_known=True,
                        thinking_enabled=False,
                        thinking_budget__isnull=True,
                    )
                    | models.Q(
                        thinking_snapshot_known=True,
                        thinking_enabled=True,
                        thinking_budget__gte=1,
                        thinking_budget__lte=32768,
                    )
                ),
                name="chat_turn_thinking_snapshot_ck",
            ),
            models.CheckConstraint(
                check=models.Q(protocol_version__in=(1, 2, 3)),
                name="chat_turn_protocol_version_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["session", "status"],
                name="chat_turn_session_status_idx",
            ),
            models.Index(
                fields=["user", "-started_at"],
                name="chat_turn_user_started_idx",
            ),
        ]

    def __str__(self):
        return f"Turn {self.id} ({self.status})"


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


def default_share_expiry():
    return timezone.now() + timedelta(days=7)


class ConversationShare(models.Model):
    """Revocable, tenant-scoped, read-only share of one conversation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client_request_id = models.UUIDField(null=True, blank=True)
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="shares",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_shares",
    )
    organization = models.ForeignKey(
        "spaces.Organization",
        on_delete=models.CASCADE,
        related_name="conversation_shares",
    )
    expires_at = models.DateTimeField(default=default_share_expiry, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chat_conversationshare"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "client_request_id"],
                condition=models.Q(client_request_id__isnull=False),
                name="chat_share_owner_request_uniq",
            ),
        ]

    @property
    def is_available(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


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
        on_delete=models.SET_NULL,
        related_name="feedbacks",
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
        related_name="feedbacks",
    )
    message = models.ForeignKey(
        Message,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedbacks",
    )
    message_uuid = models.UUIDField(null=True, blank=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="message_feedbacks",
    )
    user_uuid = models.UUIDField(null=True, blank=True, editable=False)
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
    reviewer_uuid = models.UUIDField(null=True, blank=True, editable=False)
    resolution_code = models.CharField(max_length=50, blank=True, default="")
    resolution_notes = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    review_context = models.JSONField(default=dict, blank=True)
    sensitive_payload_scrubbed_at = models.DateTimeField(null=True, blank=True)
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
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(space__isnull=False)
                    | models.Q(space_uuid__isnull=False)
                ),
                name="chat_feedback_space_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(message__isnull=False)
                    | models.Q(message_uuid__isnull=False)
                ),
                name="chat_feedback_message_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(user__isnull=False)
                    | models.Q(user_uuid__isnull=False)
                ),
                name="chat_feedback_user_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="chat_feedback_locator_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        _capture_space_retention_evidence(self)
        if self.message_id and not self.message_uuid:
            self.message_uuid = self.message_id
        if self.user_id and not self.user_uuid:
            self.user_uuid = self.user_id
        if self.reviewer_id and not self.reviewer_uuid:
            self.reviewer_uuid = self.reviewer_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Feedback {self.rating} for message {self.message_id or self.message_uuid}"


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
        on_delete=models.SET_NULL,
        related_name="model_invocations",
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
        related_name="model_invocations",
    )
    session = models.ForeignKey(
        ChatSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_invocations",
    )
    session_uuid = models.UUIDField(null=True, blank=True, editable=False)
    message = models.OneToOneField(
        Message,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_invocation",
    )
    message_uuid = models.UUIDField(null=True, blank=True, editable=False)
    question_message = models.ForeignKey(
        Message,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="model_invocations_as_question",
    )
    question_message_uuid = models.UUIDField(null=True, blank=True, editable=False)
    model = models.CharField(max_length=160, blank=True, default="")
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
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="chat_invocation_locator_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        _capture_space_retention_evidence(self)
        if self.session_id and not self.session_uuid:
            self.session_uuid = self.session_id
        if self.message_id and not self.message_uuid:
            self.message_uuid = self.message_id
        if self.question_message_id and not self.question_message_uuid:
            self.question_message_uuid = self.question_message_id
        super().save(*args, **kwargs)

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
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_events",
    )
    feedback_uuid = models.UUIDField(null=True, blank=True, editable=False)
    space = models.ForeignKey(
        "spaces.KnowledgeSpace",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_review_events",
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
        related_name="feedback_review_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_review_events",
    )
    actor_uuid = models.UUIDField(null=True, blank=True, editable=False)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_feedback_review_events",
    )
    reviewer_uuid = models.UUIDField(null=True, blank=True, editable=False)
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    sensitive_payload_scrubbed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_feedbackreviewevent"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(space__isnull=False)
                    | models.Q(space_uuid__isnull=False)
                ),
                name="chat_review_space_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(feedback__isnull=False)
                    | models.Q(feedback_uuid__isnull=False)
                ),
                name="chat_review_feedback_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="chat_review_locator_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and FeedbackReviewEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError("Feedback review events are immutable.")
        _capture_space_retention_evidence(self)
        if self.feedback_id and not self.feedback_uuid:
            self.feedback_uuid = self.feedback_id
        if self.actor_id and not self.actor_uuid:
            self.actor_uuid = self.actor_id
        if self.reviewer_id and not self.reviewer_uuid:
            self.reviewer_uuid = self.reviewer_id
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
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_gap_tickets",
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
        related_name="knowledge_gap_tickets",
    )
    feedback = models.ForeignKey(
        Feedback,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_gap_tickets",
    )
    feedback_uuid = models.UUIDField(null=True, blank=True, editable=False)
    question_snapshot = models.TextField(blank=True, default="")
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
    assignee_uuid = models.UUIDField(null=True, blank=True, editable=False)
    suggested_source = models.TextField(blank=True, default="")
    resolution_notes = models.TextField(blank=True, default="")
    sensitive_payload_scrubbed_at = models.DateTimeField(null=True, blank=True)
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
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(space__isnull=False)
                    | models.Q(space_uuid__isnull=False)
                ),
                name="chat_gap_space_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="chat_gap_locator_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        _capture_space_retention_evidence(self)
        if self.feedback_id and not self.feedback_uuid:
            self.feedback_uuid = self.feedback_id
        if self.assignee_id and not self.assignee_uuid:
            self.assignee_uuid = self.assignee_id
        super().save(*args, **kwargs)

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
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="compliance_export_jobs",
    )
    requested_by_uuid = models.UUIDField(null=True, blank=True, editable=False)
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
        on_delete=models.SET_NULL,
        related_name="compliance_export_jobs",
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
    sensitive_payload_scrubbed_at = models.DateTimeField(null=True, blank=True)
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
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(requested_by__isnull=False)
                    | models.Q(requested_by_uuid__isnull=False)
                ),
                name="chat_export_actor_evidence",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(locator_digest="")
                    | models.Q(locator_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="chat_export_locator_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        _capture_space_retention_evidence(self)
        if self.requested_by_id and not self.requested_by_uuid:
            self.requested_by_uuid = self.requested_by_id
        super().save(*args, **kwargs)

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
