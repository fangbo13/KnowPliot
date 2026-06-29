# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Audit serializers."""

from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "user_email", "action", "target_type",
            "target_id", "details", "ip_address", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
