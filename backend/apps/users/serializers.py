"""User serializers — V4.0 RBAC extended.

UserSerializer now includes roles[] and permissions[] from RBAC system.
is_hr_admin is preserved for Phase 2 dual-authorization window.
"""

from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile — includes RBAC roles and permissions."""

    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "employee_id",
            "service_line",
            "office_location",
            "role_level",
            "start_date",
            "language_preference",
            "is_hr_admin",
            "roles",
            "permissions",
        ]
        read_only_fields = ["id", "email", "username", "employee_id", "roles", "permissions"]

    def get_roles(self, obj):
        """Return list of active role names from RBAC UserRole."""
        from apps.rbac.models import UserRole
        return list(
            UserRole.objects.filter(
                user=obj, is_active=True
            ).values_list("role__name", flat=True)
        )

    def get_permissions(self, obj):
        """Return list of active permission codenames from RBAC chain."""
        return list(obj.get_permissions())


class UserPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for updating user preferences."""

    class Meta:
        model = User
        fields = ["language_preference"]


class UserManageSerializer(serializers.ModelSerializer):
    """Serializer for Admin user management — includes role assignment info."""

    roles = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "employee_id",
            "service_line",
            "office_location",
            "role_level",
            "is_hr_admin",
            "roles",
            "is_active",
            "start_date",
            "language_preference",
        ]
        read_only_fields = ["id", "email", "roles", "is_active"]

    def get_roles(self, obj):
        from apps.rbac.models import UserRole
        return list(
            UserRole.objects.filter(
                user=obj, is_active=True
            ).values_list("role__name", flat=True)
        )

    def get_is_active(self, obj):
        return obj.is_active
