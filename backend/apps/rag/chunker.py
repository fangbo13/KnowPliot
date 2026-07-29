# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Document chunking using LangChain."""

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import CHUNK_SIZE, CHUNK_OVERLAP

# RAG optimization spec Phase 1: images are never ingested (user decision —
# no OCR); markdown image syntax and inline base64 blobs are replaced with a
# tiny placeholder so they cannot pollute chunks or embeddings.
IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
BASE64_BLOB_RE = re.compile(
    r"data:[A-Za-z0-9/+.-]+;base64,[A-Za-z0-9+/=\s]{80,}"
)
# A markdown pipe-table line: |...|
TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
# The header/data separator row: | --- | :---: | …
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")

# Oversized tables are split into row groups of at most this many characters,
# each group repeating the header rows so no data row loses its column names.
TABLE_GROUP_MAX_CHARS = 2000
# Preceding-paragraph anchor injected into table chunks (cross-element link).
TABLE_ANCHOR_MAX_CHARS = 200


def strip_images(text: str) -> str:
    """Replace markdown images / base64 blobs with a placeholder."""

    def _placeholder(match: re.Match) -> str:
        alt = (match.group(1) or "").strip()
        return f"[图片：{alt}]" if alt else "[图片：已省略]"

    cleaned = IMAGE_MD_RE.sub(_placeholder, text or "")
    return BASE64_BLOB_RE.sub("[图片数据已省略]", cleaned)


class LangChainChunker:
    """Splits documents into chunks using LangChain's RecursiveCharacterTextSplitter."""

    def __init__(self, chunk_size=None, chunk_overlap=None):
        self.chunk_size = chunk_size or CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or CHUNK_OVERLAP
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", "。", ".", " ", ""],
        )

    def split(self, text: str, metadata_list: list[dict] | None = None) -> list[dict]:
        """Split text into chunks.

        Args:
            text: The full document text.
            metadata_list: Optional metadata for each chunk position.

        Returns:
            List of dicts with 'text', 'metadata' keys.
        """
        docs = self.splitter.create_documents([strip_images(text)])
        chunks = []
        for i, doc in enumerate(docs):
            chunk_meta = metadata_list[i] if metadata_list and i < len(metadata_list) else {}
            chunks.append({
                "text": doc.page_content,
                "metadata": chunk_meta,
            })
        return chunks

    # ── KB/RAG audit spec P2 §A7: structure-aware Markdown chunking ──

    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def split_markdown(self, text: str) -> list[dict]:
        """Heading-aware split: sections first, size-based split within.

        Each chunk's metadata carries ``section`` — the heading path
        ("H1 > H2 > H3") — so citations can point at the exact section
        instead of only a page number. Falls back to the plain splitter
        when the text contains no Markdown headings.

        RAG optimization spec Phase 1: pipe tables are ATOMIC — never
        shredded by the size splitter. Oversized tables split into row
        groups that each repeat the header rows. Every table chunk gets a
        cross-element anchor (section path + the paragraph right before
        the table) so text↔table association survives chunking.
        """
        text = strip_images(text)
        lines = (text or "").splitlines()
        if not any(self.HEADING_RE.match(line) for line in lines):
            return self._split_body("", text)

        sections: list[tuple[str, str]] = []  # (heading path, body text)
        path: dict[int, str] = {}
        buffer: list[str] = []
        current_path = ""

        def flush():
            body = "\n".join(buffer).strip()
            if body:
                sections.append((current_path, body))
            buffer.clear()

        for line in lines:
            match = self.HEADING_RE.match(line)
            if match is None:
                buffer.append(line)
                continue
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            path[level] = title
            for deeper in [k for k in path if k > level]:
                del path[deeper]
            current_path = " > ".join(path[k] for k in sorted(path))
            # Keep the heading line inside its section body for context.
            buffer.append(line)
        flush()

        chunks: list[dict] = []
        for section_path, body in sections:
            chunks.extend(self._split_body(section_path, body))
        return chunks

    def _split_body(self, section_path: str, body: str) -> list[dict]:
        """Split one section body, keeping pipe tables atomic."""
        chunks: list[dict] = []
        base_meta = {"section": section_path} if section_path else {}
        last_paragraph = ""
        for kind, segment in _table_segments(body):
            if kind == "text":
                for doc in self.splitter.create_documents([segment]):
                    chunks.append({"text": doc.page_content, "metadata": dict(base_meta)})
                last_paragraph = _last_paragraph(segment)
                continue
            # Table segment: atomic chunk(s) with a cross-element anchor.
            anchor_lines = []
            if section_path:
                anchor_lines.append(f"【所属章节】{section_path}")
            if last_paragraph:
                anchor_lines.append(
                    f"【上文】{last_paragraph[:TABLE_ANCHOR_MAX_CHARS]}"
                )
            anchor = "\n".join(anchor_lines)
            for table_part in _split_table(segment):
                content = f"{anchor}\n{table_part}" if anchor else table_part
                chunks.append(
                    {
                        "text": content,
                        "metadata": {**base_meta, "element_type": "table"},
                    }
                )
        return chunks


def _table_segments(body: str):
    """Yield ('text'|'table', segment) runs; a table is ≥2 pipe lines."""
    lines = (body or "").splitlines()
    plain: list[str] = []
    index = 0
    while index < len(lines):
        if TABLE_LINE_RE.match(lines[index]):
            table_lines = []
            while index < len(lines) and TABLE_LINE_RE.match(lines[index]):
                table_lines.append(lines[index])
                index += 1
            if len(table_lines) >= 2:
                text_block = "\n".join(plain).strip()
                if text_block:
                    yield "text", text_block
                plain = []
                yield "table", "\n".join(table_lines)
            else:
                plain.extend(table_lines)
            continue
        plain.append(lines[index])
        index += 1
    text_block = "\n".join(plain).strip()
    if text_block:
        yield "text", text_block


def _last_paragraph(text: str) -> str:
    """Last non-empty paragraph of a text block (single-line normalized)."""
    for paragraph in reversed(re.split(r"\n\s*\n", text or "")):
        cleaned = " ".join(paragraph.split())
        if cleaned:
            return cleaned
    return ""


def _split_table(table_text: str) -> list[str]:
    """Return the table whole, or header-repeating row groups when huge."""
    if len(table_text) <= TABLE_GROUP_MAX_CHARS:
        return [table_text]
    lines = table_text.splitlines()
    header: list[str] = [lines[0]]
    data_start = 1
    if len(lines) > 1 and TABLE_SEPARATOR_RE.match(lines[1]):
        header.append(lines[1])
        data_start = 2
    header_text = "\n".join(header)
    groups: list[str] = []
    current: list[str] = []
    current_len = len(header_text)
    for row in lines[data_start:]:
        if current and current_len + len(row) + 1 > TABLE_GROUP_MAX_CHARS:
            groups.append("\n".join([header_text, *current]))
            current = []
            current_len = len(header_text)
        current.append(row)
        current_len += len(row) + 1
    if current:
        groups.append("\n".join([header_text, *current]))
    return groups or [table_text]


def chunk_document_text(
    chunker: LangChainChunker,
    raw_text: str,
    file_type: str,
    *,
    parsed_as_markdown: bool = False,
    page_metadata: list[dict] | None = None,
) -> list[dict]:
    """Single chunk-path decision shared by ingestion and the eval seeder.

    RAG optimization spec Phase 1: Docling emits Markdown for PDF/DOCX, so
    those documents now take the structure-aware path too (headings,
    atomic tables, cross-element anchors). Only non-markdown fallbacks
    (Unstructured / plain-text reads) keep the plain size splitter.
    """
    if parsed_as_markdown or (file_type or "").lower() in ("md", "markdown"):
        return chunker.split_markdown(raw_text)
    return chunker.split(raw_text, page_metadata)
