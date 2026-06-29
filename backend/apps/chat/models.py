# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Chat models."""

import uuid

from django.db import models
from django.conf import settings


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
    rating = models.IntegerField(choices=RATING_CHOICES)
    reason = models.CharField(
        max_length=20, choices=REASON_CHOICES, null=True, blank=True
    )
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_feedback"
        unique_together = ["message"]

    def __str__(self):
        return f"Feedback {self.rating} for message {self.message.id}"
