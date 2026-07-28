# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Document chunking using LangChain."""

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import CHUNK_SIZE, CHUNK_OVERLAP


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
        docs = self.splitter.create_documents([text])
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
        """
        lines = (text or "").splitlines()
        if not any(self.HEADING_RE.match(line) for line in lines):
            return self.split(text)

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
            for doc in self.splitter.create_documents([body]):
                metadata = {"section": section_path} if section_path else {}
                chunks.append({"text": doc.page_content, "metadata": metadata})
        return chunks
