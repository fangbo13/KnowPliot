# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §3 — review gate API.

State machine: draft → pending_review → active (approve) / rejected.
Approval is the ONLY transition that indexes content (chunk+embed) — a
pending_review / rejected version never has retrievable chunks, which is the
L1 admission layer of the anti-hallucination index.

Separation of duties: the submitter can never approve their own version
(DB CheckConstraint + view-level check).
"""

from __future__ import annotations

import difflib
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.audit.views import create_audit_log
from apps.notifications.services import notify, notify_many
from apps.spaces.permissions import (
    effective_space_role,
    is_platform_admin,
    resolve_request_space,
)

from .models import Document, DocumentChunk, DocumentTag, ReviewRequest, TermOwnership

logger = logging.getLogger(__name__)

REVIEWER_ROLES = {"owner", "knowledge_admin", "reviewer"}
CONFLICT_SIMILARITY_THRESHOLD = 0.85
CONFLICT_TOP_N = 5


# ── Helpers ──────────────────────────────────────────────────────────


def space_requires_review(space) -> bool:
    return getattr(space, "review_policy", "direct_publish") == "require_review"


def _reviewer_users(space, *, exclude_user=None):
    from apps.spaces.models import SpaceMembership

    qs = SpaceMembership.objects.filter(
        space=space, status="active", role__in=REVIEWER_ROLES
    ).select_related("user")
    if exclude_user is not None:
        qs = qs.exclude(user=exclude_user)
    return [m.user for m in qs]


def _term_owner_users(document, *, exclude_user=None):
    term_ids = list(
        DocumentTag.objects.filter(document=document).values_list("term_id", flat=True)
    )
    if not term_ids:
        return []
    qs = TermOwnership.objects.filter(
        space_id=document.space_id, term_id__in=term_ids
    ).select_related("owner")
    if exclude_user is not None:
        qs = qs.exclude(owner=exclude_user)
    return list({o.owner.id: o.owner for o in qs}.values())


def build_diff_summary(old_text: str, new_text: str) -> dict:
    """Compact line-level diff stats snapshot stored on the ReviewRequest."""
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    added = removed = changed_blocks = 0
    samples = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_blocks += 1
        added += j2 - j1
        removed += i2 - i1
        if len(samples) < 5:
            samples.append(
                {
                    "tag": tag,
                    "old_lines": old_lines[i1:i2][:3],
                    "new_lines": new_lines[j1:j2][:3],
                }
            )
    return {
        "old_line_count": len(old_lines),
        "new_line_count": len(new_lines),
        "added_lines": added,
        "removed_lines": removed,
        "changed_blocks": changed_blocks,
        "samples": samples,
    }


def detect_conflicts(space, text: str, *, exclude_document_ids=()) -> list[dict]:
    """L1 conflict scan: active documents whose chunks are near-duplicates.

    Embeds a lead sample of the pending text and searches the space's live
    index; documents scoring above CONFLICT_SIMILARITY_THRESHOLD surface as
    "可能冲突/应替代" hints on the review card. Best-effort — an embedding
    outage never blocks submission.
    """
    sample = (text or "").strip()[:1500]
    if not sample or space is None:
        return []
    try:
        from apps.rag.retriever import PgVectorRetriever

        rows = PgVectorRetriever().search(
            sample,
            space_id=str(space.id),
            top_k=20,
            similarity_threshold=CONFLICT_SIMILARITY_THRESHOLD,
        )
    except Exception as exc:  # pragma: no cover — soft dependency on embeddings
        logger.warning("conflict detection failed for space %s: %s", space.id, exc)
        return []

    excluded = {str(x) for x in exclude_document_ids}
    best: dict[str, dict] = {}
    for row in rows:
        doc_id = str(row.get("document_id"))
        if doc_id in excluded:
            continue
        score = float(row.get("score", 0.0))
        if score < CONFLICT_SIMILARITY_THRESHOLD:
            continue
        entry = best.get(doc_id)
        if entry is None or score > entry["score"]:
            best[doc_id] = {
                "document_id": doc_id,
                "title": row.get("document_title", ""),
                "score": round(score, 4),
            }
    ranked = sorted(best.values(), key=lambda x: -x["score"])
    return ranked[:CONFLICT_TOP_N]


def _version_chain_ids(document) -> list[str]:
    ids = []
    current = document
    seen = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        ids.append(str(current.id))
        current = current.parent_document
    return ids


def create_review_request(*, document, submitted_by, request, diff_summary=None):
    """Create the pending ReviewRequest + notifications + audit for a version."""
    space = document.space
    exclude_ids = _version_chain_ids(document)
    conflict_hints = detect_conflicts(
        space, document.text_content or "", exclude_document_ids=exclude_ids
    )
    review = ReviewRequest.objects.create(
        space=space,
        document=document,
        submitted_by=submitted_by,
        diff_summary=diff_summary or {},
        conflict_hints=conflict_hints,
    )
    create_audit_log(
        user=submitted_by,
        action="document_review_submit",
        target_type="Document",
        target_id=str(document.id),
        details={
            "review_id": str(review.id),
            "title": document.title,
            "version": document.version,
            "conflicts": len(conflict_hints),
            "space_id": str(space.id) if space else None,
        },
        request=request,
    )
    reviewers = _reviewer_users(space, exclude_user=submitted_by)
    notify_many(
        reviewers,
        "review_requested",
        f"待审批：《{document.title}》 v{document.version}",
        body=f"{submitted_by.username or submitted_by.email} 提交了新版本，等待审批后才会进入 AI 索引。",
        link="/knowledge/review-queue",
        metadata={"review_id": str(review.id), "document_id": str(document.id)},
    )
    notify_many(
        _term_owner_users(document, exclude_user=submitted_by),
        "term_document_review",
        f"你负责的科目有文档待审批：《{document.title}》",
        link="/knowledge/review-queue",
        metadata={"review_id": str(review.id)},
    )
    return review


def create_pending_version(*, current_doc, new_text, reason, actor, request):
    """require_review branch of version creation: stage, don't index.

    Creates the v+1 Document in ``pending_review`` (no chunks, parent stays
    fully active) plus its ReviewRequest. Approval later runs the same atomic
    switch as direct publishing.
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
        updated_by=actor,
        status="pending_review",
        version=current_doc.version + 1,
        parent_document=current_doc,
        content_hash="",
    )
    # Carry taxonomy tags forward so reviewers/term owners see them.
    DocumentTag.objects.bulk_create(
        [
            DocumentTag(document=new_doc, term_id=tag.term_id, tagged_by=tag.tagged_by)
            for tag in DocumentTag.objects.filter(document=current_doc)
        ],
        ignore_conflicts=True,
    )
    diff_summary = build_diff_summary(current_doc.text_content or "", new_text or "")
    review = create_review_request(
        document=new_doc, submitted_by=actor, request=request, diff_summary=diff_summary
    )
    return new_doc, {
        "id": str(new_doc.id),
        "version": new_doc.version,
        "parent_document": str(current_doc.id),
        "status": "pending_review",
        "review_id": str(review.id),
        "pending_review": True,
        "reason": reason,
        "conflict_hints": review.conflict_hints,
    }


def _publish_approved_version(review, *, request):
    """Atomic publish on approval — mirrors _create_version_atomically."""
    from apps.knowledge.links import sync_document_links
    from apps.knowledge.taxonomy_views import sync_chunk_term_metadata

    doc = (
        Document.objects.select_for_update(of=("self",))
        .select_related("space")
        .get(id=review.document_id)
    )
    now = timezone.now()
    if doc.parent_document_id:
        parent = Document.objects.select_for_update(of=("self",)).get(
            id=doc.parent_document_id
        )
        if parent.status == "active" or parent.status == "stale":
            parent.effective_to = now
            parent.status = "superseded"
            parent.save(update_fields=["effective_to", "status", "updated_at"])
            DocumentChunk.objects.filter(document=parent).delete()

    published_via_task = False
    chunks = []
    if doc.text_content:
        from apps.rag.pipeline import RAGPipeline

        pipeline = RAGPipeline(ingestion=True)
        chunks = pipeline.ingest_text_content(doc)
        doc.chunk_count = len(chunks)
        doc.status = "active"
        doc.effective_from = now
        doc.save(update_fields=["chunk_count", "status", "effective_from", "updated_at"])
        sync_chunk_term_metadata(doc)
        sync_document_links(doc)
    elif doc.file:
        # File uploads need the parser — run through the durable Celery path.
        doc.status = "processing"
        doc.effective_from = now
        doc.save(update_fields=["status", "effective_from", "updated_at"])
        published_via_task = True
        from apps.knowledge.ingestion import enqueue_document_ingestion

        transaction.on_commit(
            lambda: enqueue_document_ingestion(
                doc, requested_by=review.submitted_by, trigger="upload"
            )
        )
    else:
        doc.status = "active"
        doc.effective_from = now
        doc.save(update_fields=["status", "effective_from", "updated_at"])

    return doc, {
        "document_id": str(doc.id),
        "version": doc.version,
        "status": doc.status,
        "chunk_count": len(chunks),
        "published_via_task": published_via_task,
    }


# ── Endpoints ────────────────────────────────────────────────────────


def _review_payload(review):
    doc = review.document
    return {
        "id": str(review.id),
        "document": {
            "id": str(doc.id),
            "title": doc.title,
            "version": doc.version,
            "status": doc.status,
            "parent_document": str(doc.parent_document_id) if doc.parent_document_id else None,
        },
        "submitted_by": {
            "id": str(review.submitted_by_id),
            "name": review.submitted_by.username or review.submitted_by.email,
        },
        "reviewer": (
            {
                "id": str(review.reviewer_id),
                "name": review.reviewer.username or review.reviewer.email,
            }
            if review.reviewer_id
            else None
        ),
        "diff_summary": review.diff_summary,
        "conflict_hints": review.conflict_hints,
        "decision": review.decision,
        "comment": review.comment,
        "decided_at": review.decided_at,
        "created_at": review.created_at,
    }


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def submit_review(request, pk):
    """Explicitly (re)submit a document version for review.

    Covers the rejected → resubmit loop and drafts created before the space
    enabled require_review. Upload/version-create in a require_review space
    submit automatically.
    """
    try:
        document = Document.objects.select_related("space", "parent_document").get(pk=pk)
    except Document.DoesNotExist:
        raise NotFound("Document not found.")
    space = document.space
    if space is None or effective_space_role(request.user, space) is None:
        raise NotFound("Document not found.")
    if document.status not in ("draft", "rejected", "pending_review", "failed"):
        raise ValidationError({"detail": f"Cannot submit a {document.status} document for review."})
    if ReviewRequest.objects.filter(document=document, decision="pending").exists():
        raise ValidationError({"detail": "This version already has a pending review."})

    if document.status != "pending_review":
        document.status = "pending_review"
        document.save(update_fields=["status", "updated_at"])
    parent_text = (
        document.parent_document.text_content if document.parent_document_id else ""
    )
    review = create_review_request(
        document=document,
        submitted_by=request.user,
        request=request,
        diff_summary=build_diff_summary(parent_text or "", document.text_content or ""),
    )
    return Response(_review_payload(review), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def review_queue(request):
    """Pending reviews for the active space (reviewer/knowledge_admin/owner)."""
    space = resolve_request_space(request)
    role = effective_space_role(request.user, space)
    if not is_platform_admin(request.user) and role not in REVIEWER_ROLES:
        raise PermissionDenied("Review queue requires reviewer rights.")
    decision = request.query_params.get("decision", "pending")
    qs = (
        ReviewRequest.objects.filter(space=space)
        .select_related("document", "submitted_by", "reviewer")
        .order_by("-created_at")
    )
    if decision != "all":
        qs = qs.filter(decision=decision)
    return Response([_review_payload(r) for r in qs[:100]])


def _resolve_review_for_decision(request, pk):
    try:
        review = ReviewRequest.objects.select_related(
            "space", "document", "submitted_by"
        ).get(pk=pk)
    except ReviewRequest.DoesNotExist:
        raise NotFound("Review request not found.")
    space = review.space
    active_space = resolve_request_space(request, required=False)
    if active_space is not None and space.id != active_space.id:
        raise NotFound("Review request not found.")
    role = effective_space_role(request.user, space)
    if not is_platform_admin(request.user) and role not in REVIEWER_ROLES:
        raise PermissionDenied("Deciding reviews requires reviewer rights.")
    if review.submitted_by_id == request.user.id:
        raise PermissionDenied("职责分离：不能审批自己提交的版本。")
    return review


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def review_approve(request, pk):
    _resolve_review_for_decision(request, pk)
    comment = str(request.data.get("comment", "") or "")
    mark_stale_ids = request.data.get("mark_stale_ids") or []

    with transaction.atomic():
        review = (
            ReviewRequest.objects.select_for_update()
            .select_related("space", "document", "submitted_by")
            .get(pk=pk)
        )
        if review.decision != ReviewRequest.DECISION_PENDING:
            raise ValidationError({"detail": f"Review already {review.decision}."})

        doc, publish_info = _publish_approved_version(review, request=request)

        # Reviewer one-click: mark superseded-by-content conflicts as stale.
        stale_marked = []
        if isinstance(mark_stale_ids, list) and mark_stale_ids:
            hinted = {h.get("document_id") for h in (review.conflict_hints or [])}
            for target in Document.objects.select_for_update(of=("self",)).filter(
                id__in=[i for i in mark_stale_ids if str(i) in hinted],
                space=review.space,
                status="active",
            ):
                target.status = "stale"
                target.save(update_fields=["status", "updated_at"])
                stale_marked.append(str(target.id))

        review.decision = ReviewRequest.DECISION_APPROVED
        review.reviewer = request.user
        review.comment = comment
        review.decided_at = timezone.now()
        review.save(update_fields=["decision", "reviewer", "comment", "decided_at", "updated_at"])

    create_audit_log(
        user=request.user,
        action="document_review_approve",
        target_type="Document",
        target_id=str(review.document_id),
        details={
            "review_id": str(review.id),
            "title": review.document.title,
            "version": review.document.version,
            "stale_marked": stale_marked,
            "space_id": str(review.space_id),
        },
        request=request,
    )
    notify(
        review.submitted_by,
        "review_approved",
        f"审批通过：《{review.document.title}》 v{review.document.version}",
        body=(comment or "版本已生效并进入 AI 索引。"),
        level="success",
        link=f"/knowledge?doc={review.document_id}",
    )
    notify_many(
        _term_owner_users(review.document, exclude_user=request.user),
        "term_document_updated",
        f"你负责的科目有文档更新生效：《{review.document.title}》 v{review.document.version}",
        link=f"/knowledge?doc={review.document_id}",
    )
    payload = _review_payload(review)
    payload["publish"] = publish_info
    payload["stale_marked"] = stale_marked
    return Response(payload)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def review_reject(request, pk):
    _resolve_review_for_decision(request, pk)
    comment = str(request.data.get("comment", "") or "")

    with transaction.atomic():
        review = (
            ReviewRequest.objects.select_for_update()
            .select_related("space", "document", "submitted_by")
            .get(pk=pk)
        )
        if review.decision != ReviewRequest.DECISION_PENDING:
            raise ValidationError({"detail": f"Review already {review.decision}."})
        doc = Document.objects.select_for_update(of=("self",)).get(
            id=review.document_id
        )
        doc.status = "rejected"
        doc.save(update_fields=["status", "updated_at"])
        review.decision = ReviewRequest.DECISION_REJECTED
        review.reviewer = request.user
        review.comment = comment
        review.decided_at = timezone.now()
        review.save(update_fields=["decision", "reviewer", "comment", "decided_at", "updated_at"])

    create_audit_log(
        user=request.user,
        action="document_review_reject",
        target_type="Document",
        target_id=str(review.document_id),
        details={
            "review_id": str(review.id),
            "title": review.document.title,
            "version": review.document.version,
            "comment": comment[:500],
            "space_id": str(review.space_id),
        },
        request=request,
    )
    notify(
        review.submitted_by,
        "review_rejected",
        f"审批被驳回：《{review.document.title}》 v{review.document.version}",
        body=comment or "请修改后重新提交。",
        level="warning",
        link=f"/knowledge?doc={review.document_id}",
    )
    return Response(_review_payload(review))
