# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

import hashlib
import unicodedata
import uuid
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.spaces.models import BusinessLine, KnowledgeSpace, Organization


def _locator_digest(value):
    canonical = unicodedata.normalize("NFC", value or "")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TemplateCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        db_table = "scenario_templates_category"
        ordering = ["name"]


class TemplateTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        db_table = "scenario_templates_tag"
        ordering = ["name"]


class ScenarioTemplate(models.Model):
    """ScenarioTemplate represents a predefined blueprint for KnowledgeSpaces."""

    SCENARIO_CHOICES = [
        ("onboarding", "Onboarding"),
        ("audit", "Audit"),
        ("tax", "Tax"),
        ("consulting", "Consulting"),
        ("core_services", "Core Business Services"),
        ("standards_qa", "Standards QA"),
        ("project_ai", "Project AI"),
    ]

    VISIBILITY_CHOICES = [
        ("private", "Private"),
        ("business_line", "Business Line Internal"),
        ("organization", "Organization Shared"),
        ("public_demo", "Public Demo"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True, default="")
    scenario_type = models.CharField(
        max_length=50, choices=SCENARIO_CHOICES, default="onboarding"
    )
    default_language = models.CharField(max_length=8, default="en")
    icon = models.CharField(max_length=50, blank=True, default="")
    category = models.ForeignKey(
        TemplateCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="templates",
    )
    tags = models.ManyToManyField(TemplateTag, blank=True, related_name="templates")
    featured = models.BooleanField(default=False)
    
    # Preseeded sample prompt questions for the chat interface in this space
    quick_questions = models.JSONField(default=list, blank=True)
    
    # Prompt engineering & system instruction config details
    prompt_policy = models.JSONField(default=dict, blank=True)
    
    # Vector search & retrieval thresholds/ratios config details
    retrieval_policy = models.JSONField(default=dict, blank=True)
    
    default_visibility = models.CharField(
        max_length=20, choices=VISIBILITY_CHOICES, default="private"
    )
    is_active = models.BooleanField(default=True)
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scenario_templates",
        help_text="Optional organization scope. Empty means global template.",
    )
    business_line = models.ForeignKey(
        BusinessLine,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scenario_templates",
        help_text="Optional business-line scope. Empty means global or organization-wide template.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_scenario_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    current_revision = models.ForeignKey(
        "ScenarioTemplateRevision",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="current_for_templates",
    )

    class Meta:
        db_table = "scenario_templates_scenariotemplate"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if self.current_revision_id:
            revision = self.current_revision
            if self.pk and revision.template_id != self.pk:
                raise ValidationError(
                    "A template current revision must belong to that template."
                )
            if revision.published_at is None:
                raise ValidationError(
                    "A template current revision must already be published."
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.code}]"


class ScenarioTemplateApplication(models.Model):
    """Immutable record of a template being used to create a KnowledgeSpace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        ScenarioTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications",
    )
    template_uuid = models.UUIDField(null=True, blank=True, editable=False)
    template_key_snapshot = models.CharField(
        max_length=120, blank=True, default="", editable=False
    )
    space = models.ForeignKey(
        KnowledgeSpace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_applications",
    )
    space_uuid = models.UUIDField(null=True, blank=True, editable=False)
    organization_uuid = models.UUIDField(null=True, blank=True, editable=False)
    locator_digest = models.CharField(
        max_length=64, blank=True, default="", editable=False
    )
    tombstone = models.ForeignKey(
        "spaces.WorkspaceTombstone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scenario_template_applications",
    )
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_applications",
    )
    business_line = models.ForeignKey(
        BusinessLine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_applications",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_applications_created",
    )
    created_by_uuid = models.UUIDField(null=True, blank=True, editable=False)
    provisioning_status = models.CharField(
        max_length=30,
        default="completed",
        choices=[
            ("completed", "Completed"),
            ("processing", "Processing"),
            ("partial_failure", "Partial Failure"),
        ],
    )
    asset_total = models.PositiveIntegerField(default=0)
    task_ids = models.JSONField(default=list, blank=True)
    template_snapshot = models.JSONField(default=dict, blank=True)
    sensitive_payload_scrubbed_at = models.DateTimeField(null=True, blank=True)
    template_revision = models.ForeignKey(
        "ScenarioTemplateRevision",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="applications",
    )
    template_revision_uuid = models.UUIDField(null=True, blank=True, editable=False)
    template_revision_hash = models.CharField(
        max_length=64, blank=True, default="", editable=False
    )
    legacy_revision_unknown = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scenario_templates_application"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(template__isnull=False)
                    | Q(template_uuid__isnull=False)
                ),
                name="scenario_app_template_evidence",
            ),
            models.CheckConstraint(
                check=(
                    Q(legacy_revision_unknown=True, template_revision__isnull=True)
                    | Q(
                        legacy_revision_unknown=False,
                        template_revision__isnull=False,
                        template_revision_uuid__isnull=False,
                        template_revision_hash__regex=r"^[0-9a-f]{64}$",
                    )
                ),
                name="scenario_app_revision_evidence",
            ),
            models.CheckConstraint(
                check=(
                    Q(locator_digest="")
                    | Q(locator_digest__regex=r"^[0-9a-f]{64}$")
                ),
                name="scenario_app_locator_shape",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.template_id:
            if not self.template_uuid:
                self.template_uuid = self.template_id
            if not self.template_key_snapshot:
                self.template_key_snapshot = self.template.code
        if self.space_id:
            if not self.space_uuid:
                self.space_uuid = self.space_id
            if not self.organization_uuid:
                self.organization_uuid = self.space.organization_id
            if not self.locator_digest:
                locator = getattr(self.space, "locator_reservation", None)
                if locator is not None:
                    self.locator_digest = _locator_digest(
                        locator.normalized_locator
                    )
        elif self.organization_id and not self.organization_uuid:
            self.organization_uuid = self.organization_id
        if self.created_by_id and not self.created_by_uuid:
            self.created_by_uuid = self.created_by_id
        if self.template_revision_id:
            if not self.template_revision_uuid:
                self.template_revision_uuid = self.template_revision_id
            if not self.template_revision_hash:
                self.template_revision_hash = self.template_revision.snapshot_hash
            self.legacy_revision_unknown = False
        super().save(*args, **kwargs)

    def __str__(self):
        space_code = self.space.code if self.space else "deleted-space"
        template_code = (
            self.template.code if self.template else self.template_key_snapshot
        )
        return f"{template_code} -> {space_code}"


class ScenarioTemplateRevision(models.Model):
    """Immutable snapshot of a template after create/update."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        ScenarioTemplate,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    version = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict, blank=True)
    snapshot_hash = models.CharField(max_length=64)
    published_at = models.DateTimeField(null=True, blank=True)
    change_note = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_revisions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scenario_templates_revision"
        ordering = ["-version"]
        unique_together = [("template", "version")]
        constraints = [
            models.CheckConstraint(
                check=Q(snapshot_hash__regex=r"^[0-9a-f]{64}$"),
                name="scenario_revision_hash_shape",
            )
        ]

    def save(self, *args, **kwargs):
        from .contract import normalize_revision_snapshot, snapshot_hash

        normalized = normalize_revision_snapshot(self.snapshot)
        calculated_hash = snapshot_hash(normalized)
        if self.snapshot_hash and self.snapshot_hash != calculated_hash:
            raise ValidationError("Scenario template revision hash does not match its snapshot.")

        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "template_id",
                "version",
                "snapshot",
                "snapshot_hash",
                "published_at",
                "change_note",
                "created_by_id",
                "created_at",
            ).first()
            if original and original["published_at"] is not None:
                candidate = {
                    "template_id": self.template_id,
                    "version": self.version,
                    "snapshot": normalized,
                    "snapshot_hash": calculated_hash,
                    "published_at": self.published_at,
                    "change_note": self.change_note,
                    "created_by_id": self.created_by_id,
                    "created_at": self.created_at,
                }
                if candidate != original:
                    raise ValidationError(
                        "Published scenario template revisions are immutable."
                    )

        self.snapshot = normalized
        self.snapshot_hash = calculated_hash
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.published_at is not None:
            raise ValidationError("Published scenario template revisions cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.template.code} v{self.version}"


class ScenarioTemplateAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        ScenarioTemplate,
        on_delete=models.CASCADE,
        related_name="assets",
    )
    document = models.ForeignKey(
        "knowledge.Document",
        on_delete=models.PROTECT,
        related_name="template_assets",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_assets_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scenario_templates_asset"
        unique_together = [("template", "document")]
        ordering = ["created_at"]


class TemplateAssetApplication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        ScenarioTemplateApplication,
        on_delete=models.CASCADE,
        related_name="asset_applications",
    )
    asset = models.ForeignKey(
        ScenarioTemplateAsset,
        on_delete=models.PROTECT,
        related_name="applications",
    )
    source_document = models.ForeignKey(
        "knowledge.Document",
        on_delete=models.PROTECT,
        related_name="template_copy_sources",
    )
    target_document = models.ForeignKey(
        "knowledge.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_copy_targets",
    )
    ingestion_job = models.ForeignKey(
        "knowledge.IngestionJob",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_asset_applications",
    )
    status = models.CharField(
        max_length=20,
        default="pending",
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("failed", "Failed"),
        ],
    )
    error_code = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scenario_templates_asset_application"
        unique_together = [("application", "asset")]
