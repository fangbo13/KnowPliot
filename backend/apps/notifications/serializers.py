# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Notification serializers — V7.0."""

from rest_framework import serializers

from .models import Announcement


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = [
            "id", "title", "body", "level", "audience", "audience_ref",
            "version", "is_active", "published_at", "created_at",
        ]
        read_only_fields = ["id", "published_at", "created_at"]


class AnnouncementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ["id", "title", "body", "level", "audience", "audience_ref", "version"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        audience = attrs.get("audience", Announcement.AUDIENCE_ALL)
        ref = (attrs.get("audience_ref") or "").strip()
        if audience != Announcement.AUDIENCE_ALL and not ref:
            raise serializers.ValidationError(
                {"audience_ref": "Required for org / business_line / role audiences."}
            )
        if audience == Announcement.AUDIENCE_ROLE and ref not in {
            "super_admin", "org_admin", "business_admin", "employee",
        }:
            raise serializers.ValidationError(
                {"audience_ref": "Role must be super_admin / org_admin / business_admin / employee."}
            )
        return attrs
