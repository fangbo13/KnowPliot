# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Users admin."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "employee_id", "service_line", "office_location", "is_hr_admin", "is_active"]
    list_filter = ["service_line", "is_hr_admin", "is_active", "start_date"]
    search_fields = ["email", "employee_id", "username"]
    ordering = ["-date_joined"]

    fieldsets = BaseUserAdmin.fieldsets + (
        ("EY Profile", {
            "fields": (
                "employee_id", "service_line", "office_location",
                "role_level", "start_date", "language_preference",
                "manager", "buddy", "is_hr_admin",
            ),
        }),
    )
