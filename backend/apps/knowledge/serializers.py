"""Knowledge serializers."""

from rest_framework import serializers
from .models import DocumentCategory, Document, DocumentChunk, AnswerTemplate


class DocumentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentCategory
        fields = ["id", "name", "slug", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DocumentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "title", "file", "file_type", "file_size",
            "category", "category_name", "tags", "status",
            "version", "effective_from", "effective_to",
            "chunk_count", "processing_error", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "version", "chunk_count",
            "processing_error", "created_at", "updated_at",
        ]


class DocumentDetailSerializer(DocumentSerializer):
    """Extended serializer with chunks info."""
    chunk_count = serializers.IntegerField(read_only=True)

    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + ["uploaded_by"]


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = ["id", "document", "content", "chunk_index", "page_number", "metadata"]
        read_only_fields = ["id"]


class AnswerTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerTemplate
        fields = ["id", "question_pattern", "answer", "language", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
