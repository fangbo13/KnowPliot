# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Canonical current-version document upload policy."""

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError


MIN_DOCUMENT_SIZE_BYTES = 1024
DEFAULT_MAX_DOCUMENT_SIZE_MB = 50

DOCUMENT_TYPE_BY_EXTENSION = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".html": "html",
    ".htm": "html",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
}

EXTENSIONS_BY_DOCUMENT_TYPE = {
    "pdf": (".pdf",),
    "docx": (".docx",),
    "html": (".html", ".htm"),
    "txt": (".txt",),
    "md": (".md", ".markdown"),
}

TEXT_DOCUMENT_TYPES = {"html", "txt", "md"}


def allowed_document_extensions() -> tuple[str, ...]:
    return tuple(DOCUMENT_TYPE_BY_EXTENSION)


def derive_document_type(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    document_type = DOCUMENT_TYPE_BY_EXTENSION.get(extension)
    if document_type is None:
        allowed = ", ".join(allowed_document_extensions())
        raise ValidationError(
            f"Unsupported file extension '{extension or '(none)'}'. "
            f"Allowed extensions: {allowed}."
        )
    return document_type


def validate_document_size(size: int) -> None:
    if size < MIN_DOCUMENT_SIZE_BYTES:
        raise ValidationError(
            f"File is too small ({size} bytes). "
            f"Minimum size is {MIN_DOCUMENT_SIZE_BYTES} bytes (1KB)."
        )

    max_size_mb = getattr(
        settings,
        "MAX_UPLOAD_SIZE_MB",
        DEFAULT_MAX_DOCUMENT_SIZE_MB,
    )
    if size > max_size_mb * 1024 * 1024:
        raise ValidationError(
            f"File is too large ({size} bytes). Maximum size is {max_size_mb}MB."
        )


def _validate_utf8_text(content: bytes) -> None:
    if b"\x00" in content:
        raise ValidationError(
            "File is not valid UTF-8 text: NUL bytes are not allowed."
        )
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("File is not valid UTF-8 text.") from exc


def _validate_pdf(content: bytes) -> None:
    if not content.startswith(b"%PDF-"):
        raise ValidationError("File content does not match filename type 'pdf'.")


def _validate_docx(content: bytes) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            if (
                "[Content_Types].xml" not in names
                or "word/document.xml" not in names
            ):
                raise ValidationError(
                    "File content does not match filename type 'docx'."
                )
            content_types = archive.read("[Content_Types].xml")
    except (BadZipFile, KeyError, OSError) as exc:
        raise ValidationError(
            "File content does not match filename type 'docx'."
        ) from exc

    if b"wordprocessingml.document" not in content_types:
        raise ValidationError(
            "File content does not match filename type 'docx'."
        )


def validate_document_content(content: bytes, document_type: str) -> None:
    if document_type in TEXT_DOCUMENT_TYPES:
        _validate_utf8_text(content)
        return
    if document_type == "pdf":
        _validate_pdf(content)
        return
    if document_type == "docx":
        _validate_docx(content)
        return
    raise ValidationError(f"Unsupported document type '{document_type}'.")


def validate_document_bytes(
    content: bytes,
    filename: str,
    declared_type: str | None = None,
) -> str:
    validate_document_size(len(content))
    derived_type = derive_document_type(filename)
    if declared_type and declared_type != derived_type:
        raise ValidationError(
            f"Declared file type '{declared_type}' does not match "
            f"filename type '{derived_type}'."
        )
    validate_document_content(content, derived_type)
    return derived_type


def validate_uploaded_document(
    file_obj,
    declared_type: str | None = None,
) -> str:
    validate_document_size(file_obj.size)
    original_position = file_obj.tell()
    try:
        file_obj.seek(0)
        content = file_obj.read()
    finally:
        file_obj.seek(original_position)
    return validate_document_bytes(content, file_obj.name, declared_type)
