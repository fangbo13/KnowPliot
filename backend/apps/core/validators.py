# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""File content validators — V4.1 KB-V4.1-006 magic number validation.

Validates that uploaded file content matches the declared file_type
using magic number (header bytes) detection, preventing file type
spoofing attacks where malicious binaries are renamed with safe extensions.
"""

import filetype
from django.core.exceptions import ValidationError


# V4.1 KB-V4.1-006: Allowed MIME types per declared file_type
ALLOWED_MIME_TYPES = {
    "pdf": ["application/pdf"],
    "docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    "doc": ["application/msword"],
    "txt": ["text/plain"],
    "csv": ["text/csv", "text/plain"],
    "xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ],
    "pptx": [
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ],
}

# V4.1 KB-V4.1-008: Min/max file size limits (in bytes)
MIN_FILE_SIZE = 1024  # 1KB — reject empty/near-empty files (DoS prevention)
MAX_FILE_SIZE_MB = 50  # 50MB default


def validate_file_content_type(file_obj, declared_type: str) -> None:
    """Validate that file content matches declared file_type using magic number detection.

    Reads the first 261 bytes (filetype's minimum requirement) to determine
    the actual content type. Prevents attackers from uploading malicious binaries
    (e.g., PE executables, shell scripts) renamed as .pdf or .docx.

    Args:
        file_obj: Django UploadedFile object.
        declared_type: The file_type field value declared by the user.

    Raises:
        ValidationError: If content type does not match declared type.
    """
    header = file_obj.read(261)
    file_obj.seek(0)  # Reset position for subsequent reads

    kind = filetype.guess(header)

    if kind is None:
        # filetype couldn't determine the type — allow only plain text formats
        # (txt/csv files have no magic number signature)
        if declared_type in ("txt", "csv"):
            return
        raise ValidationError(
            f"Cannot determine file type. Only plain text files are accepted "
            f"without type detection. Declared type: '{declared_type}'."
        )

    allowed_mimes = ALLOWED_MIME_TYPES.get(declared_type, [])
    if not allowed_mimes:
        # Unknown declared type — reject
        raise ValidationError(
            f"Unknown file type: '{declared_type}'. "
            f"Allowed types: pdf, docx, doc, txt, csv, xlsx, pptx."
        )

    if kind.mime not in allowed_mimes:
        raise ValidationError(
            f"File content does not match declared type '{declared_type}'. "
            f"Detected content type: {kind.mime}. "
            f"This may be a file type spoofing attempt."
        )


def validate_file_size(file_obj) -> None:
    """Validate file size is within allowed min/max bounds.

    V4.1 KB-V4.1-008: Prevents empty/tiny files (DoS vectors) and
    oversized files (resource exhaustion).

    Args:
        file_obj: Django UploadedFile object.

    Raises:
        ValidationError: If file is too small or too large.
    """
    from django.conf import settings

    max_size_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", MAX_FILE_SIZE_MB)

    if file_obj.size < MIN_FILE_SIZE:
        raise ValidationError(
            f"File is too small ({file_obj.size} bytes). Minimum size is {MIN_FILE_SIZE} bytes (1KB)."
        )

    max_bytes = max_size_mb * 1024 * 1024
    if file_obj.size > max_bytes:
        raise ValidationError(
            f"File is too large ({file_obj.size} bytes). Maximum size is {max_size_mb}MB."
        )
