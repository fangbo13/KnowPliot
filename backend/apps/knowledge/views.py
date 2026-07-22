# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge views — V4.1 SYS-V4.1-006: Document reindex concurrency protection.

Added select_for_update() + transaction.atomic() to prevent parallel
ingest_document tasks from running simultaneously on the same document.

V4.2 KB-V4.2-BATCH-004: Added DocumentUploadRateThrottle to all upload views.
"""

import difflib
import mimetypes
import os

from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsHROrAdmin
from apps.audit.views import create_audit_log
from apps.spaces.permissions import (  # V6.0 space isolation
    DOCUMENT_DELETE,
    DOCUMENT_DOWNLOAD,
    DOCUMENT_UPDATE,
    SpaceDocumentPermission,
    effective_space_role,
    ensure_workspace_writable,
    has_space_permission,
    is_platform_admin,
    resolve_request_space,
)
from apps.spaces.governed import (  # Part 1 (§1.13): idempotency + audit
    complete_operation_record,
    digest_payload,
    durable_governed_transaction,
    operation_record,
    replay_response,
    require_idempotency_key,
)
from .models import DocumentCategory, Document, DocumentChunk, AnswerTemplate
from .serializers import (
    DocumentCategorySerializer,
    DocumentSerializer,
    DocumentDetailSerializer,
    DocumentChunkSerializer,
    AnswerTemplateSerializer,
)
# V4.2 KB-V4.2-BATCH-004: Upload rate throttle
from .batch_views import DocumentUploadRateThrottle


def _active_doc_space(request):
    """Resolve the active space for document operations.

    New content always requires an explicit, authorized workspace selection;
    legacy default-space fallback is not an authority boundary.
    """
    return resolve_request_space(request, required=True)


class DocumentListCreateView(generics.ListCreateAPIView):
    """List and upload documents (admin only).

    V4.2 KB-V4.2-BATCH-004: Added upload rate throttle (10/minute/user).
    """

    # V6.0: space-aware document permission (replaces global IsHROrAdmin gate).
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]
    throttle_classes = [DocumentUploadRateThrottle]  # V4.2 BATCH-004

    def get_queryset(self):
        # V6.0: scope the document list to the active space when a header is sent.
        qs = Document.objects.all()
        space = resolve_request_space(self.request, required=False)
        if space is not None:
            qs = qs.filter(space=space)
        category = self.request.query_params.get("category")
        status_filter = self.request.query_params.get("status")
        if category:
            qs = qs.filter(category__slug=category)
        if status_filter:
            qs = qs.filter(status=status_filter)
        else:
            qs = qs.exclude(status="archived")
        return qs

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DocumentSerializer
        return DocumentDetailSerializer

    def perform_create(self, serializer):
        # V6.0: uploads land in the active space (header) or default 'general'.
        space = _active_doc_space(self.request)
        ensure_workspace_writable(space)
        doc = serializer.save(uploaded_by=self.request.user, space=space)
        create_audit_log(
            user=self.request.user,
            action="document_upload",
            target_type="Document",
            target_id=str(doc.id),
            details={"title": doc.title, "file_type": doc.file_type,
                     "space": str(space.id) if space else None},
            request=self.request,
        )
        # Trigger async ingestion
        from apps.knowledge.ingestion import enqueue_document_ingestion
        enqueue_document_ingestion(
            doc,
            requested_by=self.request.user,
            trigger="upload",
        )


class DocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, delete a document."""

    serializer_class = DocumentDetailSerializer
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]

    def get_queryset(self):
        # V6.0: when a space is active, only that space's documents are reachable.
        qs = Document.objects.all()
        space = resolve_request_space(self.request, required=False)
        if space is not None:
            qs = qs.filter(space=space)
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.space_id is not None:
            ensure_workspace_writable(instance.space)
        hard_delete = request.query_params.get("hard", "").lower() == "true"
        if hard_delete:
            from apps.chat.models import Citation

            if Citation.objects.filter(document=instance).exists():
                return Response(
                    {"detail": "Cited documents cannot be hard-deleted."},
                    status=status.HTTP_409_CONFLICT,
                )
            create_audit_log(
                user=request.user,
                action="document_delete",
                target_type="Document",
                target_id=str(instance.id),
                details={"title": instance.title, "hard_delete": True},
                request=request,
            )
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Content authority is workspace-scoped. Platform metadata capability
        # never turns into document mutation authority.
        allowed = instance.uploaded_by == request.user
        if not allowed and instance.space_id is not None:
            allowed = has_space_permission(request.user, instance.space, DOCUMENT_DELETE)
        if not allowed:
            return Response(
                {"detail": "You do not have permission to delete this document."},
                status=status.HTTP_403_FORBIDDEN,
            )
        create_audit_log(
            user=request.user,
            action="document_status_change",
            target_type="Document",
            target_id=str(instance.id),
            details={
                "title": instance.title,
                "from": instance.status,
                "to": "archived",
            },
            request=request,
        )
        instance.status = "archived"
        instance.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentDownloadView(APIView):
    """Stream a document after object-level space authorization.

    Raw storage URLs only establish possession of a path. This endpoint binds
    delivery to the Document object so ``document.download`` and audit policy
    are enforced for every request.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _audit_denial(self, request, document, reason):
        create_audit_log(
            user=request.user,
            action="permission_denied",
            target_type="Document",
            target_id=str(document.id),
            details={
                "permission": DOCUMENT_DOWNLOAD,
                "result": "denied",
                "reason": reason,
                "space_id": str(document.space_id) if document.space_id else None,
            },
            request=request,
        )

    def get(self, request, pk):
        try:
            document = Document.objects.select_related("space").get(pk=pk)
        except Document.DoesNotExist as exc:
            raise NotFound("Document not found.") from exc

        active_space_id = request.headers.get("X-Space-Id")
        if (
            active_space_id
            and document.space_id
            and active_space_id != str(document.space_id)
        ):
            self._audit_denial(request, document, "active_space_mismatch")
            raise NotFound("Document not found.")

        if document.space_id is None:
            if not is_platform_admin(request.user):
                self._audit_denial(request, document, "unscoped_document")
                raise NotFound("Document not found.")
        else:
            role = effective_space_role(request.user, document.space)
            if role is None:
                self._audit_denial(request, document, "space_not_accessible")
                raise NotFound("Document not found.")
            if not has_space_permission(
                request.user,
                document.space,
                DOCUMENT_DOWNLOAD,
            ):
                self._audit_denial(request, document, "permission_missing")
                raise PermissionDenied(
                    "You do not have permission to download this document."
                )

        try:
            file_handle = document.file.open("rb")
        except (FileNotFoundError, OSError) as exc:
            raise NotFound("Document file not found.") from exc

        filename = os.path.basename(document.file.name)
        content_type, _ = mimetypes.guess_type(filename)
        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=filename,
            content_type=content_type or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"

        create_audit_log(
            user=request.user,
            action="document_download",
            target_type="Document",
            target_id=str(document.id),
            details={
                "result": "success",
                "space_id": str(document.space_id) if document.space_id else None,
                "filename": filename,
            },
            request=request,
        )
        return response


class DocumentReindexView(generics.GenericAPIView):
    """Trigger re-indexing of a document."""

    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]

    def get_queryset(self):
        return Document.objects.all()

    # V4.1 SYS-V4.1-006: select_for_update() + transaction prevents concurrent reindex
    def post(self, request, pk):
        # V6.0: scope the reindex target to the active space (can't reindex a
        # document outside the space you're operating in).
        active_space = resolve_request_space(request, required=False)
        # Acquire row-level lock and check status atomically
        try:
            with transaction.atomic():
                qs = Document.objects.select_for_update()
                if active_space is not None:
                    qs = qs.filter(space=active_space)
                document = qs.get(id=pk)
                if document.status == "processing":
                    return Response(
                        {"error": "Document is already being processed"},
                        status=status.HTTP_409_CONFLICT,
                    )
                if document.status == "archived":
                    return Response(
                        {"error": "Archived documents cannot be re-indexed"},
                        status=status.HTTP_409_CONFLICT,
                    )
                document.status = "processing"
                document.save(update_fields=["status"])
        except Document.DoesNotExist:
            return Response({"error": "Document not found"}, status=404)

        create_audit_log(
            user=request.user,
            action="document_reindex",
            target_type="Document",
            target_id=str(document.id),
            details={"title": document.title},
            request=request,
        )

        # Trigger Celery task OUTSIDE the transaction (avoid long DB lock)
        from apps.knowledge.ingestion import enqueue_document_ingestion
        enqueue_document_ingestion(
            document,
            requested_by=request.user,
            trigger="reindex",
        )

        return Response({"status": "reindexing started"})


class DocumentChunksView(generics.ListAPIView):
    """View chunks of a document."""

    serializer_class = DocumentChunkSerializer
    permission_classes = [permissions.IsAuthenticated, SpaceDocumentPermission]

    def get_queryset(self):
        qs = DocumentChunk.objects.filter(document_id=self.kwargs["document_id"])
        space = resolve_request_space(self.request, required=False)
        if space is not None:
            qs = qs.filter(space=space)  # V6.0 space isolation
        return qs.order_by("chunk_index")


class CategoryListView(generics.ListCreateAPIView):
    """List and create document categories.

    V4.0 RBAC fix: POST (create) requires category.create permission
    (HR/Admin only). GET (list) is available to all authenticated users.
    """

    serializer_class = DocumentCategorySerializer

    def get_permissions(self):
        """V4.0: Separate GET/POST permission requirements.

        GET: Any authenticated user can list categories (needed for chat dropdown).
        POST: Only HR/Admin can create categories (category.create codename).
        """
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsHROrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return DocumentCategory.objects.all()

    def perform_create(self, serializer):
        instance = serializer.save()
        create_audit_log(
            user=self.request.user,
            action="category_create",
            target_type="DocumentCategory",
            target_id=str(instance.id),
            details={"name": instance.name},
            request=self.request,
        )


class AnswerTemplateListView(generics.ListCreateAPIView):
    """List and create answer templates."""

    serializer_class = AnswerTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return AnswerTemplate.objects.filter(is_active=True)

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        create_audit_log(
            user=self.request.user,
            action="template_create",
            target_type="AnswerTemplate",
            target_id=str(instance.id),
            details={"question_pattern": instance.question_pattern},
            request=self.request,
        )


class AnswerTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, delete an answer template."""

    serializer_class = AnswerTemplateSerializer
    permission_classes = [permissions.IsAuthenticated, IsHROrAdmin]

    def get_queryset(self):
        return AnswerTemplate.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        create_audit_log(
            user=request.user,
            action="template_delete",
            target_type="AnswerTemplate",
            target_id=str(instance.id),
            details={"question_pattern": instance.question_pattern},
            request=request,
        )
        return super().destroy(request, *args, **kwargs)


# ── Part 1 (KB version化): new API endpoints (SPEC §1.10) ──────────

def _resolve_doc_for_edit(request, pk):
    """Resolve a document for editing, enforcing space isolation + DOCUMENT_UPDATE.

    Returns the Document instance.  Raises NotFound / PermissionDenied.
    """
    try:
        document = Document.objects.select_related("space").get(pk=pk)
    except Document.DoesNotExist:
        raise NotFound("Document not found.")

    active_space = resolve_request_space(request, required=False)
    if active_space is not None and document.space_id != active_space.id:
        raise NotFound("Document not found.")

    if document.space_id is None:
        if not is_platform_admin(request.user):
            raise PermissionDenied("You do not have permission to edit this document.")
    else:
        if not has_space_permission(request.user, document.space, DOCUMENT_UPDATE):
            raise PermissionDenied("You do not have permission to edit this document.")
    return document


class DocumentTextEditView(APIView):
    """Part 1 (§1.10): Edit text_content — stage for preview, no version switch.

    Updates the document's ``text_content`` field without triggering version
    creation or re-chunking.  The change is "staged": the caller can then
    call preview-diff and confirm to create a new version.
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        document = _resolve_doc_for_edit(request, pk)
        new_text = request.data.get("text_content")
        if new_text is None:
            return Response(
                {"detail": "text_content field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        document.text_content = new_text
        document.save(update_fields=["text_content", "updated_at"])
        create_audit_log(
            user=request.user,
            action="document_text_edit",
            target_type="Document",
            target_id=str(document.id),
            details={"title": document.title, "staged": True},
            request=request,
        )
        return Response(
            {
                "id": str(document.id),
                "text_content": document.text_content,
                "staged": True,
            },
            status=status.HTTP_200_OK,
        )

    post = patch  # Allow POST as alias


class DocumentPreviewDiffView(APIView):
    """Part 1 (§1.4/§1.10): Preview line-level diff — no persistence, no embed.

    Accepts a proposed ``text_content`` in the request body and returns a
    structured line-level diff against the document's current ``text_content``.
    Does NOT write to the database or trigger embedding.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        document = _resolve_doc_for_edit(request, pk)
        new_text = request.data.get("text_content", "")
        old_text = document.text_content or ""

        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

        diff_blocks = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            diff_blocks.append({
                "tag": tag,
                "old_start": i1,
                "old_end": i2,
                "new_start": j1,
                "new_end": j2,
                "old_lines": old_lines[i1:i2],
                "new_lines": new_lines[j1:j2],
            })

        return Response({
            "document_id": str(document.id),
            "old_version": document.version,
            "diff": diff_blocks,
            "stats": {
                "old_lines": len(old_lines),
                "new_lines": len(new_lines),
                "changed_blocks": sum(1 for b in diff_blocks if b["tag"] != "equal"),
            },
        })


def _parse_effective_from(value):
    """Parse an ISO-8601 effective_from string; default to now."""
    if not value:
        return timezone.now()
    from datetime import datetime
    dt = datetime.fromisoformat(str(value))
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _create_version_atomically(
    *,
    current_doc,
    new_text,
    effective_from,
    reason,
    actor,
    request,
):
    """Shared version-creation logic (used by version-create + rollback).

    Must be called inside ``durable_governed_transaction`` +
    ``operation_record``.  ``current_doc`` must already be locked via
    ``select_for_update(of=("self",))``.
    """
    new_doc = Document.objects.create(
        title=current_doc.title,
        file=current_doc.file,
        text_content=new_text,
        file_type=current_doc.file_type,
        file_size=current_doc.file_size,
        category=current_doc.category,
        tags=current_doc.tags,
        space=current_doc.space,
        uploaded_by=actor,
        status="active",
        version=current_doc.version + 1,
        parent_document=current_doc,
        effective_from=effective_from,
        content_hash="",
    )

    is_immediate = effective_from <= timezone.now()

    if is_immediate:
        # Old version superseded + chunks removed from live index
        current_doc.effective_to = effective_from
        current_doc.status = "superseded"
        current_doc.save(update_fields=["effective_to", "status", "updated_at"])
        DocumentChunk.objects.filter(document=current_doc).delete()
    else:
        # Scheduled: old version stays active, but effective_to caps at new version
        current_doc.effective_to = effective_from
        current_doc.save(update_fields=["effective_to", "updated_at"])

    # Re-chunk + re-embed new version's text_content
    from apps.rag.pipeline import RAGPipeline
    pipeline = RAGPipeline(ingestion=True)
    chunks = pipeline.ingest_text_content(new_doc)

    if chunks:
        new_doc.chunk_count = len(chunks)
        new_doc.status = "active"
        new_doc.save(update_fields=["chunk_count", "status"])

    create_audit_log(
        user=actor,
        action="document_version_created",
        target_type="Document",
        target_id=str(new_doc.id),
        details={
            "title": new_doc.title,
            "old_version_id": str(current_doc.id),
            "old_version_number": current_doc.version,
            "new_version_number": new_doc.version,
            "effective_from": effective_from.isoformat(),
            "immediate": is_immediate,
            "reason": reason,
            "space_id": str(current_doc.space_id) if current_doc.space_id else None,
        },
        request=request,
    )

    return new_doc, {
        "id": str(new_doc.id),
        "version": new_doc.version,
        "parent_document": str(current_doc.id),
        "effective_from": effective_from.isoformat(),
        "immediate": is_immediate,
        "chunk_count": len(chunks) if chunks else 0,
        "old_version_status": "superseded" if is_immediate else "active",
    }


class DocumentVersionCreateView(APIView):
    """Part 1 (§1.3/§1.10): Create a new version — atomic re-chunk + re-embed.

    In a single idempotent transaction:
    - Lock current document with ``select_for_update(of=("self",))``
    - Create new Document(parent=current, version+1, effective_from, text_content=new)
    - If immediate (effective_from ≤ now): old version superseded + chunks deleted
    - If scheduled (effective_from > now): old version stays active, effective_to capped
    - Re-chunk + re-embed new text_content (pipeline.ingest_text_content)
    - Audit event (document_version_created)
    - Idempotency-Key + operation_record (§1.13)
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """KB-12-Features §3: List the version chain for a document.

        Walks up the ``parent_document`` chain to find all ancestors, then
        recursively finds all descendants from the root to capture rollback
        branches. Returns versions sorted by version number descending
        (newest first).
        """
        document = _resolve_doc_for_edit(request, pk)

        # Collect all versions connected via the parent_document chain.
        versions_by_id: dict = {}

        # Walk up the parent chain to collect ancestors (including the doc itself).
        current = document
        while current is not None:
            versions_by_id[current.id] = current
            current = current.parent_document

        # Find the root (oldest version) — follow already-loaded parent chain.
        root = document
        while root.parent_document_id is not None:
            root = root.parent_document

        # Recursively find ALL descendants from root to capture rollback branches.
        processed: set = set()
        to_process = [root]
        while to_process:
            doc = to_process.pop()
            if doc.id in processed:
                continue
            processed.add(doc.id)
            if doc.id not in versions_by_id:
                versions_by_id[doc.id] = doc
            children = Document.objects.filter(parent_document=doc)
            for child in children:
                to_process.append(child)

        # Sort by version number descending (newest first).
        all_versions = sorted(
            versions_by_id.values(), key=lambda d: d.version, reverse=True
        )

        versions_data = [
            {
                "id": str(v.id),
                "version": v.version,
                "status": v.status,
                "title": v.title,
                "effective_from": v.effective_from.isoformat()
                if v.effective_from
                else None,
                "effective_to": v.effective_to.isoformat()
                if v.effective_to
                else None,
                "created_at": v.created_at.isoformat(),
                "updated_at": v.updated_at.isoformat(),
                "parent_document": str(v.parent_document_id)
                if v.parent_document_id
                else None,
                "chunk_count": v.chunk_count,
            }
            for v in all_versions
        ]

        return Response(
            {
                "document_id": str(document.id),
                "versions": versions_data,
                "count": len(versions_data),
            }
        )

    def post(self, request, pk):
        # Pre-check: resolve document + permissions BEFORE idempotency
        document = _resolve_doc_for_edit(request, pk)

        new_text = request.data.get("text_content")
        if new_text is None:
            return Response(
                {"detail": "text_content field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        effective_from_raw = request.data.get("effective_from")
        effective_from = _parse_effective_from(effective_from_raw)
        reason = request.data.get("reason", "")

        # Idempotency (§1.13)
        idem_key = require_idempotency_key(request)
        request_digest = digest_payload({
            "document_id": pk,
            "text_content": new_text,
            "effective_from": effective_from_raw or "",  # stable: raw input, not now()
            "reason": reason,
        })

        with durable_governed_transaction():
            with operation_record(
                actor=request.user,
                operation_code="document_version_create",
                key=idem_key,
                request_digest=request_digest,
                target_uuid=pk,
            ) as (record, replay):
                if replay:
                    return replay_response(record)

                # Lock current document (prevents concurrent version racing)
                current_doc = (
                    Document.objects
                    .select_for_update(of=("self",))
                    .get(id=pk)
                )

                _, response_body = _create_version_atomically(
                    current_doc=current_doc,
                    new_text=new_text,
                    effective_from=effective_from,
                    reason=reason,
                    actor=request.user,
                    request=request,
                )

                complete_operation_record(
                    record,
                    status_code=201,
                    body=response_body,
                    result_reference=response_body["id"],
                )
                return Response(response_body, status=status.HTTP_201_CREATED)


class DocumentRollbackView(APIView):
    """Part 1 (§1.6/§1.10): Rollback — promote an old version as new current.

    Takes an old version's ``text_content`` and creates a new version (v+N+1)
    that re-chunks + re-embeds that text, following the same atomic flow as
    version creation.  ``target_version_id`` must be in the current document's
    parent_document chain.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # Pre-check: resolve current document + permissions
        current_doc = _resolve_doc_for_edit(request, pk)

        target_version_id = request.data.get("target_version_id")
        if not target_version_id:
            return Response(
                {"detail": "target_version_id field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Walk parent_document chain to find target version
        ancestor = current_doc
        found = None
        while ancestor is not None:
            if str(ancestor.id) == str(target_version_id):
                found = ancestor
                break
            ancestor = ancestor.parent_document

        if found is None:
            return Response(
                {"detail": "target_version_id is not in this document's version chain."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_text = found.text_content or ""
        reason = request.data.get("reason", f"rollback to version {found.version}")
        effective_from = timezone.now()  # Rollback is always immediate

        # Idempotency (§1.13)
        idem_key = require_idempotency_key(request)
        request_digest = digest_payload({
            "document_id": pk,
            "target_version_id": str(target_version_id),
            "reason": reason,
        })

        with durable_governed_transaction():
            with operation_record(
                actor=request.user,
                operation_code="document_rollback",
                key=idem_key,
                request_digest=request_digest,
                target_uuid=pk,
            ) as (record, replay):
                if replay:
                    return replay_response(record)

                # Lock current document
                locked_doc = (
                    Document.objects
                    .select_for_update(of=("self",))
                    .get(id=pk)
                )

                _, response_body = _create_version_atomically(
                    current_doc=locked_doc,
                    new_text=old_text,
                    effective_from=effective_from,
                    reason=reason,
                    actor=request.user,
                    request=request,
                )
                response_body["rollback_from_version"] = locked_doc.version

                complete_operation_record(
                    record,
                    status_code=201,
                    body=response_body,
                    result_reference=response_body["id"],
                )
                return Response(response_body, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# KB-12-Features §8: Markdown document templates
# ---------------------------------------------------------------------------

DOCUMENT_TEMPLATES: list[dict] = [
    {
        "slug": "policy",
        "name": "Policy Document",
        "description": "For company policies, regulations, and rules.",
        "content": (
            "# Policy Title\n\n"
            "## 1. Purpose\n\n"
            "Briefly describe the purpose of this policy.\n\n"
            "## 2. Scope\n\n"
            "Who and what this policy applies to.\n\n"
            "## 3. Policy\n\n"
            "### 3.1 General Provisions\n\n"
            "### 3.2 Specific Requirements\n\n"
            "### 3.3 Exceptions\n\n"
            "## 4. Roles and Responsibilities\n\n"
            "| Role | Responsibility |\n"
            "|------|---------------|\n"
            "|      |               |\n\n"
            "## 5. Enforcement\n\n"
            "Describe enforcement and consequences of non-compliance.\n\n"
            "## 6. Effective Date and Review\n\n"
            "- **Effective Date:**\n"
            "- **Next Review Date:**\n"
            "- **Approved By:**\n\n"
            "---\n"
            "*Version: v1.0*\n"
        ),
    },
    {
        "slug": "faq",
        "name": "FAQ Document",
        "description": "For frequently asked questions and answers.",
        "content": (
            "# FAQ: Topic Name\n\n"
            "## General Questions\n\n"
            "### Q1: Question text?\n\n"
            "**A:** Answer text.\n\n"
            "### Q2: Question text?\n\n"
            "**A:** Answer text.\n\n"
            "## Technical Questions\n\n"
            "### Q3: Question text?\n\n"
            "**A:** Answer text.\n\n"
            "### Q4: Question text?\n\n"
            "**A:** Answer text.\n\n"
            "---\n\n"
            "> If your question is not listed here, "
            "please contact support.\n"
        ),
    },
    {
        "slug": "technical-doc",
        "name": "Technical Document",
        "description": "For technical specifications and design documents.",
        "content": (
            "# Technical Document Title\n\n"
            "## Overview\n\n"
            "Brief description of the system or feature.\n\n"
            "## Architecture\n\n"
            "### Components\n\n"
            "1. **Component A** - description\n"
            "2. **Component B** - description\n\n"
            "### Data Flow\n\n"
            "```\n"
            "Input -> Processing -> Output\n"
            "```\n\n"
            "## API Specification\n\n"
            "### Endpoint: GET /api/v1/resource/\n\n"
            "| Parameter | Type | Required | Description |\n"
            "|-----------|------|----------|-------------|\n"
            "|           |      |          |             |\n\n"
            "## Configuration\n\n"
            "| Key | Default | Description |\n"
            "|-----|---------|-------------|\n"
            "|     |         |             |\n\n"
            "## Testing\n\n"
            "### Unit Tests\n\n"
            "### Integration Tests\n\n"
            "## Changelog\n\n"
            "| Version | Date | Changes |\n"
            "|---------|------|---------|\n"
            "| v1.0    |      | Initial |\n"
        ),
    },
    {
        "slug": "meeting-minutes",
        "name": "Meeting Minutes",
        "description": "For meeting records and action items.",
        "content": (
            "# Meeting Minutes: Meeting Title\n\n"
            "- **Date:**\n"
            "- **Time:**\n"
            "- **Location / Link:**\n"
            "- **Attendees:**\n"
            "- **Recorder:**\n\n"
            "## Agenda\n\n"
            "1. Item 1\n"
            "2. Item 2\n"
            "3. Item 3\n\n"
            "## Discussion\n\n"
            "### Item 1\n\n"
            "### Item 2\n\n"
            "## Action Items\n\n"
            "| # | Action | Owner | Due Date | Status |\n"
            "|---|--------|-------|----------|--------|\n"
            "| 1 |        |       |          | Open   |\n"
            "| 2 |        |       |          | Open   |\n\n"
            "## Next Meeting\n\n"
            "- **Date:**\n"
            "- **Agenda:**\n"
        ),
    },
    {
        "slug": "blank",
        "name": "Blank Document",
        "description": "Start from scratch with an empty Markdown document.",
        "content": "# Untitled Document\n\n",
    },
]


class DocumentTemplateView(APIView):
    """KB-12-Features Section 8: Return predefined Markdown document templates.

    GET /documents/document-templates/         - list all templates
    GET /documents/document-templates/<slug>/  - get a single template by slug
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug=None):
        if slug is not None:
            for template in DOCUMENT_TEMPLATES:
                if template["slug"] == slug:
                    return Response(template)
            raise NotFound("Document template not found.")

        return Response(
            {
                "templates": [
                    {
                        "slug": t["slug"],
                        "name": t["name"],
                        "description": t["description"],
                    }
                    for t in DOCUMENT_TEMPLATES
                ],
                "count": len(DOCUMENT_TEMPLATES),
            }
        )
