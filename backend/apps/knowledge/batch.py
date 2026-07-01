# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""V4.2 Batch expansion module — EY knowledge base bulk import.

Handles ZIP upload, security validation, metadata tagging, deduplication,
and batch ingestion orchestration. Implements all 12 BATCH-* security fixes:

- BATCH-001: Zip Bomb detection (compression ratio + file count + total size + depth)
- BATCH-002: ZIP filename path traversal prevention
- BATCH-003: ZIP inner file Magic Number validation
- BATCH-004: Batch upload rate limiting (via views.py throttle)
- BATCH-005: Embedding batch task timeout + chunk limits
- BATCH-006: Extracted text size limits + chunk count limits
- BATCH-008: Filename sanitization (XSS/SQLi/path patterns)
- BATCH-009: PDF metadata sanitization (bleach)
- BATCH-010: Content hash deduplication for manual uploads
- BATCH-011: Batch import result tracking + reporting
- BATCH-012: Zero-vector detection + embedding failure handling
"""

import hashlib
import logging
import os
import re
import zipfile
from datetime import date
from io import BytesIO

import bleach
from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# ── Constants ──

# BATCH-001: Zip Bomb thresholds
ZIP_MAX_COMPRESSION_RATIO = 100  # compress_size/file_size ratio threshold (> 100:1 → reject)
ZIP_MAX_FILE_COUNT = 200  # max files inside a ZIP
ZIP_MAX_TOTAL_SIZE_MB = 500  # max total uncompressed size (MB)
ZIP_MAX_NESTING_DEPTH = 3  # max nested ZIP depth

# BATCH-004/011: Bulk upload limits
BULK_UPLOAD_MAX_DOCUMENTS = getattr(settings, "BULK_UPLOAD_MAX_DOCUMENTS", 100)
BULK_UPLOAD_TOTAL_SIZE_MB = getattr(settings, "BULK_UPLOAD_TOTAL_SIZE_MB", 500)

# BATCH-006: Content size limits
MAX_EXTRACTED_TEXT_SIZE = 10_000_000  # 10MB — truncate or reject
MAX_CHUNKS_PER_DOCUMENT = 500
MAX_CHUNKS_PER_BATCH = 5000

# BATCH-008: Filename sanitization patterns
DANGEROUS_FILENAME_PATTERNS = [
    # SQL injection
    r"[;']\s*(?:DROP|ALTER|CREATE|DELETE|INSERT|UPDATE|SELECT)\s",
    r"--\s*$",
    # XSS
    r"<script[^>]*>",
    r"</script>",
    r"on(?:click|error|load|mouseover|focus|blur)\s*=",
    r"javascript:",
    r"vbscript:",
    # Path traversal
    r"\.\./",
    r"\.\.\\",
    r"/etc/",
    r"/proc/",
    r"\Windows\\System32",
]

# BATCH-008: Allowed characters for sanitized filenames
SAFE_FILENAME_REGEX = re.compile(r"[^a-zA-Z0-9_\-\.\s\(\)（）[\]]")


# ── Zip Validation ──

def validate_zip_content(zip_file_obj) -> dict:
    """BATCH-001: Validate ZIP file for Zip Bomb, path traversal, type safety.

    Checks:
    1. Compression ratio (< 100:1 per file) — prevents Zip Bomb
    2. Total uncompressed size < 500MB — prevents disk exhaustion
    3. File count < 200 — prevents resource exhaustion
    4. No nested ZIPs beyond depth 3
    5. No path traversal in filenames (BATCH-002)
    6. Each file passes Magic Number validation (BATCH-003)
    7. Filename sanitization (BATCH-008)

    Args:
        zip_file_obj: Django UploadedFile or file-like object for the ZIP.

    Returns:
        Dict with 'valid_files' (list of safe entry dicts) and
        'rejected_files' (list of rejected entry dicts with reason).

    Raises:
        ValidationError: If ZIP itself is a Zip Bomb or contains >50% invalid files.
    """
    try:
        zf = zipfile.ZipFile(BytesIO(zip_file_obj.read()), mode="r")
    except zipfile.BadZipFile:
        raise ValidationError("Invalid ZIP file — cannot be opened.")
    finally:
        zip_file_obj.seek(0)

    entries = zf.infolist()
    valid_files = []
    rejected_files = []

    # BATCH-001: File count check
    if len(entries) > ZIP_MAX_FILE_COUNT:
        raise ValidationError(
            f"ZIP contains {len(entries)} files — exceeds maximum of {ZIP_MAX_FILE_COUNT}."
        )

    # BATCH-001: Total uncompressed size check
    total_uncompressed = sum(e.file_size for e in entries if not e.is_dir())
    total_mb = total_uncompressed / (1024 * 1024)
    if total_mb > ZIP_MAX_TOTAL_SIZE_MB:
        raise ValidationError(
            f"ZIP total uncompressed size is {total_mb:.1f}MB — "
            f"exceeds maximum of {ZIP_MAX_TOTAL_SIZE_MB}MB."
        )

    # BATCH-001: Compression ratio check per file
    for entry in entries:
        if entry.is_dir():
            continue

        # Compression ratio check (prevent Zip Bomb)
        if entry.compress_size > 0 and entry.file_size > 0:
            ratio = entry.file_size / entry.compress_size
            if ratio > ZIP_MAX_COMPRESSION_RATIO:
                raise ValidationError(
                    f"Zip Bomb detected: file '{entry.filename}' has compression "
                    f"ratio {ratio:.0f}:1 — exceeds maximum {ZIP_MAX_COMPRESSION_RATIO}:1."
                )

        # BATCH-002: Path traversal check
        filename = entry.filename
        if "../" in filename or "..\\" in filename or filename.startswith("/"):
            rejected_files.append({
                "filename": filename,
                "reason": "Path traversal pattern detected in filename.",
            })
            continue

        # BATCH-002: Symbolic link check
        # external_attr: bits 0-15 = MS-DOS attrs, bits 16-31 = Unix attrs
        # Unix symlink: (S_IFLNK << 16) = 0xA0000000
        unix_attrs = entry.external_attr >> 16
        if unix_attrs & 0o120000 == 0o120000:  # S_IFLNK = 0120000
            rejected_files.append({
                "filename": filename,
                "reason": "Symbolic link detected — not allowed.",
            })
            continue

        # BATCH-008: Filename sanitization
        sanitized_name = sanitize_filename(os.path.basename(filename))
        if not sanitized_name:
            rejected_files.append({
                "filename": filename,
                "reason": "Filename contains only dangerous characters.",
            })
            continue

        # Read content for type validation
        try:
            content = zf.read(entry)
        except Exception as e:
            rejected_files.append({
                "filename": filename,
                "reason": f"Cannot read file from ZIP: {str(e)[:100]}",
            })
            continue

        # BATCH-001: Individual file size check (per-file uncompressed must match)
        if len(content) != entry.file_size:
            # Actual size differs from declared — suspicious
            rejected_files.append({
                "filename": filename,
                "reason": f"Actual size ({len(content)}) differs from declared ({entry.file_size}).",
            })
            continue

        # Phase 3B: Unknown extensions are rejected explicitly. Previously an
        # unmapped extension skipped validation and was later persisted as TXT.
        declared_ext = get_extension_from_filename(sanitized_name)
        if declared_ext is None:
            rejected_files.append({
                "filename": filename,
                "reason": "Unsupported file extension.",
            })
            continue

        from apps.knowledge.file_policy import validate_document_bytes
        try:
            validate_document_bytes(content, sanitized_name, declared_ext)
        except ValidationError as exc:
            rejected_files.append({
                "filename": filename,
                "reason": exc.messages[0],
            })
            continue

        # File passes all checks
        valid_files.append({
            "original_filename": filename,
            "sanitized_filename": sanitized_name,
            "content": content,
            "file_size": len(content),
            "extension": declared_ext,
        })

    zf.close()

    # BATCH-003: If > 50% of files are rejected, reject the entire ZIP
    total_files = len(entries) - sum(1 for e in entries if e.is_dir())
    if total_files > 0 and len(rejected_files) > total_files * 0.5:
        raise ValidationError(
            f"ZIP rejected: {len(rejected_files)}/{total_files} files are invalid (>50%). "
            f"First 5 reasons: {[r['reason'] for r in rejected_files[:5]]}"
        )

    return {
        "valid_files": valid_files,
        "rejected_files": rejected_files,
        "total_files": total_files,
        "valid_count": len(valid_files),
        "rejected_count": len(rejected_files),
    }


# ── Filename Sanitization ──

def sanitize_filename(filename: str) -> str:
    """BATCH-008: Sanitize a filename to remove dangerous patterns.

    Removes:
    - SQL injection patterns (DROP TABLE, etc.)
    - XSS patterns (<script>, onclick, javascript:)
    - Path traversal patterns (../, ..\\)
    - Special characters that could cause issues

    Args:
        filename: Raw filename from ZIP or upload.

    Returns:
        Cleaned filename. Empty string if all characters are dangerous.
    """
    # Remove path components — only keep basename
    filename = os.path.basename(filename)

    # Remove dangerous patterns
    for pattern in DANGEROUS_FILENAME_PATTERNS:
        filename = re.sub(pattern, "", filename, flags=re.IGNORECASE)

    # Remove remaining unsafe characters
    filename = SAFE_FILENAME_REGEX.sub("", filename)

    # Collapse multiple spaces/dots
    filename = re.sub(r"\s+", " ", filename).strip()
    filename = re.sub(r"\.{3,}", ".", filename)

    # Ensure filename is not empty and has reasonable length
    if not filename:
        return ""
    if len(filename) > 200:
        # Truncate but preserve extension
        base, ext = os.path.splitext(filename)
        filename = base[:200 - len(ext)] + ext

    return filename


def sanitize_title(title: str) -> str:
    """BATCH-008: Sanitize a document title to prevent stored XSS.

    Uses bleach to strip dangerous HTML tags and attributes.
    Also removes SQL injection and path traversal patterns.
    """
    # Strip HTML tags completely — titles should be plain text
    title = bleach.clean(title, tags=[], attributes=[], strip=True)

    # Remove SQL injection patterns
    for pattern in DANGEROUS_FILENAME_PATTERNS:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)

    # Truncate to model field max length
    return title.strip()[:255] if title.strip() else "Untitled"


# ── Metadata Sanitization ──

def sanitize_metadata(metadata: dict) -> dict:
    """BATCH-009: Sanitize PDF/document metadata values to prevent XSS.

    Applies bleach.clean to every string value in the metadata dict.
    Only allows plain text — no HTML tags in metadata values.
    """
    cleaned = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            cleaned[key] = bleach.clean(value, tags=[], attributes=[], strip=True)
        elif isinstance(value, dict):
            cleaned[key] = sanitize_metadata(value)
        elif isinstance(value, list):
            cleaned[key] = [
                bleach.clean(v, tags=[], attributes=[], strip=True)
                if isinstance(v, str) else v
                for v in value
            ]
        else:
            cleaned[key] = value
    return cleaned


# ── Content Hash Deduplication ──

def compute_content_hash(content: bytes) -> str:
    """BATCH-010: Compute SHA256 hash of file content for deduplication."""
    return hashlib.sha256(content).hexdigest()


def check_document_duplicate(content_hash: str, exclude_doc_id=None) -> dict:
    """BATCH-010: Check if a document with the same content_hash already exists.

    Args:
        content_hash: SHA256 hash of the file content.
        exclude_doc_id: Optional UUID to exclude from check (for updates).

    Returns:
        Dict with 'is_duplicate' bool and 'existing_document' if found.
    """
    from apps.knowledge.models import Document

    qs = Document.objects.filter(content_hash=content_hash, status__in=["active", "processing"])
    if exclude_doc_id:
        qs = qs.exclude(id=exclude_doc_id)

    existing = qs.first()
    if existing:
        return {
            "is_duplicate": True,
            "existing_document": {
                "id": str(existing.id),
                "title": existing.title,
                "status": existing.status,
                "uploaded_by": str(existing.uploaded_by_id),
                "created_at": existing.created_at.isoformat(),
            },
        }
    return {"is_duplicate": False}


# ── Inner File Type Validation ──

def get_extension_from_filename(filename: str) -> str | None:
    """Extract extension from filename, mapped to allowed types."""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    # Map common extensions to our file_type choices
    ext_map = {
        "pdf": "pdf",
        "docx": "docx",
        "txt": "txt",
        "html": "html",
        "htm": "html",
        "md": "md",
        "markdown": "md",
    }
    return ext_map.get(ext)


def validate_inner_file_type(content: bytes, declared_type: str) -> tuple[bool, str | None]:
    """BATCH-003: Validate inner file content type using Magic Number detection.

    Args:
        content: Complete file content bytes.
        declared_type: Expected file type ('pdf', 'docx', etc.).

    Returns:
        Tuple of (is_valid, detected_mime).
    """
    from apps.knowledge.file_policy import (
        EXTENSIONS_BY_DOCUMENT_TYPE,
        validate_document_bytes,
    )

    extensions = EXTENSIONS_BY_DOCUMENT_TYPE.get(declared_type)
    if not extensions:
        return False, "unsupported"
    try:
        validate_document_bytes(
            content,
            f"document{extensions[0]}",
            declared_type,
        )
    except ValidationError as exc:
        return False, exc.messages[0]
    return True, declared_type


# ── Batch Metadata Tagging ──

def build_batch_metadata(source_tag: str = "EY_Batch") -> dict:
    """BATCH-011: Build standard metadata tags for batch-imported documents.

    Args:
        source_tag: Source label (default 'EY_Batch' for EY knowledge base).

    Returns:
        Dict with standard batch metadata fields.
    """
    return {
        "source": source_tag,
        "import_date": date.today().isoformat(),
        "import_method": "batch_upload",
    }


# ── Zero Vector Detection ──

def is_zero_vector(embedding: list[float]) -> bool:
    """BATCH-012: Check if an embedding vector is all zeros (failed embedding).

    Args:
        embedding: List of float values.

    Returns:
        True if all values are 0.0 (zero vector).
    """
    if not embedding:
        return True
    return all(v == 0.0 for v in embedding)


# ── Batch Import Result Model ──

class BatchImportResult:
    """BATCH-011: Tracks batch import progress and results.

    This is a lightweight in-memory result tracker. The actual
    BatchImportResultRecord model stores persistent results in DB.
    """

    def __init__(self, total_files: int = 0):
        self.total_files = total_files
        self.success_count = 0
        self.duplicate_skipped_count = 0
        self.failed_count = 0
        self.results: list[dict] = []  # Per-file results

    def add_success(self, doc_id: str, title: str):
        self.success_count += 1
        self.results.append({
            "status": "success",
            "document_id": doc_id,
            "title": title,
        })

    def add_duplicate(self, title: str, existing_id: str):
        self.duplicate_skipped_count += 1
        self.results.append({
            "status": "duplicate_skipped",
            "title": title,
            "existing_document_id": existing_id,
        })

    def add_failure(self, title: str, reason: str):
        self.failed_count += 1
        self.results.append({
            "status": "failed",
            "title": title,
            "reason": reason,
        })

    def to_dict(self) -> dict:
        return {
            "total_files": self.total_files,
            "success_count": self.success_count,
            "duplicate_skipped_count": self.duplicate_skipped_count,
            "failed_count": self.failed_count,
            "results": self.results,
        }
