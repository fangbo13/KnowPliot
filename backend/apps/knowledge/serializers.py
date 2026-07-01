# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge serializers with canonical file policy and safe API fields."""

from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from apps.knowledge.batch import sanitize_title  # V4.2 BATCH-008
from apps.knowledge.file_policy import (
    derive_document_type,
    validate_document_content,
    validate_document_size,
)
from .models import DocumentCategory, Document, DocumentChunk, AnswerTemplate


class DocumentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentCategory
        fields = ["id", "name", "slug", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class DocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    title = serializers.CharField(required=False)
    file_type = serializers.ChoiceField(
        choices=Document.FILE_TYPE_CHOICES,
        required=False,
    )
    file_size = serializers.IntegerField(required=False, min_value=0)
    download_url = serializers.HyperlinkedIdentityField(
        view_name="document-download",
        read_only=True,
    )
    category_name = serializers.CharField(source="category.name", read_only=True)

    def validate_file(self, value):
        """Validate upload size before cross-field content checks."""
        validate_document_size(value.size)
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        uploaded_file = attrs.get("file")
        if uploaded_file is None:
            immutable_errors = {}
            if "file_type" in attrs:
                immutable_errors["file_type"] = (
                    "File type can only change when replacing the file."
                )
            if "file_size" in attrs:
                immutable_errors["file_size"] = (
                    "File size can only change when replacing the file."
                )
            if immutable_errors:
                raise serializers.ValidationError(immutable_errors)
            return attrs

        try:
            derived_type = derive_document_type(uploaded_file.name)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc

        declared_type = self.initial_data.get("file_type")
        if declared_type and declared_type != derived_type:
            raise serializers.ValidationError(
                {
                    "file_type": (
                        f"Declared file type '{declared_type}' does not match "
                        f"filename type '{derived_type}'."
                    )
                }
            )

        original_position = uploaded_file.tell()
        try:
            uploaded_file.seek(0)
            content = uploaded_file.read()
        finally:
            uploaded_file.seek(original_position)

        try:
            validate_document_content(content, derived_type)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc

        attrs["file_type"] = derived_type
        attrs["file_size"] = uploaded_file.size
        if not attrs.get("title"):
            attrs["title"] = sanitize_title(Path(uploaded_file.name).stem)
        return attrs

    def validate_title(self, value):
        """V4.2 KB-V4.2-BATCH-008: Sanitize title to prevent stored XSS."""
        sanitized = sanitize_title(value)
        if not sanitized:
            raise serializers.ValidationError("Title contains only dangerous characters.")
        return sanitized

    class Meta:
        model = Document
        fields = [
            "id", "title", "file", "download_url", "file_type", "file_size",
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
