"""Django admin for multi-space models — V6.0."""

from django.contrib import admin

from .models import (
    BusinessLine,
    InviteCode,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "slug"]


@admin.register(BusinessLine)
class BusinessLineAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "organization", "status"]
    list_filter = ["status", "organization"]
    search_fields = ["name", "code"]


@admin.register(KnowledgeSpace)
class KnowledgeSpaceAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "organization", "business_line", "visibility", "status"]
    list_filter = ["visibility", "status", "organization"]
    search_fields = ["name", "code"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(SpaceMembership)
class SpaceMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "space", "role", "status", "last_accessed_at"]
    list_filter = ["role", "status"]
    search_fields = ["user__email", "space__name"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "organization", "business_line", "created_at"]
    list_filter = ["role", "organization"]
    search_fields = ["user__email", "organization__name"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ["space", "code_prefix", "role", "status", "used_count", "max_uses", "expires_at"]
    list_filter = ["status", "role"]
    search_fields = ["space__name", "code_prefix"]
    readonly_fields = ["id", "code_hash", "created_at"]
