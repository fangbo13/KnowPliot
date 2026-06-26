"""V4.2 Batch upload serializers.

Serializers for:
- BatchDocumentUploadSerializer: ZIP file upload validation
- BatchImportResultSerializer: Batch import result reporting
- DocumentSerializer: Updated with sanitize_title validator (BATCH-008)
"""

from django.conf import settings
from rest_framework import serializers
from apps.core.validators import validate_file_content_type, validate_file_size, MIN_FILE_SIZE
from apps.knowledge.batch import (
    validate_zip_content,
    sanitize_title,
    BULK_UPLOAD_MAX_DOCUMENTS,
    BULK_UPLOAD_TOTAL_SIZE_MB,
)
from .models import DocumentCategory, Document, DocumentChunk, AnswerTemplate, BatchImportResultRecord


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

    def validate_title(self, value):
        """V4.2 KB-V4.2-BATCH-008: Sanitize title to prevent stored XSS."""
        sanitized = sanitize_title(value)
        if not sanitized:
            raise serializers.ValidationError("Title contains only dangerous characters.")
        return sanitized

    class Meta:
        model = Document
        fields = [
            "id", "title", "file", "file_type", "file_size",
            "category", "category_name", "tags", "status",
            "version", "effective_from", "effective_to",
            "chunk_count", "processing_error", "content_hash", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "version", "chunk_count",
            "processing_error", "content_hash", "created_at", "updated_at",
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


class BatchDocumentUploadSerializer(serializers.Serializer):
    """V4.2: Batch upload serializer for ZIP file import.

    Validates ZIP file size, then delegates to batch.py for
    detailed Zip Bomb, path traversal, and type validation.
    """

    zip_file = serializers.FileField(required=True, help_text="ZIP file containing documents to import")
    source_tag = serializers.CharField(
        max_length=50, default="EY_Batch",
        help_text="Source label for imported documents (default: EY_Batch)",
    )
    category = serializers.UUIDField(
        required=False, allow_null=True,
        help_text="Optional category UUID for all imported documents",
    )

    def validate_zip_file(self, value):
        """Validate ZIP file: size limit + content validation.

        BATCH-001: Zip Bomb detection.
        BATCH-002: Path traversal prevention.
        BATCH-003: Inner file type validation.
        BATCH-004: Size limits (total ZIP ≤ 500MB).
        """
        # Size check on the ZIP itself
        max_zip_bytes = BULK_UPLOAD_TOTAL_SIZE_MB * 1024 * 1024
        if value.size > max_zip_bytes:
            raise serializers.ValidationError(
                f"ZIP file size ({value.size / 1024 / 1024:.1f}MB) exceeds "
                f"maximum of {BULK_UPLOAD_TOTAL_SIZE_MB}MB."
            )

        # Minimum size check (reject empty ZIP)
        if value.size < MIN_FILE_SIZE:
            raise serializers.ValidationError(
                f"ZIP file is too small ({value.size} bytes). Minimum size is 1KB."
            )

        # MIME type check: must be a ZIP
        header = value.read(261)
        value.seek(0)

        import filetype as ft
        kind = ft.guess(header)
        if kind is None or kind.mime != "application/zip":
            raise serializers.ValidationError(
                "Uploaded file is not a valid ZIP archive. "
                f"Detected type: {kind.mime if kind else 'unknown'}."
            )

        # Full ZIP content validation (BATCH-001/002/003/008)
        validation_result = validate_zip_content(value)
        value.seek(0)  # Reset after validation reads

        if validation_result["valid_count"] == 0:
            raise serializers.ValidationError(
                "ZIP contains no valid documents. "
                f"Rejected: {validation_result['rejected_count']} files. "
                f"Reasons: {[r['reason'] for r in validation_result['rejected_files'][:3]]}"
            )

        # Store validation result for use in view
        self._validation_result = validation_result
        return value

    def validate_category(self, value):
        """Validate that category exists if provided."""
        if value is not None:
            try:
                DocumentCategory.objects.get(id=value)
            except DocumentCategory.DoesNotExist:
                raise serializers.ValidationError("Category not found.")
        return value


class BatchImportResultSerializer(serializers.ModelSerializer):
    """V4.2: Serializer for batch import result records."""

    class Meta:
        model = BatchImportResultRecord
        fields = [
            "id", "total_files", "success_count", "duplicate_skipped_count",
            "failed_count", "source_tag", "status", "error_message",
            "result_details", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
