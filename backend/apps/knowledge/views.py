"""Knowledge views."""

import os

from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsHROrAdmin
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
        # Trigger async ingestion
        from apps.rag.services import ingest_document
        ingest_document.delay(str(doc.id))


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, delete a document."""

    serializer_class = DocumentDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return Document.objects.all()


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


class AnswerTemplateListView(generics.ListCreateAPIView):
    """List and create answer templates."""

    serializer_class = AnswerTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return AnswerTemplate.objects.filter(is_active=True)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AnswerTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, delete an answer template."""

    serializer_class = AnswerTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return AnswerTemplate.objects.all()
