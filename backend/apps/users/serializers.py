# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

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

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import User
from .identity import platform_admin_flags


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile — includes RBAC roles and permissions.

    V7.0: also surfaces platform/organization admin scope so the frontend can
    gate the admin console without (mis)using organizational role_level.
    """

    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    is_superuser = serializers.BooleanField(read_only=True)
    # V7.0 identity flags (axis one — who you are in the org)
    is_super_admin = serializers.SerializerMethodField()
    is_org_admin = serializers.SerializerMethodField()
    is_business_admin = serializers.SerializerMethodField()
    admin_scope = serializers.SerializerMethodField()

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
            "is_super_admin",
            "is_org_admin",
            "is_business_admin",
            "admin_scope",
        ]
        read_only_fields = [
            "id", "email", "username", "employee_id", "is_superuser", "roles",
            "permissions", "is_super_admin", "is_org_admin", "is_business_admin", "admin_scope",
        ]

    def _flags(self, obj):
        # Cache per-instance to avoid resolving admin scope four times.
        if not hasattr(obj, "_v7_flags"):
            obj._v7_flags = platform_admin_flags(obj)
        return obj._v7_flags

    def get_is_super_admin(self, obj):
        return self._flags(obj)["is_super_admin"]

    def get_is_org_admin(self, obj):
        return self._flags(obj)["is_org_admin"]

    def get_is_business_admin(self, obj):
        return self._flags(obj)["is_business_admin"]

    def get_admin_scope(self, obj):
        return self._flags(obj)["admin_scope"]

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


# ── V7.0 Registration ────────────────────────────────────────────────

def _email_taken(email: str) -> bool:
    return User.objects.filter(email__iexact=email).exists()


def _validate_password_strength(password: str):
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": list(exc.messages)})


class RegisterSerializer(serializers.Serializer):
    """Regular self-registration — Service Line is mandatory (V7 §8)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    username = serializers.CharField(required=False, allow_blank=True, max_length=150)
    service_line = serializers.ChoiceField(choices=[c[0] for c in User.SERVICE_LINE_CHOICES])
    language_preference = serializers.ChoiceField(
        choices=[c[0] for c in User.LANGUAGE_CHOICES], required=False, default="en"
    )

    def validate_email(self, value):
        if _email_taken(value):
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        _validate_password_strength(attrs["password"])
        return attrs

    def create(self, validated_data):
        email = validated_data["email"]
        user = User(
            email=email,
            username=(validated_data.get("username") or email)[:150],
            service_line=validated_data["service_line"],
            language_preference=validated_data.get("language_preference", "en"),
        )
        user.set_password(validated_data["password"])
        # Approval gate: pending users are inactive until an admin approves them.
        from django.conf import settings
        if getattr(settings, "REQUIRE_SIGNUP_APPROVAL", False):
            user.is_active = False
        user.save()
        return user


class AdminRegisterSerializer(serializers.Serializer):
    """Admin registration via a tiered Admin Registration Code (V7 §8)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    username = serializers.CharField(required=False, allow_blank=True, max_length=150)
    code = serializers.CharField(max_length=64, trim_whitespace=True)

    def validate_email(self, value):
        if _email_taken(value):
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        _validate_password_strength(attrs["password"])
        return attrs

    def create(self, validated_data):
        email = validated_data["email"]
        user = User(
            email=email,
            username=(validated_data.get("username") or email)[:150],
        )
        user.set_password(validated_data["password"])
        user.save()  # admin-code users are always active (they hold a valid code)
        return user
