# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §3 — review gate tests.

Covers the require_review state machine (draft → pending_review →
active/rejected), the L1 admission invariant (no chunks before approval),
separation of duties, and the reviewer queue permission gate.
"""

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.spaces.models import Organization, SpaceMembership
from apps.spaces.ownership import create_space_with_owner
from .models import Document, DocumentChunk, ReviewRequest


def _fake_ingest_text_content(document):
    """Create real DocumentChunk records without calling embedding API."""
    text = document.text_content or ""
    lines = text.splitlines() if text.strip() else ["(empty)"]
    chunks = []
    for i, line in enumerate(lines):
        chunks.append(
            DocumentChunk.objects.create(
                document=document,
                space_id=document.space_id,
                content=line,
                chunk_index=i,
                metadata={},
            )
        )
    return chunks


@patch("apps.knowledge.review_views.detect_conflicts", return_value=[])
class ReviewFlowTest(TestCase):
    """require_review space: version creation stages, approval publishes."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(
            username="rv-owner", email="rv-owner@example.test", password="pw"
        )
        cls.reviewer = User.objects.create_user(
            username="rv-reviewer", email="rv-reviewer@example.test", password="pw"
        )
        cls.member = User.objects.create_user(
            username="rv-member", email="rv-member@example.test", password="pw"
        )
        cls.knowledge_admin = User.objects.create_user(
            username="rv-kadmin", email="rv-kadmin@example.test", password="pw"
        )
        cls.org = Organization.objects.create(name="Review org", slug="review-org")
        cls.space = create_space_with_owner(
            organization=cls.org,
            owner=cls.owner,
            name="Review workspace",
            code="review-ws",
            visibility="private",
        )
        # Spec default, but set explicitly so the suite stays valid if the
        # model default ever changes.
        cls.space.review_policy = "require_review"
        cls.space.save(update_fields=["review_policy"])
        SpaceMembership.objects.create(
            space=cls.space, user=cls.reviewer,
            role=SpaceMembership.ROLE_REVIEWER, status="active",
        )
        SpaceMembership.objects.create(
            space=cls.space, user=cls.member,
            role=SpaceMembership.ROLE_MEMBER, status="active",
        )
        SpaceMembership.objects.create(
            space=cls.space, user=cls.knowledge_admin,
            role=SpaceMembership.ROLE_KNOWLEDGE_ADMIN, status="active",
        )

    def setUp(self):
        self.client = APIClient()
        self.headers = {"HTTP_X_SPACE_ID": str(self.space.pk)}
        self.doc = Document.objects.create(
            title="Gated Doc",
            text_content="Line 1\nLine 2",
            file_type="md",
            file_size=0,
            space=self.space,
            uploaded_by=self.owner,
            status="active",
            version=1,
        )

    def _post(self, path, data, user, idem=True):
        self.client.force_authenticate(user=user)
        headers = dict(self.headers)
        if idem:
            headers["HTTP_IDEMPOTENCY_KEY"] = str(uuid.uuid4())
        return self.client.post(path, data, format="json", **headers)

    def _stage_version(self, user=None):
        """Stage a version as pending_review via a non-owner user."""
        user = user or self.member
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/versions/",
            {"text_content": "Line 1\nLine 2 modified", "reason": "gated edit"},
            user,
        )
        self.assertEqual(resp.status_code, 202, resp.data)
        return resp.data

    def test_version_creation_stages_pending_review_without_chunks(self, _dc):
        data = self._stage_version()
        self.assertTrue(data["pending_review"])
        self.assertEqual(data["status"], "pending_review")
        new_doc = Document.objects.get(id=data["id"])
        self.assertEqual(new_doc.version, 2)
        self.assertEqual(new_doc.parent_document_id, self.doc.id)
        # L1 admission: staged versions never have retrievable chunks.
        self.assertEqual(DocumentChunk.objects.filter(document=new_doc).count(), 0)
        # Parent stays fully active until approval.
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "active")
        review = ReviewRequest.objects.get(id=data["review_id"])
        self.assertEqual(review.decision, "pending")
        self.assertEqual(review.submitted_by_id, self.member.id)
        self.assertIn("added_lines", review.diff_summary)

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_approve_publishes_and_supersedes_parent(self, mock_pipeline_cls, _dc):
        mock_pipeline_cls.return_value.ingest_text_content.side_effect = (
            _fake_ingest_text_content
        )
        data = self._stage_version()
        resp = self._post(
            f"/api/v1/documents/reviews/{data['review_id']}/approve/",
            {"comment": "looks good"},
            self.reviewer, idem=False,
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["decision"], "approved")
        new_doc = Document.objects.get(id=data["id"])
        self.assertEqual(new_doc.status, "active")
        self.assertGreater(DocumentChunk.objects.filter(document=new_doc).count(), 0)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "superseded")
        self.assertIsNotNone(self.doc.effective_to)
        self.assertEqual(DocumentChunk.objects.filter(document=self.doc).count(), 0)

    def test_reject_keeps_parent_active(self, _dc):
        data = self._stage_version()
        resp = self._post(
            f"/api/v1/documents/reviews/{data['review_id']}/reject/",
            {"comment": "needs work"},
            self.reviewer, idem=False,
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["decision"], "rejected")
        new_doc = Document.objects.get(id=data["id"])
        self.assertEqual(new_doc.status, "rejected")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "active")
        self.assertEqual(DocumentChunk.objects.filter(document=new_doc).count(), 0)

    def test_submitter_cannot_decide_own_review(self, _dc):
        # knowledge_admin submits (goes through review — not owner bypass)
        # and is a reviewer, but cannot approve their own submission.
        data = self._stage_version(self.knowledge_admin)
        resp = self._post(
            f"/api/v1/documents/reviews/{data['review_id']}/approve/",
            {}, self.knowledge_admin, idem=False,
        )
        self.assertEqual(resp.status_code, 403, resp.data)
        self.assertEqual(
            ReviewRequest.objects.get(id=data["review_id"]).decision, "pending"
        )

    def test_review_queue_requires_reviewer_rights(self, _dc):
        self._stage_version()
        self.client.force_authenticate(user=self.member)
        denied = self.client.get("/api/v1/documents/review-queue/", **self.headers)
        self.assertEqual(denied.status_code, 403)
        self.client.force_authenticate(user=self.reviewer)
        allowed = self.client.get("/api/v1/documents/review-queue/", **self.headers)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(len(allowed.data), 1)
        self.assertEqual(allowed.data[0]["document"]["title"], "Gated Doc")

    def test_rejected_version_can_be_resubmitted(self, _dc):
        data = self._stage_version()
        self._post(
            f"/api/v1/documents/reviews/{data['review_id']}/reject/",
            {"comment": "no"}, self.reviewer, idem=False,
        )
        resp = self._post(
            f"/api/v1/documents/{data['id']}/submit-review/", {}, self.member, idem=False,
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        new_doc = Document.objects.get(id=data["id"])
        self.assertEqual(new_doc.status, "pending_review")
        self.assertEqual(
            ReviewRequest.objects.filter(document_id=data["id"]).count(), 2
        )

    # ── Owner bypass (spec §3): owner may directly publish — no review gate ─

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_owner_version_bypasses_review(self, mock_pipeline_cls, _dc):
        """Space owner may directly publish a new version without review."""
        mock_pipeline_cls.return_value.ingest_text_content.side_effect = (
            _fake_ingest_text_content
        )
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/versions/",
            {"text_content": "Line 1\nLine 2 owner bypass", "reason": "owner edit"},
            self.owner,
        )
        # Owner bypasses review → 201 (directly published), not 202
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertNotIn("pending_review", resp.data)
        new_doc = Document.objects.get(id=resp.data["id"])
        self.assertEqual(new_doc.status, "active")
        # No ReviewRequest should exist for the owner's version
        self.assertFalse(
            ReviewRequest.objects.filter(document_id=new_doc.id).exists()
        )
        # Chunks created (direct publish)
        self.assertGreater(
            DocumentChunk.objects.filter(document=new_doc).count(), 0
        )
        # Parent superseded
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "superseded")

    @patch("apps.knowledge.ingestion.enqueue_document_ingestion")
    def test_owner_upload_bypasses_review(self, mock_enqueue, _dc):
        """Space owner uploads → document skips pending_review (spec §3)."""
        resp = self._post(
            "/api/v1/documents/",
            {"title": "Owner Direct Upload", "text_content": "Owner content"},
            self.owner,
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        doc = Document.objects.get(id=resp.data["id"])
        self.assertNotEqual(doc.status, "pending_review")
        self.assertFalse(ReviewRequest.objects.filter(document_id=doc.id).exists())
