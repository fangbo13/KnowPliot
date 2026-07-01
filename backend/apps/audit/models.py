# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Audit log models — V4.0 extended with system-level actions and role_used.

V3.8: 11 ACTION_CHOICES (content domain only)
V4.0: +9 system-level ACTION_CHOICES + role_used field for dual-role audit tracing
"""

import uuid

from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """Audit log entry for admin actions.

    V4.0: Extended with 9 new system-level action types and role_used
    field for tracking which role (hr/admin) was active during the operation.
    """

    ACTION_CHOICES = [
        # ── Content domain (V3.8 original) ──
        ("document_upload", "Document Upload"),
        ("document_download", "Document Download"),
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
        # ── System domain (V4.0 new) ──
        ("role_assign", "Role Assign"),
        ("role_revoke", "Role Revoke"),
        ("user_create", "User Create"),
        ("user_update", "User Update"),
        ("user_deactivate", "User Deactivate"),
        ("config_change", "Config Change"),
        ("system_health_view", "System Health View"),
        ("audit_export", "Audit Export"),
        ("role_change_log", "Role Change Log"),
        # ── Crawler domain (V4.1) — retained for historical log compatibility.
        #    V6.0 retired the crawler; no new logs of these types are produced.
        ("document_crawl", "Document Crawl"),
        ("document_crawl_withdraw", "Document Crawl Withdraw"),
        # ── Batch domain (V4.2 new) ──
        ("document_batch_import", "Document Batch Import"),
        ("document_batch_result_view", "Document Batch Result View"),
        # ── Space domain (V6.0 new) ──
        ("space_create", "Space Create"),
        ("space_update", "Space Update"),
        ("space_archive", "Space Archive"),
        ("space_switch", "Space Switch"),
        ("space_join", "Space Join (Access Code)"),
        ("space_invite_create", "Space Invite Code Create"),
        ("space_invite_revoke", "Space Invite Code Revoke"),
        ("space_member_add", "Space Member Add"),
        ("space_member_update", "Space Member Update"),
        ("permission_denied", "Permission Denied"),
        # ── Identity / Governance domain (V7.0 new) ──
        ("user_register", "User Register"),
        ("admin_code_register", "Admin Code Register"),
        ("admin_code_create", "Admin Code Create"),
        ("admin_code_revoke", "Admin Code Revoke"),
        ("space_member_remove", "Space Member Remove"),
        ("space_email_invite", "Space Email Invite"),
        ("notification_broadcast", "Notification Broadcast"),
        ("signup_approved", "Signup Approved"),
        ("signup_rejected", "Signup Rejected"),
        ("user_promote_superadmin", "User Promote Super Admin"),
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
    # V4.0: role_used tracks which role was active during the operation
    # (hr/admin/superuser/employee) — critical for dual-role audit tracing
    role_used = models.CharField(max_length=20, blank=True, default="", help_text="Role used for this action")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_auditlog"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.user} at {self.created_at}"
