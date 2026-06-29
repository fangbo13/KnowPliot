"""V4.2 Batch upload views — EY knowledge base bulk import API.

Provides:
- BatchDocumentUploadView: ZIP file upload → batch import orchestration
- BatchImportResultDetailView: View batch import result status
- DocumentUploadRateThrottle: Per-user upload rate limit (BATCH-004)
"""

import logging

from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.core.permissions import IsHROrAdmin  # noqa: F401 (kept for compatibility)
from apps.spaces.permissions import SpaceDocumentPermission, is_platform_admin
from apps.audit.views import create_audit_log
from apps.knowledge.batch import (
    compute_content_hash,
    check_document_duplicate,
    build_batch_metadata,
    BatchImportResult,
    BULK_UPLOAD_MAX_DOCUMENTS,
    sanitize_filename,
    sanitize_title,
    sanitize_metadata,
    MAX_EXTRACTED_TEXT_SIZE,
    MAX_CHUNKS_PER_DOCUMENT,
    MAX_CHUNKS_PER_BATCH,
    is_zero_vector,
)
from apps.knowledge.models import Document, DocumentCategory, BatchImportResultRecord
from apps.knowledge.batch_serializers import (
    BatchDocumentUploadSerializer,
    BatchImportResultSerializer,
)

logger = logging.getLogger(__name__)


# ── V4.2 BATCH-004: Upload Rate Throttle ──

class DocumentUploadRateThrottle(UserRateThrottle):
    """V4.2 KB-V4.2-BATCH-004: Per-user document upload rate limit.

    Limits single document uploads to 10/minute/user.
    Batch ZIP uploads have a separate, stricter limit (3/minute/user).
    """
    scope = "document_upload"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


class BatchUploadRateThrottle(UserRateThrottle):
    """V4.2 KB-V4.2-BATCH-004: Per-user batch ZIP upload rate limit.

    Stricter limit: 3 batch uploads per minute per user.
    """
    scope = "batch_upload"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }


# ── V4.2: Batch Document Upload View ──

class BatchDocumentUploadView(generics.CreateAPIView):
    """V4.2: Upload ZIP file for batch knowledge base import.

    Process:
    1. Validate ZIP (BATCH-001: Zip Bomb, BATCH-002: path traversal,
       BATCH-003: type validation, BATCH-008: filename sanitization)
    2. Compute content hashes for deduplication (BATCH-010)
    3. Create Document entries with EY_Batch metadata (BATCH-011)
    4. Trigger Celery batch ingestion tasks (BATCH-005)
    5. Return batch result with import statistics

    Rate limited to 3/minute/user (BATCH-004).
    Only accessible by HR/Admin roles.
    """

    serializer_class = BatchDocumentUploadSerializer
    # V6.0: batch upload requires the space's document.upload permission.
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]
    throttle_classes = [DocumentUploadRateThrottle, BatchUploadRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get validation result from serializer (stored by validate_zip_file)
        validation_result = getattr(serializer, "_validation_result", None)
        if not validation_result:
            # If not cached, re-validate (edge case)
            from apps.knowledge.batch import validate_zip_content
            zip_file = serializer.validated_data["zip_file"]
            validation_result = validate_zip_content(zip_file)
            zip_file.seek(0)

        valid_files = validation_result["valid_files"]
        source_tag = serializer.validated_data.get("source_tag", "EY_Batch")
        category_id = serializer.validated_data.get("category")

        # BATCH-004: Max document count per batch
        if len(valid_files) > BULK_UPLOAD_MAX_DOCUMENTS:
            return Response(
                {"error": f"ZIP contains {len(valid_files)} valid files — "
                         f"exceeds maximum of {BULK_UPLOAD_MAX_DOCUMENTS}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create BatchImportResultRecord (BATCH-011)
        batch_record = BatchImportResultRecord.objects.create(
            total_files=len(valid_files),
            source_tag=source_tag,
            status="processing",
            uploaded_by=request.user,
        )

        # Create audit log for batch import (BATCH-011)
        create_audit_log(
            user=request.user,
            action="document_batch_import",
            target_type="BatchImportResultRecord",
            target_id=str(batch_record.id),
            details={
                "total_files": len(valid_files),
                "rejected_files": validation_result["rejected_count"],
                "source_tag": source_tag,
            },
            request=request,
        )

        # Process each valid file
        batch_result = BatchImportResult(total_files=len(valid_files))
        category = None
        if category_id:
            try:
                category = DocumentCategory.objects.get(id=category_id)
            except DocumentCategory.DoesNotExist:
                pass

        batch_metadata = build_batch_metadata(source_tag)

        # V6.0: batch uploads land in the active space (header) or default 'general'.
        from apps.spaces.permissions import resolve_request_space
        from apps.spaces.models import KnowledgeSpace
        batch_space = resolve_request_space(request, required=False) or \
            KnowledgeSpace.objects.filter(code="general").first()

        total_chunks_in_batch = 0  # BATCH-005: Track total chunks

        for file_info in valid_files:
            filename = file_info["sanitized_filename"]
            content = file_info["content"]
            file_ext = file_info["extension"]

            # BATCH-010: Content hash deduplication
            content_hash = compute_content_hash(content)
            dup_check = check_document_duplicate(content_hash)
            if dup_check["is_duplicate"]:
                batch_result.add_duplicate(filename, dup_check["existing_document"]["id"])
                logger.info(
                    f"[BatchImport] Duplicate skipped: '{filename}' — "
                    f"matches existing doc {dup_check['existing_document']['id']}"
                )
                continue

            # Create Document entry
            try:
                doc = Document(
                    title=sanitize_title(filename),
                    file_type=file_ext or "txt",
                    file_size=len(content),
                    category=category,
                    tags=[source_tag],
                    status="processing",
                    uploaded_by=request.user,
                    content_hash=content_hash,
                    space=batch_space,  # V6.0 space isolation
                )

                # Save file content to Document.file field
                from django.core.files.base import ContentFile
                doc.file.save(filename, ContentFile(content), save=False)
                doc.save()

                # Trigger async ingestion via Celery
                from apps.rag.services import ingest_document
                ingest_document.delay(str(doc.id))

                batch_result.add_success(str(doc.id), doc.title)
                logger.info(f"[BatchImport] Document created: '{filename}' → {doc.id}")

            except Exception as e:
                batch_result.add_failure(filename, str(e)[:200])
                logger.error(f"[BatchImport] Failed to create document '{filename}': {e}")

        # Update batch record with results
        batch_record.success_count = batch_result.success_count
        batch_record.duplicate_skipped_count = batch_result.duplicate_skipped_count
        batch_record.failed_count = batch_result.failed_count
        batch_record.result_details = batch_result.results
        batch_record.status = "completed"
        batch_record.save()

        return Response(
            {
                "batch_id": str(batch_record.id),
                "total_files": batch_result.total_files,
                "success_count": batch_result.success_count,
                "duplicate_skipped_count": batch_result.duplicate_skipped_count,
                "failed_count": batch_result.failed_count,
                "results": batch_result.results,
            },
            status=status.HTTP_201_CREATED,
        )


class BatchImportResultDetailView(generics.RetrieveAPIView):
    """V4.2: View batch import result status and details."""

    serializer_class = BatchImportResultSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # V6.0: users see their own batch results; platform admins see all.
        qs = BatchImportResultRecord.objects.all()
        if is_platform_admin(self.request.user):
            return qs
        return qs.filter(uploaded_by=self.request.user)
