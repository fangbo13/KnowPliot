"""Audit admin."""

from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "action", "target_type", "ip_address", "created_at"]
    list_filter = ["action", "target_type"]
    search_fields = ["user__email", "target_type"]
    readonly_fields = ["id", "created_at"]
    date_hierarchy = "created_at"
