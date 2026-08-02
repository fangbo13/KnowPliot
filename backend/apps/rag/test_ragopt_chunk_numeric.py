"""Unit tests for RAG optimization spec Phase 1/2 (chunking + tokenization)."""

from django.test import SimpleTestCase

from apps.rag.chunker import LangChainChunker, strip_images
from apps.rag.cjk import cjk_tokens
from apps.rag.hybrid import _numeric_query_tokens, _tokens


TABLE_DOC = (
    "# 轴承装配工艺规范\n\n"
    "## 关键参数表\n\n"
    "下表给出关键尺寸参数。\n\n"
    "| 代号 | 参数名称 | 标准值 | 公差 |\n"
    "| --- | --- | --- | --- |\n"
    "| D1 | 轴承内径 | 40mm | ±0.05mm |\n"
    "| D2 | 轴承外径 | 80mm | ±0.02mm |\n"
    "| C1 | 径向游隙 | 0.012mm | +0.008mm |\n\n"
    "## 运转测试\n\n"
    "噪声不得超过65dB。\n"
)


class TableAtomicityTest(SimpleTestCase):
    def setUp(self):
        self.chunker = LangChainChunker()

    def test_pipe_table_stays_in_one_chunk(self):
        chunks = self.chunker.split_markdown(TABLE_DOC)
        table_chunks = [c for c in chunks if c["metadata"].get("element_type") == "table"]
        self.assertTrue(table_chunks, "a table chunk should exist")
        table = table_chunks[0]["text"]
        # Every data row co-locates with the header inside ONE chunk.
        for token in ("D1", "D2", "C1", "±0.05mm", "0.012mm"):
            self.assertIn(token, table)

    def test_table_chunk_carries_cross_element_anchor(self):
        chunks = self.chunker.split_markdown(TABLE_DOC)
        table = next(c for c in chunks if c["metadata"].get("element_type") == "table")
        # Section path + preceding paragraph rebuild the text↔table link.
        self.assertIn("【所属章节】", table["text"])
        self.assertIn("关键参数表", table["text"])
        self.assertIn("【上文】", table["text"])

    def test_oversized_table_repeats_header_per_group(self):
        header = "| 编号 | 名称 | 值 |\n| --- | --- | --- |\n"
        rows = "".join(f"| P{i} | 部件{i} | {i}mm |\n" for i in range(200))
        doc = f"## 大表\n\n{header}{rows}"
        chunks = self.chunker.split_markdown(doc)
        table_chunks = [c for c in chunks if c["metadata"].get("element_type") == "table"]
        self.assertGreater(len(table_chunks), 1, "huge table should split into groups")
        for chunk in table_chunks:
            self.assertIn("| 编号 | 名称 | 值 |", chunk["text"])


class ImageStripTest(SimpleTestCase):
    def test_markdown_image_replaced_with_placeholder(self):
        out = strip_images("见下图 ![装配示意图](media/a.png) 完成。")
        self.assertNotIn("media/a.png", out)
        self.assertIn("[图片：装配示意图]", out)

    def test_base64_blob_stripped(self):
        blob = "data:image/png;base64," + "A" * 200
        out = strip_images(f"图: {blob} 结束")
        self.assertNotIn("AAAA", out)
        self.assertIn("[图片数据已省略]", out)


class NumericTokenTest(SimpleTestCase):
    def test_tolerance_tokens_survive_tokenization(self):
        tokens = _tokens("轴承内径公差是±0.05mm还是0.1mm")
        self.assertIn("±0.05mm", tokens)
        self.assertIn("0.1mm", tokens)

    def test_percentage_and_unit_tokens_survive(self):
        tokens = _tokens("余高5.2% 扭矩25n·m 粗糙度1.6μm")
        self.assertIn("5.2%", tokens)
        self.assertIn("1.6μm", tokens)

    def test_numeric_query_tokens_exclude_plain_integers(self):
        numerics = _numeric_query_tokens("在20℃下公差±0.05mm，样本30个")
        self.assertIn("±0.05mm", numerics)
        self.assertIn("20℃", numerics)
        # A bare integer like the sample count is not a boosted numeric token.
        self.assertNotIn("30", numerics)

    def test_cjk_tokens_keep_numeric_units(self):
        tokens = cjk_tokens("公差±0.05mm")
        self.assertIn("±0.05mm", tokens)
