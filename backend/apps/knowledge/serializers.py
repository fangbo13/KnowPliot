"""Knowledge serializers — V4.1 KB-V4.1-006/008: Magic number + file size validation.

DocumentSerializer now validates:
- V4.1 SYS-V4.1-012: File size against settings.MAX_UPLOAD_SIZE_MB (existing)
- V4.1 KB-V4.1-006: File content type matches declared file_type (magic number)
- V4.1 KB-V4.1-008: Min/max file size enforcement
"""

from django.conf import settings
from rest_framework import serializers
from apps.core.validators import validate_file_content_type, validate_file_size, MIN_FILE_SIZE
from .models import DocumentCategory, Document, DocumentChunk, AnswerTemplate


class DocumentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentCategory
        fields = ["id", "name", "slug", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DocumentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    def validate_file(self, value):
        """Validate uploaded file: size limits + magic number content type check.

        V4.1 SYS-V4.1-012: Max file size against MAX_UPLOAD_SIZE_MB setting.
        V4.1 KB-V4.1-006: Magic number validation — content must match declared type.
        V4.1 KB-V4.1-008: Min file size — reject empty/near-empty files.
        """
        # V4.1 SYS-V4.1-012: Max file size check (existing, preserved)
        max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if value.size > max_size_bytes:
            raise serializers.ValidationError(
                "File size exceeds the limit of %dMB. "
                "Your file is %.1fMB."
                % (settings.MAX_UPLOAD_SIZE_MB, value.size / 1024 / 1024)
            )

        # V4.1 KB-V4.1-008: Min file size check
        if value.size < MIN_FILE_SIZE:
            raise serializers.ValidationError(
                f"File is too small ({value.size} bytes). Minimum size is 1KB."
            )

        # V4.1 KB-V4.1-006: Magic number content type validation
        declared_type = self.initial_data.get("file_type")
        if declared_type:
            validate_file_content_type(value, declared_type)

        return value

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
