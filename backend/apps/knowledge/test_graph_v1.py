"""Graph workspace v1 contract and semantic regression tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.spaces.models import BusinessLine, Organization, SpaceMembership
from apps.spaces.ownership import create_space_with_owner

from .models import (
    Document,
    DocumentLink,
    DocumentSimilarity,
    DocumentTag,
    TaxonomyDimension,
    TaxonomyTerm,
)


User = get_user_model()


class GraphQueryV1Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="graph-owner", email="graph-owner@example.test", password="pw"
        )
        cls.member = User.objects.create_user(
            username="graph-member", email="graph-member@example.test", password="pw"
        )
        cls.org = Organization.objects.create(name="Graph Org", slug="graph-org")
        cls.business_line = BusinessLine.objects.create(
            organization=cls.org, name="Assurance", code="graph-assurance"
        )
        cls.space = create_space_with_owner(
            organization=cls.org,
            owner=cls.owner,
            name="Graph Space",
            code="graph-space",
            visibility="private",
            business_line=cls.business_line,
        )
        SpaceMembership.objects.create(
            space=cls.space,
            user=cls.member,
            role=SpaceMembership.ROLE_MEMBER,
            status="active",
        )

        def document(title: str):
            return Document.objects.create(
                title=title,
                text_content=f"Content for {title}",
                file_type="md",
                file_size=0,
                space=cls.space,
                uploaded_by=cls.owner,
                status="active",
            )

        cls.doc_a = document("Doc A")
        cls.doc_b = document("Doc B")
        cls.doc_c = document("Doc C")
        cls.doc_d = document("Doc D")
        cls.link_ab = DocumentLink.objects.create(
            space=cls.space,
            source=cls.doc_a,
            target=cls.doc_b,
            anchor_text="to B",
        )
        cls.link_ba = DocumentLink.objects.create(
            space=cls.space,
            source=cls.doc_b,
            target=cls.doc_a,
            anchor_text="back to A",
        )
        DocumentLink.objects.create(
            space=cls.space,
            source=cls.doc_b,
            target=cls.doc_c,
            anchor_text="to C",
        )
        cls.ghost_link = DocumentLink.objects.create(
            space=cls.space,
            source=cls.doc_a,
            target=None,
            unresolved_title="Missing policy",
            anchor_text="Missing policy",
        )
        dimension = TaxonomyDimension.objects.create(
            organization=cls.org,
            space=cls.space,
            code="topic",
            name="Topic",
        )
        cls.term = TaxonomyTerm.objects.create(
            dimension=dimension,
            code="audit",
            label="Audit",
        )
        DocumentTag.objects.create(document=cls.doc_c, term=cls.term, tagged_by=cls.owner)
        DocumentTag.objects.create(document=cls.doc_d, term=cls.term, tagged_by=cls.owner)
        cls.similarity = DocumentSimilarity.objects.create(
            space=cls.space,
            source=cls.doc_c,
            target=cls.doc_d,
            score=0.91,
        )

    def api_client(self):
        client = APIClient()
        client.force_authenticate(user=self.member)
        client.credentials(HTTP_X_SPACE_ID=str(self.space.id))
        return client

    def query(self, **overrides):
        payload = {
            "schema_version": "graph.query.v1",
            "scope": {"mode": "global"},
            "edge_kinds": ["links_to"],
        }
        payload.update(overrides)
        return self.api_client().post(
            "/api/v1/documents/graph/query/", payload, format="json"
        )

    def test_query_preserves_reciprocal_link_direction_and_evidence(self):
        response = self.query()

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        links = [edge for edge in response.data["edges"] if edge["kind"] == "links_to"]
        directed_pairs = {(edge["source"], edge["target"]) for edge in links}
        a_id = next(node["id"] for node in response.data["nodes"] if node["label"] == "Doc A")
        b_id = next(node["id"] for node in response.data["nodes"] if node["label"] == "Doc B")
        self.assertIn((a_id, b_id), directed_pairs)
        self.assertIn((b_id, a_id), directed_pairs)
        self.assertTrue(all(edge["directed"] for edge in links))
        self.assertTrue(all(edge["evidence"]["ref"] for edge in links))

    def test_taxonomy_is_a_bipartite_term_node_not_a_document_clique(self):
        response = self.query(edge_kinds=["tagged_with"])

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        term_nodes = [node for node in response.data["nodes"] if node["type"] == "term"]
        self.assertEqual([node["label"] for node in term_nodes], ["Audit"])
        term_edges = [edge for edge in response.data["edges"] if edge["kind"] == "tagged_with"]
        self.assertEqual(len(term_edges), 2)
        self.assertTrue(all(edge["target"] == term_nodes[0]["id"] for edge in term_edges))

    def test_unresolved_wikilink_is_projected_as_a_ghost_node(self):
        response = self.query(include_ghosts=True)

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        ghosts = [node for node in response.data["nodes"] if node["type"] == "ghost"]
        self.assertEqual([node["label"] for node in ghosts], ["Missing policy"])
        ghost_edges = [edge for edge in response.data["edges"] if edge["target"] == ghosts[0]["id"]]
        self.assertEqual(len(ghost_edges), 1)
        self.assertEqual(ghost_edges[0]["provenance"], "explicit")

    def test_local_query_filters_edges_before_traversal(self):
        response = self.query(
            scope={
                "mode": "local",
                "center_id": str(self.doc_a.id),
                "depth": 1,
                "direction": "out",
            },
            edge_kinds=["links_to"],
        )

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual({node["label"] for node in response.data["nodes"]}, {"Doc A", "Doc B"})
        self.assertFalse(any(edge["kind"] == "tagged_with" for edge in response.data["edges"]))

    def test_local_center_is_resolved_before_result_limits(self):
        response = self.query(
            scope={
                "mode": "local",
                "center_id": str(self.doc_c.id),
                "depth": 1,
                "direction": "both",
            },
            limits={"nodes": 2, "edges": 10},
        )

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertIn("Doc C", {node["label"] for node in response.data["nodes"]})
        self.assertLessEqual(len(response.data["nodes"]), 2)
        self.assertEqual(response.data["meta"]["returned_nodes"], len(response.data["nodes"]))

    def test_large_global_graph_returns_taxonomy_overview_instead_of_raw_documents(self):
        Document.objects.bulk_create([
            Document(
                title=f"Scale document {index}",
                text_content="scale",
                file_type="md",
                file_size=0,
                space=self.space,
                uploaded_by=self.owner,
                status="active",
            )
            for index in range(301)
        ])

        response = self.query()

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertTrue(response.data["meta"]["overview"])
        self.assertGreaterEqual(response.data["meta"]["total_documents"], 305)
        self.assertTrue(all(node["type"] == "cluster" for node in response.data["nodes"]))
        self.assertLessEqual(len(response.data["nodes"]), 150)

    def test_dsl_filters_documents_before_building_edges(self):
        response = self.query(
            query='file:"Doc A" OR tag:audit',
            edge_kinds=["links_to", "tagged_with"],
        )

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        document_labels = {
            node["label"] for node in response.data["nodes"] if node["type"] == "document"
        }
        self.assertEqual(document_labels, {"Doc A", "Doc C", "Doc D"})
        self.assertFalse(any(edge["target"].endswith(str(self.doc_b.lineage_id)) for edge in response.data["edges"]))

    def test_dsl_reports_unsupported_path_field_with_position(self):
        response = self.query(query="path:policies")

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "unsupported_field")
        self.assertEqual(response.data["position"], 0)
        self.assertIn("file:", response.data["hint"])

    def test_groups_use_server_dsl_and_first_match_wins(self):
        response = self.query(
            groups=[
                {"id": "focus", "name": "Focus", "query": 'file:"Doc A"', "color": "#ef4444"},
                {"id": "all-docs", "name": "All docs", "query": "file:/Doc/", "color": "#3b82f6"},
            ]
        )

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        by_label = {
            node["label"]: node["properties"]
            for node in response.data["nodes"]
            if node["type"] == "document"
        }
        self.assertEqual(by_label["Doc A"]["group_id"], "focus")
        self.assertEqual(by_label["Doc A"]["group_color"], "#ef4444")
        self.assertEqual(by_label["Doc B"]["group_id"], "all-docs")

    def test_path_returns_explainable_explicit_route(self):
        response = self.api_client().post(
            "/api/v1/documents/graph/path/",
            {
                "schema_version": "graph.path.v1",
                "source_id": str(self.doc_a.id),
                "target_id": str(self.doc_c.id),
                "edge_kinds": ["links_to"],
                "max_paths": 3,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual(len(response.data["paths"]), 1)
        self.assertEqual(
            [node["label"] for node in response.data["paths"][0]["nodes"]],
            ["Doc A", "Doc B", "Doc C"],
        )
        self.assertTrue(
            all(edge["provenance"] == "explicit" for edge in response.data["paths"][0]["edges"])
        )

    def test_link_evidence_returns_anchor_and_source_version(self):
        response = self.api_client().get(
            f"/api/v1/documents/graph/evidence/link:{self.link_ab.id}/"
        )

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual(response.data["kind"], "links_to")
        self.assertEqual(response.data["anchor_text"], "to B")
        self.assertEqual(response.data["source"]["version"], 1)
        self.assertEqual(response.data["source"]["resource_id"], str(self.doc_a.id))

    def test_taxonomy_and_similarity_evidence_are_explainable(self):
        graph = self.query(edge_kinds=["tagged_with", "similar_to"])
        refs = {edge["kind"]: edge["evidence"]["ref"] for edge in graph.data["edges"]}

        taxonomy = self.api_client().get(
            f"/api/v1/documents/graph/evidence/{refs['tagged_with']}/"
        )
        similarity = self.api_client().get(
            f"/api/v1/documents/graph/evidence/{refs['similar_to']}/"
        )

        self.assertEqual(taxonomy.status_code, 200, getattr(taxonomy, "data", None))
        self.assertEqual(taxonomy.data["term"]["code"], "audit")
        self.assertEqual(similarity.status_code, 200, getattr(similarity, "data", None))
        self.assertEqual(similarity.data["score"], 0.91)
        self.assertTrue(similarity.data["algorithm_version"])
        self.assertTrue(similarity.data["model_version"])

    def test_scene_visibility_is_reprojected_for_the_current_user(self):
        owner_client = APIClient()
        owner_client.force_authenticate(user=self.owner)
        owner_client.credentials(HTTP_X_SPACE_ID=str(self.space.id))
        private = owner_client.post(
            "/api/v1/documents/graph/scenes/",
            {
                "name": "Private investigation",
                "visibility": "private",
                "canonical_query": {"schema_version": "graph.query.v1", "scope": {"mode": "global"}},
                "layout": {"viewport": {"x": 0, "y": 0, "ratio": 1}},
            },
            format="json",
        )
        shared = owner_client.post(
            "/api/v1/documents/graph/scenes/",
            {
                "name": "Shared investigation",
                "visibility": "workspace",
                "canonical_query": {"schema_version": "graph.query.v1", "scope": {"mode": "global"}},
                "layout": {},
            },
            format="json",
        )

        self.assertEqual(private.status_code, 201, getattr(private, "data", None))
        self.assertEqual(shared.status_code, 201, getattr(shared, "data", None))
        listing = self.api_client().get("/api/v1/documents/graph/scenes/")
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual([scene["name"] for scene in listing.data["results"]], ["Shared investigation"])
        hidden = self.api_client().get(
            f"/api/v1/documents/graph/scenes/{private.data['id']}/"
        )
        self.assertEqual(hidden.status_code, 404)

    def test_graph_mutation_invalidates_continuation_cursor(self):
        first = self.query(limits={"nodes": 2, "edges": 10})
        self.assertEqual(first.status_code, 200, first.data)
        cursor = first.data["meta"]["continuations"]["nodes"]
        Document.objects.create(
            title="New mutation",
            text_content="new",
            file_type="md",
            file_size=0,
            space=self.space,
            uploaded_by=self.owner,
            status="active",
        )

        stale = self.query(limits={"nodes": 2, "edges": 10}, cursor=cursor)

        self.assertEqual(stale.status_code, 409, stale.data)
        self.assertEqual(stale.data["code"], "graph_cursor_stale")

    def test_expand_uses_the_same_filtered_local_graph_contract(self):
        response = self.api_client().post(
            "/api/v1/documents/graph/expand/",
            {
                "schema_version": "graph.expand.v1",
                "center_id": str(self.doc_a.id),
                "depth": 2,
                "direction": "out",
                "edge_kinds": ["links_to"],
                "limit": 25,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual(
            {node["label"] for node in response.data["nodes"]},
            {"Doc A", "Doc B", "Doc C"},
        )

    def test_workspace_scene_can_be_resolved_and_copied_privately(self):
        owner_client = APIClient()
        owner_client.force_authenticate(user=self.owner)
        owner_client.credentials(HTTP_X_SPACE_ID=str(self.space.id))
        created = owner_client.post(
            "/api/v1/documents/graph/scenes/",
            {
                "name": "Team scene",
                "visibility": "workspace",
                "canonical_query": {
                    "schema_version": "graph.query.v1",
                    "scope": {"mode": "global"},
                    "edge_kinds": ["links_to"],
                },
                "layout": {},
            },
            format="json",
        )
        scene_id = created.data["id"]

        resolved = self.api_client().post(
            f"/api/v1/documents/graph/scenes/{scene_id}/resolve/", {}, format="json"
        )
        copied = self.api_client().post(
            f"/api/v1/documents/graph/scenes/{scene_id}/copy/", {}, format="json"
        )

        self.assertEqual(resolved.status_code, 200, getattr(resolved, "data", None))
        self.assertEqual(resolved.data["scene"]["id"], scene_id)
        self.assertEqual(resolved.data["graph"]["schema_version"], "graph.response.v1")
        self.assertEqual(copied.status_code, 201, getattr(copied, "data", None))
        self.assertEqual(copied.data["visibility"], "private")
        self.assertEqual(copied.data["owner_id"], str(self.member.id))

    def test_scene_state_is_permission_reprojected_and_tracks_versions(self):
        created = self.api_client().post(
            "/api/v1/documents/graph/scenes/",
            {
                "name": "Sanitized scene",
                "visibility": "private",
                "canonical_query": {
                    "schema_version": "graph.query.v1",
                    "scope": {"mode": "global"},
                    "edge_kinds": ["links_to"],
                },
                "layout": {
                    "positions": {
                        f"doc:{self.doc_a.lineage_id}": {"x": 1, "y": 2},
                        "doc:forged-secret": {"x": 9, "y": 9},
                    },
                    "hidden_node_ids": ["doc:forged-secret"],
                },
                "resolved_versions": {"doc:forged-secret": 999},
            },
            format="json",
        )

        self.assertEqual(created.status_code, 201, getattr(created, "data", None))
        self.assertNotIn("doc:forged-secret", created.data["layout"]["positions"])
        self.assertNotIn("doc:forged-secret", created.data["resolved_versions"])
        a_id = f"doc:{self.doc_a.lineage_id}"
        self.assertEqual(created.data["resolved_versions"][a_id], 1)

        self.doc_a.version = 2
        self.doc_a.save(update_fields=["version"])
        resolved = self.api_client().post(
            f"/api/v1/documents/graph/scenes/{created.data['id']}/resolve/",
            {},
            format="json",
        )

        self.assertEqual(resolved.status_code, 200, getattr(resolved, "data", None))
        self.assertIn(a_id, resolved.data["changes"]["version_changed"])

    def test_repeated_wikilinks_keep_each_source_occurrence_as_evidence(self):
        owner_client = APIClient()
        owner_client.force_authenticate(user=self.owner)
        owner_client.credentials(HTTP_X_SPACE_ID=str(self.space.id))
        edited = owner_client.patch(
            f"/api/v1/documents/{self.doc_d.id}/text/",
            {"text_content": "# Sources\nSee [[Doc A]] and [[Doc A|primary source]]."},
            format="json",
        )
        self.assertEqual(edited.status_code, 200, edited.data)

        graph = self.query()
        doc_d_id = next(node["id"] for node in graph.data["nodes"] if node["label"] == "Doc D")
        doc_a_id = next(node["id"] for node in graph.data["nodes"] if node["label"] == "Doc A")
        edge = next(
            edge
            for edge in graph.data["edges"]
            if edge["source"] == doc_d_id and edge["target"] == doc_a_id
        )
        evidence = self.api_client().get(
            f"/api/v1/documents/graph/evidence/{edge['evidence']['ref']}/"
        )

        self.assertEqual(edge["evidence"]["count"], 2)
        self.assertEqual(len(evidence.data["occurrences"]), 2)
        self.assertEqual(evidence.data["occurrences"][1]["anchor_text"], "primary source")
        self.assertEqual(evidence.data["occurrences"][1]["heading_path"], ["Sources"])
