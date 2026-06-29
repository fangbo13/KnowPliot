# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""V6.0 data migration: create the default space and backfill existing data.

The pre-V6.0 system had a single global knowledge base. This migration:
  1. creates a "Default Organization" -> "General" business line -> "General
     Knowledge Space";
  2. assigns every existing Document, DocumentChunk, ChatSession, Message,
     Citation, and Feedback to that default space;
  3. gives every existing user an active membership (owner for superusers /
     hr-admins, otherwise member) so current users keep access.

It is reversible as a no-op (we never delete migrated data on reverse).
"""

from django.conf import settings
from django.db import migrations


DEFAULT_SPACE_CODE = "general"


def forwards(apps, schema_editor):
    Organization = apps.get_model("spaces", "Organization")
    BusinessLine = apps.get_model("spaces", "BusinessLine")
    KnowledgeSpace = apps.get_model("spaces", "KnowledgeSpace")
    SpaceMembership = apps.get_model("spaces", "SpaceMembership")
    Document = apps.get_model("knowledge", "Document")
    DocumentChunk = apps.get_model("knowledge", "DocumentChunk")
    ChatSession = apps.get_model("chat", "ChatSession")
    Message = apps.get_model("chat", "Message")
    Citation = apps.get_model("chat", "Citation")
    Feedback = apps.get_model("chat", "Feedback")

    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)

    org, _ = Organization.objects.get_or_create(
        slug="default",
        defaults={"name": "Default Organization", "status": "active"},
    )
    business_line, _ = BusinessLine.objects.get_or_create(
        organization=org,
        code="general",
        defaults={"name": "General", "status": "active"},
    )
    space, _ = KnowledgeSpace.objects.get_or_create(
        code=DEFAULT_SPACE_CODE,
        defaults={
            "organization": org,
            "business_line": business_line,
            "name": "General Knowledge Space",
            "description": "Default space migrated from the single global knowledge base.",
            "visibility": "organization",
            "status": "active",
            "language": "en",
        },
    )

    # Backfill all space-scoped business objects to the default space.
    Document.objects.filter(space__isnull=True).update(space=space)
    DocumentChunk.objects.filter(space__isnull=True).update(space=space)
    ChatSession.objects.filter(space__isnull=True).update(space=space)
    Message.objects.filter(space__isnull=True).update(space=space)
    Citation.objects.filter(space__isnull=True).update(space=space)
    Feedback.objects.filter(space__isnull=True).update(space=space)

    # Give every existing user access to the default space.
    for user in User.objects.all().iterator():
        is_admin = bool(getattr(user, "is_superuser", False) or getattr(user, "is_hr_admin", False))
        SpaceMembership.objects.get_or_create(
            space=space,
            user=user,
            defaults={
                "role": "owner" if is_admin else "member",
                "status": "active",
            },
        )


def backwards(apps, schema_editor):
    # Non-destructive reverse: keep the default space and memberships.
    # (Unsetting space FKs would risk orphaning data; intentionally a no-op.)
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("spaces", "0001_initial"),
        ("knowledge", "0006_rename_knowledge_doc_content_hash_idx_knowledge_d_content_979d1d_idx_and_more"),
        ("chat", "0003_chatsession_space_citation_space_feedback_space_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
