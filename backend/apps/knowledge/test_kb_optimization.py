# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""KB optimization spec tests — space taxonomy modes, presets, reference
libraries, multi-space retrieval isolation, backlinks and local graph."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.spaces.models import BusinessLine, Organization, SpaceMembership
from apps.spaces.ownership import create_space_with_owner

from .library_views import resolve_reference_space_ids
from .models import (
    Document,
    DocumentChunk,
    DocumentLink,
    ReferenceLibrary,
    SpaceLibraryReference,
    TaxonomyDimension,
    TaxonomyTerm,
)
from .taxonomy_presets import TAXONOMY_PRESETS, seed_space_taxonomy
from .taxonomy_views import visible_dimensions_qs

User = get_user_model()


class _BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="kb-owner", email="kb-owner@example.test", password="pw"
        )
        cls.member = User.objects.create_user(
            username="kb-member", email="kb-member@example.test", password="pw"
        )
        cls.admin = User.objects.create_superuser(
            username="kb-admin", email="kb-admin@example.test", password="pw"
        )
        cls.org = Organization.objects.create(name="KB Org", slug="kb-org")
        cls.bl = BusinessLine.objects.create(
            organization=cls.org, name="Assurance", code="assurance"
        )
        cls.space_inherit = create_space_with_owner(
            organization=cls.org, owner=cls.owner,
            name="Inherit WS", code="kb-inherit-ws", visibility="private",
            business_line=cls.bl,
        )
        cls.space_private = create_space_with_owner(
            organization=cls.org, owner=cls.owner,
            name="Private WS", code="kb-private-ws", visibility="private",
            business_line=cls.bl,
        )
        cls.space_private.taxonomy_mode = "space"
        cls.space_private.save(update_fields=["taxonomy_mode"])
        cls.space_none = create_space_with_owner(
            organization=cls.org, owner=cls.owner,
            name="Enablement WS", code="kb-none-ws", visibility="private",
        )
        cls.space_none.taxonomy_mode = "none"
        cls.space_none.save(update_fields=["taxonomy_mode"])
        for space in (cls.space_inherit, cls.space_private, cls.space_none):
            SpaceMembership.objects.get_or_create(
                space=space, user=cls.member,
                defaults={"role": SpaceMembership.ROLE_MEMBER, "status": "active"},
            )
        # Shared dimensions: one business-line scoped + one org-wide.
        cls.dim_shared_bl = TaxonomyDimension.objects.create(
            organization=cls.org, business_line=cls.bl, code="account", name="会计科目"
        )
        cls.dim_shared_org = TaxonomyDimension.objects.create(
            organization=cls.org, code="fiscal_year", name="财年"
        )
        # Space-private dimension owned by space_private.
        cls.dim_private = TaxonomyDimension.objects.create(
            organization=cls.org, space=cls.space_private,
            code="project_phase", name="项目阶段",
        )

    def _client(self, user, space):
        client = APIClient()
        client.force_authenticate(user=user)
        client.credentials(HTTP_X_SPACE_ID=str(space.pk))
        return client


class TaxonomyModeTests(_BaseCase):
    """Spec §2.1 — dimension visibility follows the space's taxonomy_mode."""

    def test_inherit_space_sees_shared_dimensions_only(self):
        codes = set(visible_dimensions_qs(self.space_inherit).values_list("code", flat=True))
        self.assertEqual(codes, {"account", "fiscal_year"})

    def test_space_mode_sees_private_plus_org_wide(self):
        codes = set(visible_dimensions_qs(self.space_private).values_list("code", flat=True))
        self.assertEqual(codes, {"project_phase", "fiscal_year"})

    def test_none_mode_sees_nothing(self):
        self.assertEqual(visible_dimensions_qs(self.space_none).count(), 0)

    def test_dimension_api_dispatches_by_mode(self):
        client = self._client(self.member, self.space_none)
        resp = client.get("/api/v1/documents/taxonomy/dimensions/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_space_mode_owner_creates_private_dimension(self):
        client = self._client(self.owner, self.space_private)
        resp = client.post(
            "/api/v1/documents/taxonomy/dimensions/",
            {"code": "risk_area", "name": "风险领域"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        dim = TaxonomyDimension.objects.get(code="risk_area")
        self.assertEqual(dim.space_id, self.space_private.id)

    def test_inherit_mode_owner_cannot_create_shared_dimension(self):
        client = self._client(self.owner, self.space_inherit)
        resp = client.post(
            "/api/v1/documents/taxonomy/dimensions/",
            {"code": "blocked", "name": "Blocked"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_archives_private_dimension_but_not_shared(self):
        client = self._client(self.owner, self.space_private)
        resp = client.patch(
            f"/api/v1/documents/taxonomy/dimensions/{self.dim_private.id}/",
            {"status": "archived"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.dim_private.refresh_from_db()
        self.assertEqual(self.dim_private.status, "archived")
        resp = client.patch(
            f"/api/v1/documents/taxonomy/dimensions/{self.dim_shared_org.id}/",
            {"status": "archived"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_term_write_requires_dimension_scope(self):
        client = self._client(self.owner, self.space_private)
        resp = client.post(
            "/api/v1/documents/taxonomy/terms/",
            {"dimension": str(self.dim_private.id), "code": "phase1", "label": "阶段一"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        # Shared dimension term creation stays platform-admin only.
        resp = client.post(
            "/api/v1/documents/taxonomy/terms/",
            {"dimension": str(self.dim_shared_bl.id), "code": "cash", "label": "货币资金"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


class TaxonomyPresetTests(_BaseCase):
    """Spec §3.1 — preset seeding is one-shot and idempotent."""

    def test_seed_space_taxonomy_idempotent(self):
        created = seed_space_taxonomy(self.space_private, "audit_default")
        self.assertEqual(created, len(TAXONOMY_PRESETS["audit_default"]["dimensions"]))
        self.assertEqual(seed_space_taxonomy(self.space_private, "audit_default"), 0)
        account = TaxonomyDimension.objects.get(space=self.space_private, code="account")
        self.assertTrue(account.is_hierarchical)
        # Hierarchy copied: parent + children terms.
        self.assertTrue(
            TaxonomyTerm.objects.filter(dimension=account, parent__isnull=False).exists()
        )

    def test_seed_defaults_endpoint_gates_on_mode(self):
        client = self._client(self.owner, self.space_inherit)
        resp = client.post(
            "/api/v1/documents/taxonomy/seed-defaults/", {"preset": "audit_default"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        client = self._client(self.owner, self.space_private)
        resp = client.post(
            "/api/v1/documents/taxonomy/seed-defaults/", {"preset": "audit_default"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertGreater(resp.data["created"], 0)

    def test_seed_defaults_requires_admin_role(self):
        client = self._client(self.member, self.space_private)
        resp = client.post(
            "/api/v1/documents/taxonomy/seed-defaults/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_presets_catalog(self):
        client = self._client(self.member, self.space_private)
        resp = client.get("/api/v1/documents/taxonomy/presets/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["presets"][0]["code"], "audit_default")


class ReferenceLibraryTests(_BaseCase):
    """Spec §3.2 — platform-certified libraries and space references."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.lib_space = create_space_with_owner(
            organization=cls.org, owner=cls.admin,
            name="IFRS Library", code="kb-ifrs-lib", visibility="organization",
        )
        cls.library = ReferenceLibrary.objects.create(
            space=cls.lib_space, name="IFRS参考库", category="ifrs",
            status="published", is_official=True, published_by=cls.admin,
        )
        cls.unpublished_space = create_space_with_owner(
            organization=cls.org, owner=cls.admin,
            name="Draft Library", code="kb-draft-lib", visibility="organization",
        )
        cls.unpublished = ReferenceLibrary.objects.create(
            space=cls.unpublished_space, name="草稿库", category="other",
            status="unpublished",
        )

    def test_library_management_requires_platform_admin(self):
        client = self._client(self.owner, self.space_private)
        resp = client.get("/api/v1/documents/libraries/")
        self.assertEqual(resp.status_code, 403)
        client = self._client(self.admin, self.space_private)
        resp = client.get("/api/v1/documents/libraries/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)

    def test_catalog_lists_published_only(self):
        client = self._client(self.member, self.space_private)
        resp = client.get("/api/v1/documents/libraries/catalog/")
        self.assertEqual(resp.status_code, 200)
        names = {row["name"] for row in resp.data}
        self.assertEqual(names, {"IFRS参考库"})

    def test_space_owner_adds_reference_and_member_cannot(self):
        client = self._client(self.member, self.space_private)
        resp = client.post(
            "/api/v1/documents/library-references/",
            {"library": str(self.library.id)}, format="json",
        )
        self.assertEqual(resp.status_code, 403)
        client = self._client(self.owner, self.space_private)
        resp = client.post(
            "/api/v1/documents/library-references/",
            {"library": str(self.library.id)}, format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_cannot_reference_unpublished_library(self):
        client = self._client(self.owner, self.space_private)
        resp = client.post(
            "/api/v1/documents/library-references/",
            {"library": str(self.unpublished.id)}, format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_library_space_cannot_reference_itself(self):
        client = self._client(self.admin, self.lib_space)
        resp = client.post(
            "/api/v1/documents/library-references/",
            {"library": str(self.library.id)}, format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_resolve_reference_space_ids_respects_state(self):
        ref = SpaceLibraryReference.objects.create(
            space=self.space_private, library=self.library, added_by=self.owner
        )
        SpaceLibraryReference.objects.create(
            space=self.space_private, library=self.unpublished, added_by=self.owner
        )
        ids = resolve_reference_space_ids(self.space_private)
        self.assertEqual(ids, [str(self.lib_space.id)])
        # Disabled reference drops out immediately.
        ref.enabled = False
        ref.save(update_fields=["enabled"])
        self.assertEqual(resolve_reference_space_ids(self.space_private), [])
        # Unpublishing the library also removes it from scope.
        ref.enabled = True
        ref.save(update_fields=["enabled"])
        self.library.status = "unpublished"
        self.library.is_official = False
        self.library.save(update_fields=["status", "is_official"])
        self.assertEqual(resolve_reference_space_ids(self.space_private), [])


class _FakeEmbedder:
    def embed(self, text):
        return [1.0, 0.0, 0.0]


class MultiSpaceRetrievalTests(_BaseCase):
    """Spec §3.3 — retrieval is limited to the explicit space allowlist."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.lib_space = create_space_with_owner(
            organization=cls.org, owner=cls.admin,
            name="CAS Library", code="kb-cas-lib", visibility="organization",
        )
        cls.other_space = create_space_with_owner(
            organization=cls.org, owner=cls.admin,
            name="Other WS", code="kb-other-ws", visibility="private",
        )
        for space, title in (
            (cls.space_private, "Local doc"),
            (cls.lib_space, "Library doc"),
            (cls.other_space, "Foreign doc"),
        ):
            doc = Document.objects.create(
                title=title, text_content="revenue recognition",
                file_type="md", file_size=0, space=space,
                uploaded_by=cls.admin, status="active",
            )
            DocumentChunk.objects.create(
                document=doc, space=space, content="revenue recognition rules",
                chunk_index=0, embedding=[1.0, 0.0, 0.0], metadata={},
            )

    def test_search_never_leaks_unreferenced_spaces(self):
        from apps.rag.retriever import PgVectorRetriever, RetrievalFilters

        retriever = PgVectorRetriever(embedder=_FakeEmbedder())
        results = retriever._search_sqlite(
            "revenue", 10, 0.1, RetrievalFilters(),
            [str(self.space_private.id), str(self.lib_space.id)],
        )
        spaces = {row["space_id"] for row in results}
        self.assertEqual(
            spaces, {str(self.space_private.id), str(self.lib_space.id)}
        )
        titles = {row["document_title"] for row in results}
        self.assertNotIn("Foreign doc", titles)


class BacklinksAndLocalGraphTests(_BaseCase):
    """Spec §3.4 — Obsidian backlinks + center/depth local graph."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        def _doc(title):
            return Document.objects.create(
                title=title, text_content=f"content of {title}",
                file_type="md", file_size=0, space=cls.space_private,
                uploaded_by=cls.owner, status="active",
            )
        cls.doc_a = _doc("Doc A")
        cls.doc_b = _doc("Doc B")
        cls.doc_c = _doc("Doc C")
        DocumentLink.objects.create(
            space=cls.space_private, source=cls.doc_a, target=cls.doc_b,
            anchor_text="Doc B",
        )
        DocumentLink.objects.create(
            space=cls.space_private, source=cls.doc_b, target=cls.doc_c,
            anchor_text="Doc C",
        )

    def test_backlinks_endpoint(self):
        client = self._client(self.member, self.space_private)
        resp = client.get(f"/api/v1/documents/{self.doc_b.id}/backlinks/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["backlinks"]), 1)
        self.assertEqual(resp.data["backlinks"][0]["title"], "Doc A")

    def test_wikilink_edit_updates_backlinks(self):
        client = self._client(self.owner, self.space_private)
        resp = client.patch(
            f"/api/v1/documents/{self.doc_c.id}/text/",
            {"text_content": "See [[Doc B]] for details."},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        resp = client.get(f"/api/v1/documents/{self.doc_b.id}/backlinks/")
        titles = {row["title"] for row in resp.data["backlinks"]}
        self.assertIn("Doc C", titles)

    def test_local_graph_depth_limits_neighborhood(self):
        client = self._client(self.member, self.space_private)
        resp = client.get(
            "/api/v1/documents/graph/",
            {"center": str(self.doc_a.id), "depth": 1},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["mode"], "local")
        ids = {node["id"] for node in resp.data["nodes"]}
        self.assertEqual(ids, {str(self.doc_a.id), str(self.doc_b.id)})
        resp = client.get(
            "/api/v1/documents/graph/",
            {"center": str(self.doc_a.id), "depth": 2},
        )
        ids = {node["id"] for node in resp.data["nodes"]}
        self.assertEqual(
            ids, {str(self.doc_a.id), str(self.doc_b.id), str(self.doc_c.id)}
        )

    def test_global_graph_unchanged(self):
        client = self._client(self.member, self.space_private)
        resp = client.get("/api/v1/documents/graph/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["mode"], "global")
        self.assertEqual(len(resp.data["nodes"]), 3)
