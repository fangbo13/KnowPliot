# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from rest_framework import serializers
from .models import (
    ScenarioTemplate,
    ScenarioTemplateApplication,
    ScenarioTemplateRevision,
)
from apps.spaces.models import KnowledgeSpace, Organization, BusinessLine


class ScenarioTemplateSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    business_line_name = serializers.CharField(source="business_line.name", read_only=True, default=None)
    can_manage = serializers.SerializerMethodField()
    usage_count = serializers.SerializerMethodField()
    last_applied_at = serializers.SerializerMethodField()
    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = ScenarioTemplate
        fields = [
            "id", "name", "code", "description", "scenario_type",
            "default_language", "icon", "quick_questions",
            "prompt_policy", "retrieval_policy", "default_visibility",
            "is_active", "organization", "organization_name",
            "business_line", "business_line_name",
            "can_manage", "usage_count", "last_applied_at",
            "latest_version",
            "created_by", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_can_manage(self, obj):
        request = self.context.get("request")
        if not request:
            return False
        from .views import _can_manage_template
        return _can_manage_template(request.user, obj)

    def get_usage_count(self, obj):
        request = self.context.get("request")
        if not request:
            return 0
        from .views import _application_scope_filter, is_any_admin
        if not is_any_admin(request.user):
            return 0
        return obj.applications.filter(_application_scope_filter(request.user)).count()

    def get_last_applied_at(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        from .views import _application_scope_filter, is_any_admin
        if not is_any_admin(request.user):
            return None
        latest = obj.applications.filter(_application_scope_filter(request.user)).order_by("-created_at").first()
        return latest.created_at if latest else None

    def get_latest_version(self, obj):
        latest = obj.revisions.order_by("-version").first()
        return latest.version if latest else 0

    def validate_code(self, value):
        # Ensure code is unique
        qs = ScenarioTemplate.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("A template with this code already exists.")
        return value

    def validate(self, attrs):
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        business_line = attrs.get("business_line", getattr(self.instance, "business_line", None))
        if business_line and organization and business_line.organization_id != organization.id:
            raise serializers.ValidationError({
                "business_line": "Business line must belong to the selected organization."
            })
        if business_line and organization is None:
            attrs["organization"] = business_line.organization
        return attrs


class ScenarioTemplateApplicationSerializer(serializers.ModelSerializer):
    template_code = serializers.CharField(source="template.code", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    space_code = serializers.CharField(source="space.code", read_only=True, default=None)
    space_name = serializers.CharField(source="space.name", read_only=True, default=None)
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)
    business_line_name = serializers.CharField(source="business_line.name", read_only=True, default=None)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = ScenarioTemplateApplication
        fields = [
            "id", "template", "template_code", "template_name",
            "space", "space_code", "space_name",
            "organization", "organization_name",
            "business_line", "business_line_name",
            "created_by", "created_by_email",
            "template_snapshot", "created_at",
        ]
        read_only_fields = fields


class ScenarioTemplateRevisionSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = ScenarioTemplateRevision
        fields = [
            "id", "template", "version", "snapshot", "change_note",
            "created_by", "created_by_email", "created_at",
        ]
        read_only_fields = fields


class CloneScenarioTemplateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.SlugField(max_length=120)
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), required=False, allow_null=True
    )
    business_line = serializers.PrimaryKeyRelatedField(
        queryset=BusinessLine.objects.all(), required=False, allow_null=True
    )
    is_active = serializers.BooleanField(required=False)

    def validate_code(self, value):
        if ScenarioTemplate.objects.filter(code=value).exists():
            raise serializers.ValidationError("A template with this code already exists.")
        return value


class CreateSpaceFromTemplateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.SlugField(max_length=120)
    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), required=False, allow_null=True
    )
    business_line = serializers.PrimaryKeyRelatedField(
        queryset=BusinessLine.objects.all(), required=False, allow_null=True
    )
    visibility = serializers.ChoiceField(
        choices=KnowledgeSpace.VISIBILITY_CHOICES, required=False
    )

    def validate_code(self, value):
        if KnowledgeSpace.objects.filter(code=value).exists():
            raise serializers.ValidationError("A space with this code already exists.")
        return value
