"""User serializers — V4.0 RBAC extended.

UserSerializer now includes roles[] and permissions[] from RBAC system.
is_hr_admin is preserved for Phase 2 dual-authorization window.

V4.3 UAT FIX: get_roles() now includes superuser bypass and is_hr_admin fallback,
matching the logic in CustomTokenObtainPairSerializer.validate(). Previously,
/admin/dashboard and /admin/knowledge were inaccessible because:
- LoginPage.tsx didn't pass roles/permissions from profile API → AuthProvider derived
  roles from role_level (organizational value "partner", not RBAC "admin") → RoleGuard denied
- UserSerializer.get_roles() didn't include superuser bypass → /api/v1/auth/me/ returned
  roles=[] for superusers without UserRole records → login() got roles=[]
"""

from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile — includes RBAC roles and permissions."""

    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    is_superuser = serializers.BooleanField(read_only=True)

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
            "is_superuser",
            "roles",
            "permissions",
        ]
        read_only_fields = ["id", "email", "username", "employee_id", "is_superuser", "roles", "permissions"]

    def get_roles(self, obj):
        """Return list of active role names from RBAC UserRole.

        V4.3 UAT FIX: Now includes superuser bypass (is_superuser → 'admin') and
        is_hr_admin fallback (is_hr_admin → 'hr'), matching CustomTokenObtainPairSerializer.
        Previously only queried UserRole table, missing superusers without UserRole records.
        """
        roles = []
        # Superuser bypass: superusers implicitly have 'admin' role
        if obj.is_superuser:
            roles.append("admin")
        # RBAC UserRole records
        from apps.rbac.models import UserRole
        rbac_roles = list(
            UserRole.objects.filter(
                user=obj, is_active=True
            ).values_list("role__name", flat=True)
        )
        for role_name in rbac_roles:
            if role_name not in roles:  # Avoid duplicates (superuser already has 'admin')
                roles.append(role_name)
        # Phase 2 dual-authorization: is_hr_admin grants 'hr' role equivalent
        if getattr(obj, "is_hr_admin", False) and "hr" not in roles:
            roles.append("hr")
        return roles

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
