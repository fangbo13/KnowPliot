"""Knowledge views — V4.1 SYS-V4.1-006: Document reindex concurrency protection.

Added select_for_update() + transaction.atomic() to prevent parallel
ingest_document tasks from running simultaneously on the same document.

V4.2 KB-V4.2-BATCH-004: Added DocumentUploadRateThrottle to all upload views.
"""

import os

from django.conf import settings
from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsHROrAdmin
from apps.audit.views import create_audit_log
from apps.spaces.permissions import (  # V6.0 space isolation
    DOCUMENT_DELETE,
    SpaceDocumentPermission,
    has_space_permission,
    is_platform_admin,
    resolve_request_space,
)
from .models import DocumentCategory, Document, DocumentChunk, AnswerTemplate
from .serializers import (
    DocumentCategorySerializer,
    DocumentSerializer,
    DocumentDetailSerializer,
    DocumentChunkSerializer,
    AnswerTemplateSerializer,
)
# V4.2 KB-V4.2-BATCH-004: Upload rate throttle
from .batch_views import DocumentUploadRateThrottle


def _active_doc_space(request):
    """Resolve the active space for document operations.

    Uses the X-Space-Id header when present, else falls back to the default
    'general' space so admin uploads without a header are still scoped.
    """
    space = resolve_request_space(request, required=False)
    if space is not None:
        return space
    from apps.spaces.models import KnowledgeSpace
    return KnowledgeSpace.objects.filter(code="general").first()


class DocumentListCreateView(generics.ListCreateAPIView):
    """List and upload documents (admin only).

    V4.2 KB-V4.2-BATCH-004: Added upload rate throttle (10/minute/user).
    """

    # V6.0: space-aware document permission (replaces global IsHROrAdmin gate).
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]
    throttle_classes = [DocumentUploadRateThrottle]  # V4.2 BATCH-004

    def get_queryset(self):
        # V6.0: scope the document list to the active space when a header is sent.
        qs = Document.objects.all()
        space = resolve_request_space(self.request, required=False)
        if space is not None:
            qs = qs.filter(space=space)
        category = self.request.query_params.get("category")
        status_filter = self.request.query_params.get("status")
        if category:
            qs = qs.filter(category__slug=category)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DocumentSerializer
        return DocumentDetailSerializer

    def perform_create(self, serializer):
        # V6.0: uploads land in the active space (header) or default 'general'.
        space = _active_doc_space(self.request)
        doc = serializer.save(uploaded_by=self.request.user, space=space)
        create_audit_log(
            user=self.request.user,
            action="document_upload",
            target_type="Document",
            target_id=str(doc.id),
            details={"title": doc.title, "file_type": doc.file_type,
                     "space": str(space.id) if space else None},
            request=self.request,
        )
        # Trigger async ingestion
        from apps.rag.services import ingest_document
        ingest_document.delay(str(doc.id))


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, delete a document."""

    serializer_class = DocumentDetailSerializer
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]

    def get_queryset(self):
        # V6.0: when a space is active, only that space's documents are reachable.
        qs = Document.objects.all()
        space = resolve_request_space(self.request, required=False)
        if space is not None:
            qs = qs.filter(space=space)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # V6.0: a document may be deleted by a platform admin, the uploader, or a
        # user with the space's document.delete permission (owner / knowledge
        # admin / org / business admin). Prevents cross-user/space deletion.
        allowed = is_platform_admin(request.user) or instance.uploaded_by == request.user
        if not allowed and instance.space_id is not None:
            allowed = has_space_permission(request.user, instance.space, DOCUMENT_DELETE)
        if not allowed:
            return Response(
                {"detail": "You do not have permission to delete this document."},
                status=status.HTTP_403_FORBIDDEN,
            )
        create_audit_log(
            user=request.user,
            action="document_delete",
            target_type="Document",
            target_id=str(instance.id),
            details={"title": instance.title},
            request=request,
        )

        # Citations protect their source document/chunk so historical answers do
        # not silently lose provenance. For an explicit document delete, remove
        # those citation rows first, then let Document.delete cascade chunks.
        # Without this, documents that have ever been cited fail with
        # ProtectedError and the UI appears unable to delete them.
        from apps.chat.models import Citation

        with transaction.atomic():
            Citation.objects.filter(document=instance).delete()
            self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentReindexView(generics.GenericAPIView):
    """Trigger re-indexing of a document."""

    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]

    def get_queryset(self):
        return Document.objects.all()

    # V4.1 SYS-V4.1-006: select_for_update() + transaction prevents concurrent reindex
    def post(self, request, pk):
        # V6.0: scope the reindex target to the active space (can't reindex a
        # document outside the space you're operating in).
        active_space = resolve_request_space(request, required=False)
        # Acquire row-level lock and check status atomically
        try:
            with transaction.atomic():
                qs = Document.objects.select_for_update()
                if active_space is not None:
                    qs = qs.filter(space=active_space)
                document = qs.get(id=pk)
                if document.status == "processing":
                    return Response(
                        {"error": "Document is already being processed"},
                        status=status.HTTP_409_CONFLICT,
                    )
                document.status = "processing"
                document.save(update_fields=["status"])
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=404)

        create_audit_log(
            user=request.user,
            action="document_reindex",
            target_type="Document",
            target_id=str(document.id),
            details={"title": document.title},
            request=request,
        )

        # Trigger Celery task OUTSIDE the transaction (avoid long DB lock)
        from apps.rag.services import ingest_document
        ingest_document.delay(str(document.id))

        return Response({"status": "reindexing started"})


class DocumentChunksView(generics.ListAPIView):
    """View chunks of a document."""

    serializer_class = DocumentChunkSerializer
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]

    def get_queryset(self):
        qs = DocumentChunk.objects.filter(document_id=self.kwargs["document_id"])
        space = resolve_request_space(self.request, required=False)
        if space is not None:
            qs = qs.filter(space=space)  # V6.0 space isolation
        return qs.order_by("chunk_index")


class CategoryListView(generics.ListCreateAPIView):
    """List and create document categories.

    V4.0 RBAC fix: POST (create) requires category.create permission
    (HR/Admin only). GET (list) is available to all authenticated users.
    """

    serializer_class = DocumentCategorySerializer

    def get_permissions(self):
        """V4.0: Separate GET/POST permission requirements.

        GET: Any authenticated user can list categories (needed for chat dropdown).
        POST: Only HR/Admin can create categories (category.create codename).
        """
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsHROrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return DocumentCategory.objects.all()

    def perform_create(self, serializer):
        instance = serializer.save()
        create_audit_log(
            user=self.request.user,
            action="category_create",
            target_type="DocumentCategory",
            target_id=str(instance.id),
            details={"name": instance.name},
            request=self.request,
        )


class AnswerTemplateListView(generics.ListCreateAPIView):
    """List and create answer templates."""

    serializer_class = AnswerTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return AnswerTemplate.objects.filter(is_active=True)

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        create_audit_log(
            user=self.request.user,
            action="template_create",
            target_type="AnswerTemplate",
            target_id=str(instance.id),
            details={"question_pattern": instance.question_pattern},
            request=self.request,
        )


class AnswerTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, delete an answer template."""

    serializer_class = AnswerTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return AnswerTemplate.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        create_audit_log(
            user=request.user,
            action="template_delete",
            target_type="AnswerTemplate",
            target_id=str(instance.id),
            details={"question_pattern": instance.question_pattern},
            request=request,
        )
        return super().destroy(request, *args, **kwargs)
