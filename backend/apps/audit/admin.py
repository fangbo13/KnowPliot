# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

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
