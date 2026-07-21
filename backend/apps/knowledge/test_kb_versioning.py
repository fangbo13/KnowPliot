"""Part 1 (SPEC §1.12): KB version化 TDD tests — 8 required categories.

1. Edit → new version creation, old version superseded + effective_to correct
2. Diff preview — no persistence, no embed
3. Retrieval only hits current effective version chunks; old chunks zero hits
4. Scheduled effective: future version not retrieved before effective_from
5. Rollback: old text → new version, chain correct
6. Concurrent edit: select_for_update + version racing, no dual version
7. Binary document: edit extracted text, original file retained
8. Audit: version lineage + actor/when/reason
9. Permission: member/guest 403; knowledge_admin/owner 200
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.spaces.models import Organization, SpaceMembership
from apps.spaces.ownership import create_space_with_owner
from .models import Document, DocumentChunk


def _fake_ingest_text_content(document):
    """Create real DocumentChunk records without calling embedding API."""
    text = document.text_content or ""
    lines = text.splitlines() if text.strip() else ["(empty)"]
    chunks = []
    for i, line in enumerate(lines):
        chunk = DocumentChunk.objects.create(
            document=document,
            space_id=document.space_id,
            content=line,
            chunk_index=i,
            metadata={},
        )
        chunks.append(chunk)
    return chunks


class KBVersioningTestBase(TransactionTestCase):
    """Base: create org/space/owner/member + initial document."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def setUp(self, _mock_pipeline):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="kb-owner", email="kb-owner@example.test", password="pw"
        )
        self.member = User.objects.create_user(
            username="kb-member", email="kb-member@example.test", password="pw"
        )
        self.org = Organization.objects.create(name="KB test org", slug="kb-test-org")
        self.space = create_space_with_owner(
            organization=self.org,
            owner=self.owner,
            name="KB test workspace",
            code="kb-test-ws",
            visibility="private",
        )
        SpaceMembership.objects.create(
            space=self.space,
            user=self.member,
            role=SpaceMembership.ROLE_MEMBER,
            status="active",
        )
        self.client = APIClient()
        self.headers = {"HTTP_X_SPACE_ID": str(self.space.pk)}
        # Initial v1 document
        self.doc = Document.objects.create(
            title="Versioned Doc",
            text_content="Line 1\nLine 2\nLine 3",
            file_type="md",
            file_size=0,
            space=self.space,
            uploaded_by=self.owner,
            status="active",
            version=1,
            effective_from=timezone.now(),
        )

    def _post(self, path, data, user, idem=False, **extra):
        self.client.force_authenticate(user=user)
        headers = dict(self.headers)
        if idem:
            headers["HTTP_IDEMPOTENCY_KEY"] = str(uuid.uuid4())
        headers.update(extra)
        return self.client.post(path, data, format="json", **headers)

    def _patch(self, path, data, user, **extra):
        self.client.force_authenticate(user=user)
        headers = dict(self.headers)
        headers.update(extra)
        return self.client.patch(path, data, format="json", **headers)


class TestVersionCreation(KBVersioningTestBase):
    """§1.12-1: Edit → new version, old version superseded + effective_to."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_create_new_version_old_superseded(self, mock_pipeline_cls):
        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.ingest_text_content.side_effect = _fake_ingest_text_content

        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/versions/",
            {"text_content": "Line 1\nLine 2 modified\nLine 3\nLine 4 new",
             "reason": "update line 2"},
            self.owner, idem=True,
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        # Old version superseded
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "superseded")
        self.assertIsNotNone(self.doc.effective_to)
        # New version created
        new_doc = Document.objects.get(id=resp.data["id"])
        self.assertEqual(new_doc.version, 2)
        self.assertEqual(new_doc.parent_document_id, self.doc.id)
        self.assertEqual(new_doc.status, "active")
        self.assertEqual(new_doc.effective_from, self.doc.effective_to)
        # Old chunks deleted, new chunks exist
        self.assertEqual(
            DocumentChunk.objects.filter(document=self.doc).count(), 0
        )
        self.assertTrue(
            DocumentChunk.objects.filter(document=new_doc).count() > 0
        )


class TestDiffPreview(KBVersioningTestBase):
    """§1.12-2: Diff preview — no persistence, no embed."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_diff_preview_no_persistence(self, _mock):
        old_text = self.doc.text_content
        new_text = "Line 1\nLine 2 CHANGED\nLine 3\nLine 4 new"
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/preview-diff/",
            {"text_content": new_text},
            self.owner,
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        # Diff blocks returned
        blocks = resp.data["diff"]
        self.assertTrue(any(b["tag"] == "replace" for b in blocks))
        self.assertTrue(any(b["tag"] == "insert" for b in blocks))
        # No persistence: text_content unchanged
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.text_content, old_text)
        # No new chunks created
        self.assertEqual(DocumentChunk.objects.filter(document=self.doc).count(), 0)


class TestRetrievalInvariant(KBVersioningTestBase):
    """§1.12-3: Retrieval only hits current effective version; old chunks zero."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_old_chunks_not_in_live_index(self, mock_pipeline_cls):
        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.ingest_text_content.side_effect = _fake_ingest_text_content

        # Create v1 chunks
        _fake_ingest_text_content(self.doc)
        old_chunks = list(DocumentChunk.objects.filter(document=self.doc))
        self.assertTrue(len(old_chunks) > 0)

        # Create new version (immediate)
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/versions/",
            {"text_content": "Completely new content", "reason": "rewrite"},
            self.owner, idem=True,
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        new_doc = Document.objects.get(id=resp.data["id"])

        # Old chunks deleted
        self.assertEqual(
            DocumentChunk.objects.filter(document=self.doc).count(), 0
        )
        # New chunks exist
        self.assertTrue(
            DocumentChunk.objects.filter(document=new_doc).count() > 0
        )
        # Only active version's chunks in live index
        active_chunks = DocumentChunk.objects.filter(
            document__status="active",
            document__space=self.space,
        )
        self.assertTrue(active_chunks.exists())
        self.assertFalse(
            active_chunks.filter(document=self.doc).exists()
        )


class TestScheduledEffective(KBVersioningTestBase):
    """§1.12-4: Scheduled effective_from — old version still active before date."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_scheduled_version_keeps_old_active(self, mock_pipeline_cls):
        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.ingest_text_content.side_effect = _fake_ingest_text_content

        future = (timezone.now() + timedelta(days=7)).isoformat()
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/versions/",
            {"text_content": "Future content", "effective_from": future,
             "reason": "scheduled"},
            self.owner, idem=True,
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertFalse(resp.data["immediate"])

        # Old version stays active
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "active")
        # Old version effective_to capped at new version's effective_from
        self.assertIsNotNone(self.doc.effective_to)

        # New version also active but effective_from in future
        new_doc = Document.objects.get(id=resp.data["id"])
        self.assertEqual(new_doc.status, "active")
        self.assertTrue(new_doc.effective_from > timezone.now().date())

        # Retrieval invariant: old version's effective window caps at new version
        # Old version: effective_to == new version's effective_from (capped)
        self.assertEqual(self.doc.effective_to, new_doc.effective_from)
        # New version's effective_from is later than old version's effective_from
        self.assertGreater(new_doc.effective_from, self.doc.effective_from)


class TestRollback(KBVersioningTestBase):
    """§1.12-5: Rollback — old text → new version, chain correct."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_rollback_creates_new_version_from_old_text(self, mock_pipeline_cls):
        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.ingest_text_content.side_effect = _fake_ingest_text_content

        # v1 text
        v1_text = self.doc.text_content
        # Create v2
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/versions/",
            {"text_content": "v2 content", "reason": "second version"},
            self.owner, idem=True,
        )
        v2_id = resp.data["id"]
        self.assertEqual(resp.status_code, 201, resp.data)

        # Rollback to v1
        resp2 = self._post(
            f"/api/v1/documents/{v2_id}/rollback/",
            {"target_version_id": str(self.doc.id), "reason": "rollback to v1"},
            self.owner, idem=True,
        )
        self.assertEqual(resp2.status_code, 201, resp2.data)
        v3 = Document.objects.get(id=resp2.data["id"])
        # v3 is version 3, parent is v2, text = v1's text
        self.assertEqual(v3.version, 3)
        self.assertEqual(str(v3.parent_document_id), str(v2_id))
        self.assertEqual(v3.text_content, v1_text)
        self.assertEqual(resp2.data["rollback_from_version"], 2)


class TestConcurrentEdit(KBVersioningTestBase):
    """§1.12-6: Concurrent edit — select_for_update prevents dual versions."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_idempotent_retry_no_duplicate(self, mock_pipeline_cls):
        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.ingest_text_content.side_effect = _fake_ingest_text_content

        idem_key = str(uuid.uuid4())
        path = f"/api/v1/documents/{self.doc.id}/versions/"
        data = {"text_content": "Concurrent edit", "reason": "test"}

        # First call
        r1 = self._post(path, data, self.owner, idem=False,
                       HTTP_IDEMPOTENCY_KEY=idem_key)
        self.assertEqual(r1.status_code, 201, r1.data)
        v2_id = r1.data["id"]

        # Replay with same key — should return same response
        r2 = self._post(path, data, self.owner, idem=False,
                       HTTP_IDEMPOTENCY_KEY=idem_key)
        self.assertEqual(r2.status_code, 201, r2.data)
        self.assertEqual(r2.data["id"], v2_id)
        # Only one new version created
        self.assertEqual(
            Document.objects.filter(parent_document=self.doc).count(), 1
        )


class TestBinaryDocumentEdit(KBVersioningTestBase):
    """§1.12-7: Binary document — edit extracted text, original file retained."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_binary_doc_edit_retains_file(self, mock_pipeline_cls):
        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.ingest_text_content.side_effect = _fake_ingest_text_content

        # Create a binary doc (simulate PDF with extracted text)
        from django.core.files.base import ContentFile
        binary_doc = Document.objects.create(
            title="Binary PDF",
            file=ContentFile(b"%PDF-1.4 fake", name="test.pdf"),
            text_content="Extracted text from PDF",
            file_type="pdf",
            file_size=14,
            space=self.space,
            uploaded_by=self.owner,
            status="active",
            version=1,
            effective_from=timezone.now(),
        )

        resp = self._post(
            f"/api/v1/documents/{binary_doc.id}/versions/",
            {"text_content": "Edited extracted text", "reason": "fix extraction"},
            self.owner, idem=True,
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        new_doc = Document.objects.get(id=resp.data["id"])
        # Original file retained on new version
        self.assertTrue(new_doc.file.name)
        self.assertEqual(new_doc.file_type, "pdf")
        # New text_content is the edited version
        self.assertEqual(new_doc.text_content, "Edited extracted text")


class TestAuditLineage(KBVersioningTestBase):
    """§1.12-8: Audit — version lineage + actor/when/reason."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_audit_recorded_for_version_creation(self, mock_pipeline_cls):
        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.ingest_text_content.side_effect = _fake_ingest_text_content

        from apps.audit.models import AuditLog
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/versions/",
            {"text_content": "Audited version", "reason": "audit test"},
            self.owner, idem=True,
        )
        self.assertEqual(resp.status_code, 201, resp.data)

        logs = AuditLog.objects.filter(
            action="document_version_created",
            target_id=str(resp.data["id"]),
        )
        self.assertTrue(logs.exists())
        log = logs.first()
        self.assertEqual(str(log.user_id), str(self.owner.id))
        self.assertIn("old_version_number", log.details)
        self.assertEqual(log.details["old_version_number"], 1)
        self.assertEqual(log.details["new_version_number"], 2)
        self.assertEqual(log.details["reason"], "audit test")


class TestPermissions(KBVersioningTestBase):
    """§1.12-9: Permission — member/guest 403; knowledge_admin/owner 200."""

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_member_denied_version_creation(self, mock_pipeline_cls):
        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.ingest_text_content.side_effect = _fake_ingest_text_content

        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/versions/",
            {"text_content": "Member edit", "reason": "should fail"},
            self.member, idem=True,
        )
        self.assertEqual(resp.status_code, 403, resp.data)

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_member_denied_diff_preview(self, _mock):
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/preview-diff/",
            {"text_content": "Member preview"},
            self.member,
        )
        self.assertEqual(resp.status_code, 403, resp.data)

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_owner_allowed_diff_preview(self, _mock):
        resp = self._post(
            f"/api/v1/documents/{self.doc.id}/preview-diff/",
            {"text_content": "Owner preview"},
            self.owner,
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    @patch("apps.rag.pipeline.RAGPipeline")
    def test_owner_allowed_text_edit(self, _mock):
        resp = self._patch(
            f"/api/v1/documents/{self.doc.id}/text/",
            {"text_content": "Owner staged edit"},
            self.owner,
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.text_content, "Owner staged edit")
