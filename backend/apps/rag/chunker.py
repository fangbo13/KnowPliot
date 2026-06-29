# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Document chunking using LangChain."""

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
