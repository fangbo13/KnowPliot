# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Compatibility wrappers for the canonical knowledge document policy."""

from apps.knowledge.file_policy import (
    DEFAULT_MAX_DOCUMENT_SIZE_MB,
    MIN_DOCUMENT_SIZE_BYTES,
    validate_document_size,
    validate_uploaded_document,
)


ALLOWED_MIME_TYPES = {
    "pdf": ["application/pdf"],
    "docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    "html": ["text/html"],
    "txt": ["text/plain"],
    "md": ["text/markdown", "text/plain"],
}

MIN_FILE_SIZE = MIN_DOCUMENT_SIZE_BYTES
MAX_FILE_SIZE_MB = DEFAULT_MAX_DOCUMENT_SIZE_MB


def validate_file_content_type(file_obj, declared_type: str) -> None:
    """Validate through the shared current-version document policy."""
    validate_uploaded_document(file_obj, declared_type)


def validate_file_size(file_obj) -> None:
    """Validate through the shared current-version size policy."""
    validate_document_size(file_obj.size)
