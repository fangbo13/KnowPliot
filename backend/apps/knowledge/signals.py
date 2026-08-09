"""Revision tracking for graph-affecting knowledge mutations."""

from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import (
    Document,
    DocumentLink,
    DocumentSimilarity,
    DocumentTag,
    KnowledgeGraphState,
)


def bump_graph_revision(space_id):
    if not space_id:
        return
    state, created = KnowledgeGraphState.objects.get_or_create(space_id=space_id)
    if not created:
        KnowledgeGraphState.objects.filter(space_id=space_id).update(revision=F("revision") + 1)


@receiver([post_save, post_delete], sender=Document)
@receiver([post_save, post_delete], sender=DocumentLink)
@receiver([post_save, post_delete], sender=DocumentSimilarity)
def graph_resource_changed(sender, instance, **kwargs):
    bump_graph_revision(instance.space_id)


@receiver([post_save, post_delete], sender=DocumentTag)
def graph_tag_changed(sender, instance, **kwargs):
    space_id = (
        Document.objects.filter(pk=instance.document_id)
        .values_list("space_id", flat=True)
        .first()
    )
    bump_graph_revision(space_id)
