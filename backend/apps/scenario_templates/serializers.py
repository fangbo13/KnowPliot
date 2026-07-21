# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from rest_framework import serializers
from .models import (
    ScenarioTemplate,
    ScenarioTemplateApplication,
    ScenarioTemplateRevision,
    ScenarioTemplateAsset,
    TemplateAssetApplication,
    TemplateCategory,
    TemplateTag,
)
from apps.spaces.models import KnowledgeSpace, Organization, BusinessLine
from .contract import normalize_components


class ScenarioTemplateSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    business_line_name = serializers.CharField(source="business_line.name", read_only=True, default=None)
    can_manage = serializers.SerializerMethodField()
    usage_count = serializers.SerializerMethodField()
    last_applied_at = serializers.SerializerMethodField()
    latest_version = serializers.SerializerMethodField()
    current_revision_id = serializers.UUIDField(read_only=True, allow_null=True)
    current_revision_version = serializers.SerializerMethodField()
    current_revision_hash = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    category_id = serializers.PrimaryKeyRelatedField(
        source="category",
        queryset=TemplateCategory.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )
    tag_ids = serializers.PrimaryKeyRelatedField(
        source="tags",
        queryset=TemplateTag.objects.all(),
        required=False,
        many=True,
        write_only=True,
    )

    class Meta:
        model = ScenarioTemplate
        fields = [
            "id", "name", "code", "description", "scenario_type",
            "default_language", "icon", "quick_questions",
            "category", "category_id", "tags", "tag_ids", "featured",
            "prompt_policy", "retrieval_policy", "default_visibility",
            "is_active", "organization", "organization_name",
            "business_line", "business_line_name",
            "can_manage", "usage_count", "last_applied_at",
            "latest_version", "current_revision_id", "current_revision_version",
            "current_revision_hash",
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
        request = self.context.get("request")
        if request:
            from .views import _can_manage_template

            if not _can_manage_template(request.user, obj):
                return obj.current_revision.version if obj.current_revision_id else 0
        latest = obj.revisions.order_by("-version").first()
        return latest.version if latest else 0

    def get_current_revision_version(self, obj):
        return obj.current_revision.version if obj.current_revision_id else None

    def get_current_revision_hash(self, obj):
        return obj.current_revision.snapshot_hash if obj.current_revision_id else None

    def get_category(self, obj):
        if not obj.category_id:
            return None
        return {"id": str(obj.category_id), "name": obj.category.name, "slug": obj.category.slug}

    def get_tags(self, obj):
        return [
            {"id": str(tag.id), "name": tag.name, "slug": tag.slug}
            for tag in obj.tags.all()
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.current_revision_id:
            from .contract import legacy_template_projection

            data.update(legacy_template_projection(instance.current_revision.snapshot))
        return data

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
        if self.instance is not None:
            immutable_changes = {}
            if "code" in attrs and attrs["code"] != self.instance.code:
                immutable_changes["code"] = "Template keys are immutable; clone to a new key."
            if (
                "organization" in attrs
                and getattr(attrs["organization"], "pk", None)
                != self.instance.organization_id
            ):
                immutable_changes["organization"] = (
                    "Template scope is immutable; clone into the target scope."
                )
            if (
                "business_line" in attrs
                and getattr(attrs["business_line"], "pk", None)
                != self.instance.business_line_id
            ):
                immutable_changes["business_line"] = (
                    "Template scope is immutable; clone into the target scope."
                )
            if "is_active" in attrs and attrs["is_active"] != self.instance.is_active:
                immutable_changes["is_active"] = (
                    "Use the archive or restore transition endpoint."
                )
            if immutable_changes:
                raise serializers.ValidationError(immutable_changes)
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
            "template_revision", "legacy_revision_unknown",
            "template_snapshot", "provisioning_status", "asset_total",
            "task_ids", "created_at",
        ]
        read_only_fields = fields


class ScenarioTemplateRevisionSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = ScenarioTemplateRevision
        fields = [
            "id", "template", "version", "snapshot", "snapshot_hash",
            "published_at", "change_note",
            "created_by", "created_by_email", "created_at",
        ]
        read_only_fields = fields


class ScenarioTemplateRevisionCreateSerializer(serializers.Serializer):
    expected_template_version = serializers.IntegerField(min_value=0)
    components = serializers.JSONField()

    def validate_components(self, value):
        return normalize_components(value)

    def validate(self, attrs):
        unknown = sorted(set(self.initial_data) - {"expected_template_version", "components"})
        if unknown:
            raise serializers.ValidationError({"unknown_fields": unknown})
        return attrs


class ScenarioTemplateRevisionActivateSerializer(serializers.Serializer):
    expected_template_version = serializers.IntegerField(min_value=1)
    expected_revision_hash = serializers.RegexField(r"^[0-9a-f]{64}$")

    def validate(self, attrs):
        unknown = sorted(
            set(self.initial_data)
            - {"expected_template_version", "expected_revision_hash"}
        )
        if unknown:
            raise serializers.ValidationError({"unknown_fields": unknown})
        return attrs


class ScenarioTemplateAssetSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source="document.title", read_only=True)
    source_space = serializers.UUIDField(source="document.space_id", read_only=True)

    class Meta:
        model = ScenarioTemplateAsset
        fields = [
            "id", "template", "document", "document_title", "source_space",
            "created_by", "created_at",
        ]
        read_only_fields = [
            "id", "template", "document_title", "source_space",
            "created_by", "created_at",
        ]


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
