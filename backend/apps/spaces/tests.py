# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""V6.0 multi-space isolation & access-control tests.

Run with:
    python manage.py test apps.spaces --settings=config.settings.test

Covers the core security guarantees from SPEC.MD:
  - documents, sessions, and retrieval are isolated per space;
  - an access code grants only its membership role (no RBAC bypass);
  - the retired crawler API is gone.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.chat.models import ChatSession, Citation, Message
from apps.knowledge.models import Document, DocumentChunk
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.spaces.models import (
    BusinessLine,
    InviteCode,
    KnowledgeSpace,
    Organization,
    OrganizationMembership,
    SpaceMembership,
)
from apps.spaces import permissions as sp
from apps.spaces.views import _hash_code

User = get_user_model()


def make_space(org, code, name, visibility="private"):
    return KnowledgeSpace.objects.create(
        organization=org, name=name, code=code, visibility=visibility, status="active"
    )


def make_doc(space, title="Doc", status="active"):
    return Document.objects.create(
        title=title,
        file=f"documents/{title}.txt",
        file_type="txt",
        file_size=10,
        status=status,
        uploaded_by=space.created_by or User.objects.filter(is_superuser=True).first(),
        space=space,
    )


class SpaceTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="Org", slug="org")
        cls.bl = BusinessLine.objects.create(organization=cls.org, name="Audit", code="audit")
        cls.space_a = make_space(cls.org, "space-a", "Space A")
        cls.space_b = make_space(cls.org, "space-b", "Space B")

        cls.alice = User.objects.create_user(username="alice", email="alice@test.com", password="x")
        cls.bob = User.objects.create_user(username="bob", email="bob@test.com", password="x")
        cls.admin = User.objects.create_superuser(username="admin", email="admin@test.com", password="x")

        # Alice is a member of A only; Bob is a member of B only.
        SpaceMembership.objects.create(space=cls.space_a, user=cls.alice, role="member", status="active")
        SpaceMembership.objects.create(space=cls.space_b, user=cls.bob, role="member", status="active")


class DocumentIsolationTest(SpaceTestBase):
    def test_document_list_scoped_to_active_space(self):
        make_doc(self.space_a, "A-doc")
        make_doc(self.space_b, "B-doc")
        self.client.force_authenticate(self.admin)  # platform admin sees all spaces

        resp = self.client.get("/api/v1/documents/", HTTP_X_SPACE_ID=str(self.space_a.id))
        self.assertEqual(resp.status_code, 200)
        titles = {d["title"] for d in resp.json().get("results", resp.json())}
        self.assertIn("A-doc", titles)
        self.assertNotIn("B-doc", titles, "Space A listing leaked a Space B document")

    def test_document_detail_blocked_cross_space(self):
        b_doc = make_doc(self.space_b, "B-doc")
        self.client.force_authenticate(self.admin)
        # Request B's doc while the active space is A -> not found (isolated).
        resp = self.client.get(f"/api/v1/documents/{b_doc.id}/", HTTP_X_SPACE_ID=str(self.space_a.id))
        self.assertEqual(resp.status_code, 404)

    def test_delete_cited_document_clears_citations_first(self):
        doc = make_doc(self.space_a, "Cited-doc")
        chunk = DocumentChunk.objects.create(
            document=doc, space=self.space_a, content="cited content", chunk_index=0
        )
        session = ChatSession.objects.create(user=self.admin, space=self.space_a, title="cited session")
        message = Message.objects.create(
            session=session, role="assistant", content="answer with citation", space=self.space_a
        )
        Citation.objects.create(
            message=message, document=doc, chunk=chunk, relevance_score=0.9, space=self.space_a
        )

        self.client.force_authenticate(self.admin)
        resp = self.client.delete(f"/api/v1/documents/{doc.id}/", HTTP_X_SPACE_ID=str(self.space_a.id))

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Document.objects.filter(id=doc.id).exists())
        self.assertFalse(DocumentChunk.objects.filter(id=chunk.id).exists())
        self.assertFalse(Citation.objects.filter(document_id=doc.id).exists())


class SessionIsolationTest(SpaceTestBase):
    def test_session_list_scoped_to_active_space(self):
        # Carol is a member of both spaces.
        carol = User.objects.create_user(username="carol", email="carol@test.com", password="x")
        SpaceMembership.objects.create(space=self.space_a, user=carol, role="member", status="active")
        SpaceMembership.objects.create(space=self.space_b, user=carol, role="member", status="active")
        ChatSession.objects.create(user=carol, space=self.space_a, title="in-A")
        ChatSession.objects.create(user=carol, space=self.space_b, title="in-B")

        self.client.force_authenticate(carol)
        resp = self.client.get("/api/v1/chat/sessions/", HTTP_X_SPACE_ID=str(self.space_a.id))
        self.assertEqual(resp.status_code, 200)
        titles = {s["title"] for s in resp.json().get("results", resp.json())}
        self.assertEqual(titles, {"in-A"}, "Session list is not isolated by space")

    def test_spaces_list_excludes_unjoined_spaces(self):
        self.client.force_authenticate(self.alice)  # member of A only
        resp = self.client.get("/api/v1/spaces/")
        self.assertEqual(resp.status_code, 200)
        codes = {s["code"] for s in resp.json()}
        self.assertIn("space-a", codes)
        self.assertNotIn("space-b", codes, "Alice should not see Space B")


class AccessCodeTest(SpaceTestBase):
    def _make_code(self, space, role="member"):
        raw = "JOIN-TEST-CODE"
        InviteCode.objects.create(
            space=space, code_hash=_hash_code(raw), code_prefix=raw[:8],
            role=role, status="active",
        )
        return raw

    def test_join_by_code_grants_only_membership_role(self):
        raw = self._make_code(self.space_b, role="member")
        self.client.force_authenticate(self.alice)  # not yet a member of B
        resp = self.client.post("/api/v1/spaces/join/", {"code": raw}, format="json")
        self.assertEqual(resp.status_code, 200)
        membership = SpaceMembership.objects.get(space=self.space_b, user=self.alice)
        self.assertEqual(membership.role, "member")
        # The code granted entry as 'member' — it must NOT confer space.update.
        self.assertFalse(sp.has_space_permission(self.alice, self.space_b, sp.SPACE_UPDATE))
        self.assertTrue(sp.has_space_permission(self.alice, self.space_b, sp.CHAT_ASK))

    def test_invalid_code_rejected(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.post("/api/v1/spaces/join/", {"code": "NOPE"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_revoked_code_cannot_join(self):
        raw = self._make_code(self.space_b)
        InviteCode.objects.filter(code_hash=_hash_code(raw)).update(status="revoked")
        self.client.force_authenticate(self.alice)
        resp = self.client.post("/api/v1/spaces/join/", {"code": raw}, format="json")
        self.assertEqual(resp.status_code, 400)


class PermissionMatrixTest(SpaceTestBase):
    def test_role_permissions(self):
        # Owner can update; member cannot; guest cannot view docs' download.
        SpaceMembership.objects.create(space=self.space_a, user=self.bob, role="owner", status="active")
        self.assertTrue(sp.has_space_permission(self.bob, self.space_a, sp.SPACE_UPDATE))
        self.assertFalse(sp.has_space_permission(self.alice, self.space_a, sp.SPACE_UPDATE))
        self.assertTrue(sp.has_space_permission(self.alice, self.space_a, sp.DOCUMENT_VIEW))

    def test_no_access_without_membership(self):
        self.assertIsNone(sp.effective_space_role(self.alice, self.space_b))
        self.assertFalse(sp.has_space_permission(self.alice, self.space_b, sp.DOCUMENT_VIEW))

    def test_platform_admin_sees_everything(self):
        self.assertEqual(sp.effective_space_role(self.admin, self.space_a), sp.ROLE_SUPER_ADMIN)
        self.assertTrue(sp.has_space_permission(self.admin, self.space_b, sp.SPACE_UPDATE))


class RetrievalIsolationTest(SpaceTestBase):
    def test_retriever_only_returns_active_space_chunks(self):
        doc_a = make_doc(self.space_a, "A")
        doc_b = make_doc(self.space_b, "B")
        DocumentChunk.objects.create(
            document=doc_a, space=self.space_a, content="alpha content",
            chunk_index=0, embedding=[1.0, 1.0],
        )
        DocumentChunk.objects.create(
            document=doc_b, space=self.space_b, content="beta content",
            chunk_index=0, embedding=[1.0, 1.0],
        )

        from apps.rag.retriever import PgVectorRetriever
        retriever = PgVectorRetriever()
        with patch("apps.rag.retriever.EmbeddingService") as MockEmb:
            MockEmb.return_value.embed.return_value = [1.0, 1.0]
            # Call the space-filtered code path directly (DB-agnostic ORM filter).
            results = retriever._search_sqlite(
                "anything", top_k=10, threshold=0.1, filters=None, space_id=str(self.space_a.id)
            )
        contents = {r["content"] for r in results}
        self.assertIn("alpha content", contents)
        self.assertNotIn("beta content", contents, "Retrieval leaked a chunk from another space")


class CrawlerRemovedTest(SpaceTestBase):
    def test_crawler_api_is_gone(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.get("/api/v1/crawl/")
        self.assertEqual(resp.status_code, 404, "Crawler API should no longer be routed")


class DocumentPermissionTest(SpaceTestBase):
    def test_member_cannot_upload(self):
        # Alice is a plain member of A -> no document.upload permission.
        self.assertFalse(sp.has_space_permission(self.alice, self.space_a, sp.DOCUMENT_UPLOAD))
        self.client.force_authenticate(self.alice)
        f = SimpleUploadedFile("t.txt", b"hello", content_type="text/plain")
        resp = self.client.post(
            "/api/v1/documents/",
            {"title": "x", "file": f, "file_type": "txt", "file_size": 5},
            format="multipart",
            HTTP_X_SPACE_ID=str(self.space_a.id),
        )
        self.assertEqual(resp.status_code, 403, "A plain member must not be able to upload")

    def test_knowledge_admin_can_upload_in_own_space_only(self):
        SpaceMembership.objects.create(
            space=self.space_a, user=self.bob, role="knowledge_admin", status="active"
        )
        self.assertTrue(sp.has_space_permission(self.bob, self.space_a, sp.DOCUMENT_UPLOAD))
        # ...but not in space B where Bob is only a member.
        self.assertFalse(sp.has_space_permission(self.bob, self.space_b, sp.DOCUMENT_UPLOAD))

    def test_member_view_allowed(self):
        self.assertTrue(sp.has_space_permission(self.alice, self.space_a, sp.DOCUMENT_VIEW))


class OrgBusinessAdminTest(SpaceTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.org2 = Organization.objects.create(name="Org2", slug="org2")
        cls.bl1 = BusinessLine.objects.create(organization=cls.org2, name="BL1", code="bl1")
        cls.bl2 = BusinessLine.objects.create(organization=cls.org2, name="BL2", code="bl2")
        cls.s1 = KnowledgeSpace.objects.create(
            organization=cls.org2, business_line=cls.bl1, name="S1", code="s1", status="active"
        )
        cls.s2 = KnowledgeSpace.objects.create(
            organization=cls.org2, business_line=cls.bl2, name="S2", code="s2", status="active"
        )
        cls.org_admin = User.objects.create_user(username="oadm", email="oadm@test.com", password="x")
        cls.biz_admin = User.objects.create_user(username="badm", email="badm@test.com", password="x")
        OrganizationMembership.objects.create(
            organization=cls.org2, user=cls.org_admin, role="org_admin"
        )
        OrganizationMembership.objects.create(
            organization=cls.org2, business_line=cls.bl1, user=cls.biz_admin, role="business_admin"
        )

    def test_org_admin_has_full_access_to_all_org_spaces(self):
        self.assertEqual(sp.effective_space_role(self.org_admin, self.s1), sp.ROLE_ORG_ADMIN)
        self.assertEqual(sp.effective_space_role(self.org_admin, self.s2), sp.ROLE_ORG_ADMIN)
        self.assertTrue(sp.has_space_permission(self.org_admin, self.s1, sp.SPACE_UPDATE))
        self.assertTrue(sp.has_space_permission(self.org_admin, self.s2, sp.DOCUMENT_UPLOAD))
        ids = set(sp.accessible_spaces(self.org_admin).values_list("id", flat=True))
        self.assertIn(self.s1.id, ids)
        self.assertIn(self.s2.id, ids)

    def test_business_admin_scoped_to_business_line(self):
        self.assertEqual(sp.effective_space_role(self.biz_admin, self.s1), sp.ROLE_BUSINESS_ADMIN)
        self.assertIsNone(sp.effective_space_role(self.biz_admin, self.s2))
        self.assertTrue(sp.has_space_permission(self.biz_admin, self.s1, sp.SPACE_UPDATE))
        self.assertFalse(sp.has_space_permission(self.biz_admin, self.s2, sp.DOCUMENT_VIEW))
        ids = set(sp.accessible_spaces(self.biz_admin).values_list("id", flat=True))
        self.assertIn(self.s1.id, ids)
        self.assertNotIn(self.s2.id, ids)

    def test_org_admin_can_create_space(self):
        self.assertTrue(sp.can_create_space(self.org_admin))
        self.assertFalse(sp.can_create_space(self.alice))
