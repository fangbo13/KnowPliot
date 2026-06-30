# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

import uuid
from django.db import models
from django.conf import settings
from apps.spaces.models import BusinessLine, KnowledgeSpace, Organization


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

    class Meta:
        db_table = "scenario_templates_scenariotemplate"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} [{self.code}]"


class ScenarioTemplateApplication(models.Model):
    """Immutable record of a template being used to create a KnowledgeSpace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        ScenarioTemplate,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    space = models.ForeignKey(
        KnowledgeSpace,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_applications",
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
    template_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "scenario_templates_application"
        ordering = ["-created_at"]

    def __str__(self):
        space_code = self.space.code if self.space else "deleted-space"
        return f"{self.template.code} -> {space_code}"


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

    def __str__(self):
        return f"{self.template.code} v{self.version}"
