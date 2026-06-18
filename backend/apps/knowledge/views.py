"""Knowledge views."""

import os

from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsHROrAdmin
from apps.audit.views import create_audit_log
from .models import DocumentCategory, Document, DocumentChunk, AnswerTemplate
from .serializers import (
    DocumentCategorySerializer,
    DocumentSerializer,
    DocumentDetailSerializer,
    DocumentChunkSerializer,
    AnswerTemplateSerializer,
)


class DocumentListCreateView(generics.ListCreateAPIView):
    """List and upload documents (admin only)."""

    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        qs = Document.objects.all()
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
        doc = serializer.save(uploaded_by=self.request.user)
        create_audit_log(
            user=self.request.user,
            action="document_upload",
            target_type="Document",
            target_id=str(doc.id),
            details={"title": doc.title, "file_type": doc.file_type},
            request=self.request,
        )
        # Trigger async ingestion
        from apps.rag.services import ingest_document
        ingest_document.delay(str(doc.id))


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, delete a document."""

    serializer_class = DocumentDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return Document.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        create_audit_log(
            user=request.user,
            action="document_delete",
            target_type="Document",
            target_id=str(instance.id),
            details={"title": instance.title},
            request=request,
        )
        return super().destroy(request, *args, **kwargs)


class DocumentReindexView(generics.GenericAPIView):
    """Trigger re-indexing of a document."""

    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return Document.objects.all()

    def post(self, request, pk):
        document = self.get_object()
        document.status = "processing"
        document.save()

        create_audit_log(
            user=request.user,
            action="document_reindex",
            target_type="Document",
            target_id=str(document.id),
            details={"title": document.title},
            request=request,
        )

        from apps.rag.services import ingest_document
        ingest_document.delay(str(document.id))

        return Response({"status": "reindexing started"})


class DocumentChunksView(generics.ListAPIView):
    """View chunks of a document."""

    serializer_class = DocumentChunkSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return DocumentChunk.objects.filter(document_id=self.kwargs["document_id"]).order_by(
            "chunk_index"
        )


class CategoryListView(generics.ListCreateAPIView):
    """List and create document categories."""

    serializer_class = DocumentCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

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
