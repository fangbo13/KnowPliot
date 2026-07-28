# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""KB/RAG audit spec P2/P3 — contract tests.

P2: library routing, structure-aware chunking, synonym expansion,
optional LLM rerank, auto knowledge-gap tickets.
P3: unresolved links, rename propagation, cross-library links,
link-suggest endpoint, superseded-chunk purge.
"""

from datetime import timedelta
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.knowledge.links import (
    propagate_title_rename,
    resolve_unresolved_links_to,
    sync_document_links,
)
from apps.knowledge.models import (
    Document,
    DocumentChunk,
    DocumentLink,
    ReferenceLibrary,
    SpaceLibraryReference,
    TaxonomyDimension,
    TaxonomyTerm,
)
from apps.knowledge.tasks import purge_superseded_chunks
from apps.spaces.models import Organization, SpaceMembership
from apps.spaces.test_utils import create_test_space
from apps.rag.chunker import LangChainChunker
from apps.rag.library_routing import route_reference_libraries
from apps.rag.llm_rerank import _parse_order, llm_rerank
from apps.rag.query_understanding import analyze_query

User = get_user_model()


def make_doc(space, user, title, *, status="active", text_content=""):
    return Document.objects.create(
        space=space,
        uploaded_by=user,
        title=title,
        file=f"documents/{title}.txt",
        file_type="txt",
        file_size=10,
        status=status,
        text_content=text_content,
    )


class LibraryRoutingTest(TestCase):
    """P2 §A1: libraries are searched only when the query signals them."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p2route", email="p2route@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P2 Route", slug="p2-route")
        cls.space = create_test_space(
            organization=cls.org, name="Primary", code="p2-primary"
        )
        cls.lib_space = create_test_space(
            organization=cls.org, name="IFRS Lib", code="p2-ifrs"
        )
        cls.library = ReferenceLibrary.objects.create(
            space=cls.lib_space,
            name="IFRS Reference",
            category="ifrs",
            status=ReferenceLibrary.STATUS_PUBLISHED,
        )
        SpaceLibraryReference.objects.create(
            space=cls.space, library=cls.library, enabled=True
        )

    def test_category_keyword_routes_the_library(self):
        space_ids, names = route_reference_libraries("IFRS 15 收入确认五步法", self.space)
        self.assertEqual(space_ids, [str(self.lib_space.id)])
        self.assertEqual(names[str(self.lib_space.id)], "IFRS Reference")

    def test_unrelated_query_stays_in_primary_space(self):
        space_ids, _ = route_reference_libraries("我们组的底稿放在哪里", self.space)
        self.assertEqual(space_ids, [])

    def test_library_name_mention_routes_it(self):
        space_ids, _ = route_reference_libraries("查一下 ifrs reference 里的资料", self.space)
        self.assertEqual(space_ids, [str(self.lib_space.id)])

    @override_settings(RAG_LIBRARY_ROUTING_ENABLED=False)
    def test_escape_hatch_restores_full_fanout(self):
        space_ids, _ = route_reference_libraries("完全无关的问题", self.space)
        self.assertEqual(space_ids, [str(self.lib_space.id)])


class MarkdownChunkingTest(TestCase):
    """P2 §A7: heading-aware chunks carry the section path."""

    def test_sections_carry_heading_path(self):
        chunker = LangChainChunker(chunk_size=200, chunk_overlap=0)
        text = (
            "# 收入准则\n正文A\n\n## 五步法\n正文B\n\n### 识别合同\n正文C\n\n"
            "## 披露\n正文D\n"
        )
        chunks = chunker.split_markdown(text)
        sections = [c["metadata"].get("section") for c in chunks]
        self.assertIn("收入准则", sections)
        self.assertIn("收入准则 > 五步法", sections)
        self.assertIn("收入准则 > 五步法 > 识别合同", sections)
        self.assertIn("收入准则 > 披露", sections)

    def test_plain_text_falls_back_without_sections(self):
        chunker = LangChainChunker(chunk_size=200, chunk_overlap=0)
        chunks = chunker.split_markdown("没有任何标题的纯文本内容。")
        self.assertTrue(chunks)
        self.assertNotIn("section", chunks[0]["metadata"])


class SynonymExpansionTest(TestCase):
    """P2 §A4: controlled synonyms match and expand the query."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p2syn", email="p2syn@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P2 Syn", slug="p2-syn")
        cls.space = create_test_space(
            organization=cls.org, name="Syn Space", code="p2-syn"
        )
        dimension = TaxonomyDimension.objects.create(
            organization=cls.org, code="account", name="科目"
        )
        TaxonomyTerm.objects.create(
            dimension=dimension,
            code="bad-debt",
            label="坏账准备",
            synonyms=["信用减值损失", "呆账准备"],
        )

    def test_synonym_matches_and_expands(self):
        signals = analyze_query("信用减值损失如何计提", space_id=str(self.space.id))
        self.assertIn("bad-debt", signals.term_codes)
        self.assertIn("坏账准备", signals.expansion_terms)
        self.assertIn("信用减值损失", signals.expansion_terms)


class LlmRerankTest(TestCase):
    """P2 §A8: best-effort rerank — parse, reorder, degrade safely."""

    def rows(self):
        return [
            {"id": "a", "content": "alpha"},
            {"id": "b", "content": "beta"},
            {"id": "c", "content": "gamma"},
        ]

    def test_parse_order_completes_missing_indices(self):
        self.assertEqual(_parse_order("2, 0", 3), [2, 0, 1])
        self.assertIsNone(_parse_order("no digits", 3))

    def test_rerank_reorders_by_llm_output(self):
        llm = Mock()
        llm.stream_chat.return_value = iter(["2,", "0,", "1"])
        ordered = llm_rerank("q", self.rows(), llm)
        self.assertEqual([r["id"] for r in ordered], ["c", "a", "b"])

    def test_rerank_failure_keeps_original_order(self):
        llm = Mock()
        llm.stream_chat.side_effect = RuntimeError("down")
        ordered = llm_rerank("q", self.rows(), llm)
        self.assertEqual([r["id"] for r in ordered], ["a", "b", "c"])


class AutoKnowledgeGapTest(TestCase):
    """P2 §B3: insufficient answers open an idempotent gap ticket."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p2gap", email="p2gap@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P2 Gap", slug="p2-gap")
        cls.space = create_test_space(
            organization=cls.org, name="Gap Space", code="p2-gap"
        )

    def _turn(self, question):
        turn = Mock()
        turn.space_id = self.space.id
        turn.space = self.space
        turn.user = self.user
        turn.question_message = Mock()
        turn.question_message.content = question
        return turn

    def test_insufficient_answer_creates_ticket_once(self):
        from apps.chat.generation import _maybe_open_knowledge_gap
        from apps.chat.models import KnowledgeGapTicket

        message = Mock()
        message.confidence_label = "insufficient"

        _maybe_open_knowledge_gap(self._turn("量子预算是多少？"), message)
        _maybe_open_knowledge_gap(self._turn("量子预算是多少？"), message)

        tickets = KnowledgeGapTicket.objects.filter(space=self.space)
        self.assertEqual(tickets.count(), 1)
        self.assertIn("auto-created", tickets.first().suggested_source)

    def test_confident_answer_creates_nothing(self):
        from apps.chat.generation import _maybe_open_knowledge_gap
        from apps.chat.models import KnowledgeGapTicket

        message = Mock()
        message.confidence_label = "high"
        _maybe_open_knowledge_gap(self._turn("正常问题"), message)
        self.assertFalse(KnowledgeGapTicket.objects.filter(space=self.space).exists())


class ObsidianLinksTest(TestCase):
    """P3 §B1: unresolved links, auto-resolution, rename propagation, cross-lib."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p3links", email="p3links@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P3 Links", slug="p3-links")
        cls.space = create_test_space(
            organization=cls.org, name="Links Space", code="p3-links"
        )
        cls.lib_space = create_test_space(
            organization=cls.org, name="Lib Space", code="p3-lib"
        )
        library = ReferenceLibrary.objects.create(
            space=cls.lib_space,
            name="Standards Lib",
            category="ifrs",
            status=ReferenceLibrary.STATUS_PUBLISHED,
        )
        SpaceLibraryReference.objects.create(
            space=cls.space, library=library, enabled=True
        )

    def test_unresolved_wikilink_is_recorded_and_resolves_on_creation(self):
        source = make_doc(
            self.space, self.user, "source-doc",
            text_content="见 [[尚不存在的文档]] 说明。",
        )
        sync_document_links(source)
        unresolved = DocumentLink.objects.get(source=source, target__isnull=True)
        self.assertEqual(unresolved.unresolved_title, "尚不存在的文档")

        # Creating the document resolves the gray link.
        target = make_doc(self.space, self.user, "尚不存在的文档")
        resolve_unresolved_links_to(target)
        link = DocumentLink.objects.get(source=source)
        self.assertEqual(link.target_id, target.id)

    def test_rename_propagates_into_referencing_documents(self):
        target = make_doc(self.space, self.user, "旧标题")
        referer = make_doc(
            self.space, self.user, "引用方",
            text_content="参见 [[旧标题]] 与 [[旧标题|别名]]。",
        )
        sync_document_links(referer)

        target.title = "新标题"
        target.save(update_fields=["title"])
        updated = propagate_title_rename(target, "旧标题", "新标题")

        referer.refresh_from_db()
        self.assertEqual(updated, 1)
        self.assertIn("[[新标题]]", referer.text_content)
        self.assertIn("[[新标题|别名]]", referer.text_content)
        self.assertNotIn("旧标题", referer.text_content)

    def test_wikilink_resolves_into_enabled_library(self):
        lib_doc = make_doc(self.lib_space, self.user, "IFRS 9 金融工具")
        source = make_doc(
            self.space, self.user, "本地文档",
            text_content="依据 [[IFRS 9 金融工具]] 处理。",
        )
        sync_document_links(source)
        link = DocumentLink.objects.get(source=source)
        self.assertEqual(link.target_id, lib_doc.id)


class LinkSuggestApiTest(APITestCase):
    """P3 §B1: autocomplete endpoint spans space + enabled libraries."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p3suggest", email="p3suggest@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P3 Suggest", slug="p3-suggest")
        cls.space = create_test_space(
            organization=cls.org, name="Suggest Space", code="p3-suggest"
        )
        SpaceMembership.objects.create(
            user=cls.user, space=cls.space, role=SpaceMembership.ROLE_MEMBER
        )
        make_doc(cls.space, cls.user, "应收账款分析")
        make_doc(cls.space, cls.user, "收入循环底稿")

    def test_suggestions_filter_by_query(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(
            "/api/v1/documents/link-suggest/",
            {"q": "应收"},
            HTTP_X_SPACE_ID=str(self.space.id),
        )
        self.assertEqual(response.status_code, 200)
        titles = [s["title"] for s in response.data["suggestions"]]
        self.assertEqual(titles, ["应收账款分析"])


class SupersededChunkPurgeTest(TestCase):
    """P3 §B4: chunks of long-superseded versions are reclaimed."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="p3purge", email="p3purge@example.com", password="test"
        )
        cls.org = Organization.objects.create(name="P3 Purge", slug="p3-purge")
        cls.space = create_test_space(
            organization=cls.org, name="Purge Space", code="p3-purge"
        )

    def _doc_with_chunk(self, title, status):
        doc = make_doc(self.space, self.user, title, status=status)
        DocumentChunk.objects.create(
            document=doc, space=self.space, content="x", chunk_index=0
        )
        return doc

    def test_old_superseded_chunks_deleted_recent_kept(self):
        old_doc = self._doc_with_chunk("old-superseded", "superseded")
        recent_doc = self._doc_with_chunk("recent-superseded", "superseded")
        active_doc = self._doc_with_chunk("still-active", "active")
        Document.objects.filter(pk=old_doc.pk).update(
            updated_at=timezone.now() - timedelta(days=90)
        )

        result = purge_superseded_chunks()

        self.assertEqual(result["chunks_deleted"], 1)
        self.assertFalse(DocumentChunk.objects.filter(document=old_doc).exists())
        self.assertTrue(DocumentChunk.objects.filter(document=recent_doc).exists())
        self.assertTrue(DocumentChunk.objects.filter(document=active_doc).exists())
