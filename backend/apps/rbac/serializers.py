# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""RBAC serializers — V4.0 dual-track permission system."""

from rest_framework import serializers
from .models import Role, Permission, RolePermission, UserRole
from apps.users.models import User
from apps.users.serializers import UserManageSerializer


class RoleSerializer(serializers.ModelSerializer):
    """Role serializer with permission count."""

    permission_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "name", "label", "scope", "is_active", "permission_count", "created_at"]

    def get_permission_count(self, obj):
        return obj.role_permissions.filter(role__is_active=True).count()


class PermissionSerializer(serializers.ModelSerializer):
    """Permission codename serializer."""

    class Meta:
        model = Permission
        fields = ["id", "codename", "resource", "action", "label"]


class RolePermissionSerializer(serializers.ModelSerializer):
    """Role-Permission mapping serializer."""

    permission_codename = serializers.CharField(source="permission.codename", read_only=True)
    permission_label = serializers.CharField(source="permission.label", read_only=True)

    class Meta:
        model = RolePermission
        fields = ["id", "role", "permission", "permission_codename", "permission_label"]


class UserRoleSerializer(serializers.ModelSerializer):
    """User-Role assignment serializer."""

    role_name = serializers.CharField(source="role.name", read_only=True)
    role_label = serializers.CharField(source="role.label", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    assigned_by_email = serializers.CharField(source="assigned_by.email", read_only=True, default=None)

    class Meta:
        model = UserRole
        fields = [
            "id", "user", "role", "role_name", "role_label",
            "user_email", "assigned_by", "assigned_by_email",
            "is_active", "assigned_at",
        ]
        read_only_fields = ["id", "assigned_at", "assigned_by"]

    def create(self, validated_data):
        """Auto-fill assigned_by from request.user."""
        validated_data["assigned_by"] = self.context["request"].user
        return super().create(validated_data)


class UserRoleAssignSerializer(serializers.Serializer):
    """Serializer for assigning a role to a user (POST body)."""

    user_id = serializers.UUIDField()
    role_name = serializers.CharField()

    def validate_role_name(self, value):
        if not Role.objects.filter(name=value, is_active=True).exists():
            raise serializers.ValidationError(f"Role '{value}' does not exist or is inactive.")
        return value

    def validate_user_id(self, value):
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"User with id '{value}' does not exist.")
        return value

    def validate(self, data):
        # Check for duplicate assignment
        if UserRole.objects.filter(
            user_id=data["user_id"],
            role__name=data["role_name"],
            is_active=True,
        ).exists():
            raise serializers.ValidationError(
                f"User already has active role '{data['role_name']}'."
            )
        return data
