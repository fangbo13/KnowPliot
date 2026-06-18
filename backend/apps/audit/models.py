"""Audit log models."""

import uuid

from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """Audit log entry for admin actions."""

    ACTION_CHOICES = [
        ("document_upload", "Document Upload"),
        ("document_delete", "Document Delete"),
        ("document_reindex", "Document Reindex"),
        ("document_status_change", "Document Status Change"),
        ("template_create", "Template Create"),
        ("template_update", "Template Update"),
        ("template_delete", "Template Delete"),
        ("user_login", "User Login"),
        ("export_data", "Export Data"),
        ("category_create", "Category Create"),
        ("category_update", "Category Update"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    target_type = models.CharField(max_length=100, help_text="Model name")
    target_id = models.UUIDField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_auditlog"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.user} at {self.created_at}"
