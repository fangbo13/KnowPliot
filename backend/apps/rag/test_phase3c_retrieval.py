"""Phase 3C retrieval-safety regression tests."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.knowledge.models import Document, DocumentChunk
from apps.rag.retriever import PgVectorRetriever
from apps.spaces.models import KnowledgeSpace, Organization


User = get_user_model()


class RetrievalSafetyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="retrieval-owner",
            email="retrieval@example.com",
            password="test",
        )
        cls.org = Organization.objects.create(name="Retrieval Org", slug="retrieval-org")
        cls.space_a = KnowledgeSpace.objects.create(
            organization=cls.org,
            name="Retrieval A",
            code="retrieval-a",
        )
        cls.space_b = KnowledgeSpace.objects.create(
            organization=cls.org,
            name="Retrieval B",
            code="retrieval-b",
        )

    def make_chunk(self, *, space, title, status="active", category=None):
        document = Document.objects.create(
            space=space,
            uploaded_by=self.user,
            title=title,
            file=f"documents/{title}.txt",
            file_type="txt",
            file_size=10,
            status=status,
            category=category,
        )
        return DocumentChunk.objects.create(
            space=space,
            document=document,
            content=f"{title} content",
            chunk_index=0,
            embedding=[1.0, 1.0],
        )

    def search(self, **kwargs):
        with patch("apps.rag.retriever.EmbeddingService") as embedder:
            embedder.return_value.embed.return_value = [1.0, 1.0]
            return PgVectorRetriever().search(
                "policy",
                space_id=str(self.space_a.id),
                top_k=20,
                similarity_threshold=0.1,
                **kwargs,
            )

    def test_space_id_is_required(self):
        with self.assertRaisesRegex(ValueError, "space_id"):
            PgVectorRetriever().search("policy", space_id=None)

    def test_blank_and_invalid_space_ids_are_rejected(self):
        for value in ("", "not-a-uuid"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "space_id"):
                    PgVectorRetriever().search("policy", space_id=value)

    def test_sqlite_returns_only_active_documents_in_requested_space(self):
        expected = self.make_chunk(space=self.space_a, title="active-a")
        self.make_chunk(space=self.space_b, title="active-b")
        for status in ("draft", "processing", "expired", "stale", "archived", "failed"):
            self.make_chunk(space=self.space_a, title=f"{status}-a", status=status)

        results = self.search()

        self.assertEqual([row["id"] for row in results], [str(expected.id)])

    def test_unknown_and_orm_traversal_filter_keys_are_rejected(self):
        for filters in (
            {"document__status": "failed"},
            {"space_id": str(self.space_b.id)},
            {"content__icontains": "secret"},
        ):
            with self.subTest(filters=filters):
                with self.assertRaisesRegex(ValueError, "filter"):
                    self.search(filters=filters)

    def test_document_and_category_filters_validate_uuid_values(self):
        from apps.rag.retriever import RetrievalFilters

        for filters in (
            RetrievalFilters(document_ids=("bad-id",)),
            RetrievalFilters(category_ids=("bad-id",)),
        ):
            with self.subTest(filters=filters):
                with self.assertRaisesRegex(ValueError, "UUID"):
                    self.search(filters=filters)

    def test_postgres_query_uses_mapped_columns_and_parameter_values(self):
        from apps.rag.retriever import RetrievalFilters

        cursor = MagicMock()
        cursor.fetchall.return_value = []
        context = MagicMock()
        context.__enter__.return_value = cursor
        context.__exit__.return_value = False

        with (
            patch.dict(
                settings.DATABASES["default"],
                {"ENGINE": "django.db.backends.postgresql"},
            ),
            patch("apps.rag.retriever.EmbeddingService") as embedder,
            patch("apps.rag.retriever.connection.cursor", return_value=context),
        ):
            embedder.return_value.embed.return_value = [1.0, 1.0]
            PgVectorRetriever().search(
                "policy",
                space_id=str(self.space_a.id),
                filters=RetrievalFilters(
                    document_ids=(str(uuid4()),),
                    category_ids=(str(uuid4()),),
                ),
            )

        sql, params = cursor.execute.call_args.args
        self.assertIn("dc.space_id = %s", sql)
        self.assertIn("d.status = %s", sql)
        self.assertIn("dc.document_id IN (%s)", sql)
        self.assertIn("d.category_id IN (%s)", sql)
        self.assertNotIn(str(self.space_a.id), sql)
        self.assertIn(str(self.space_a.id), params)
        self.assertIn("active", params)
