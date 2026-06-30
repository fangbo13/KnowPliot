# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Serializers for the multi-space platform — V6.0."""

from rest_framework import serializers

from .models import (
    AdminRegistrationCode,
    BusinessLine,
    InviteCode,
    KnowledgeSpace,
    Organization,
    SpaceEmailInvite,
    SpaceMembership,
)


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "status", "created_at"]
        read_only_fields = fields


class BusinessLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessLine
        fields = ["id", "organization", "name", "code", "description", "status"]
        read_only_fields = ["id"]


class KnowledgeSpaceSerializer(serializers.ModelSerializer):
    """Read serializer — includes the requesting user's effective role."""

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    business_line_name = serializers.CharField(source="business_line.name", read_only=True, default=None)
    my_role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeSpace
        fields = [
            "id", "name", "code", "description", "icon", "language",
            "visibility", "status", "organization", "organization_name",
            "business_line", "business_line_name",
            "my_role", "member_count", "settings", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_my_role(self, obj):
        from .permissions import effective_space_role
        request = self.context.get("request")
        if not request:
            return None
        return effective_space_role(request.user, obj)

    def get_member_count(self, obj):
        # Prefetched/annotated where possible; falls back to a count query.
        return getattr(obj, "_member_count", None) or obj.memberships.filter(status="active").count()


class SpaceCreateSerializer(serializers.ModelSerializer):
    """Create serializer — organization optional (defaults to first/Default)."""

    class Meta:
        model = KnowledgeSpace
        fields = [
            "id", "name", "code", "description", "icon", "language",
            "visibility", "organization", "business_line",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "organization": {"required": False},
            "business_line": {"required": False},
            "visibility": {"required": False},
        }

    def validate_code(self, value):
        if KnowledgeSpace.objects.filter(code=value).exists():
            raise serializers.ValidationError("A space with this code already exists.")
        return value


class SpaceMembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = SpaceMembership
        fields = [
            "id", "space", "user", "user_email", "role", "status",
            "expires_at", "last_accessed_at", "created_at",
        ]
        read_only_fields = ["id", "space", "user", "user_email", "last_accessed_at", "created_at"]


class InviteCodeSerializer(serializers.ModelSerializer):
    """Read serializer — never exposes the code hash; only a display prefix."""

    class Meta:
        model = InviteCode
        fields = [
            "id", "space", "code_prefix", "role", "expires_at",
            "max_uses", "used_count", "status", "created_at",
        ]
        read_only_fields = fields


class InviteCodeCreateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[c[0] for c in SpaceMembership.ROLE_CHOICES],
        default=SpaceMembership.ROLE_MEMBER,
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    max_uses = serializers.IntegerField(required=False, min_value=0, default=0)


class JoinByCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64, trim_whitespace=True)


# ── V7.0 Admin registration codes ────────────────────────────────────

class AdminRegistrationCodeSerializer(serializers.ModelSerializer):
    """Read serializer — never exposes the hash; only the display prefix."""

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    business_line_name = serializers.CharField(
        source="business_line.name", read_only=True, default=None
    )

    class Meta:
        model = AdminRegistrationCode
        fields = [
            "id", "code_prefix", "grants_role", "organization", "organization_name",
            "business_line", "business_line_name", "expires_at", "max_uses",
            "used_count", "status", "created_at",
        ]
        read_only_fields = fields


class AdminRegistrationCodeCreateSerializer(serializers.Serializer):
    grants_role = serializers.ChoiceField(choices=[c[0] for c in AdminRegistrationCode.GRANT_CHOICES])
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    business_line = serializers.PrimaryKeyRelatedField(
        queryset=BusinessLine.objects.all(), required=False, allow_null=True
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    max_uses = serializers.IntegerField(required=False, min_value=0, default=0)

    def validate(self, attrs):
        role = attrs["grants_role"]
        bl = attrs.get("business_line")
        org = attrs["organization"]
        if role == AdminRegistrationCode.GRANT_CHOICES[1][0]:  # business_admin
            if bl is None:
                raise serializers.ValidationError(
                    {"business_line": "Required when granting business_admin."}
                )
            if bl.organization_id != org.id:
                raise serializers.ValidationError(
                    {"business_line": "Business line must belong to the organization."}
                )
        else:
            attrs["business_line"] = None  # org_admin ignores business_line
        return attrs


# ── V7.0 Space email invites ─────────────────────────────────────────

class SpaceEmailInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpaceEmailInvite
        fields = ["id", "email", "space", "role", "status", "expires_at", "created_at"]
        read_only_fields = ["id", "space", "status", "created_at"]


class AddMemberByEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=[c[0] for c in SpaceMembership.ROLE_CHOICES],
        default=SpaceMembership.ROLE_MEMBER,
    )


class UpdateMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[c[0] for c in SpaceMembership.ROLE_CHOICES])
