# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""RAG Pipeline - Main orchestrator.

V4.2 SYS-V4.2-014: Added DashScope circuit breaker protection.
When DashScope API fails 3 times consecutively, the circuit opens
and returns a degraded response for 30 seconds (half-open recovery).
This prevents external API failures from blocking the entire server.

V4.2 KB-V4.2-BATCH-006: Added extracted text size limit + chunk count limit.
V4.2 KB-V4.2-BATCH-009: Added metadata sanitization via bleach.
"""

import logging
import time

from django.conf import settings

from .chunker import LangChainChunker
from .embedding import EmbeddingService
from .retriever import PgVectorRetriever
from .prompt_builder import PromptBuilder
from .guardrails import GuardrailsService, LiteLLMChatService
from .config import CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, SIMILARITY_THRESHOLD
from apps.core.circuit_breaker import dashscope_breaker  # V4.2 SYS-V4.2-014
from apps.knowledge.batch import sanitize_metadata, is_zero_vector  # V4.2 BATCH-009/012

logger = logging.getLogger(__name__)


class RAGPipeline:
    """Orchestrates the full RAG lifecycle: ingest, retrieve, generate."""

    def __init__(self):
        self.parser = DocumentParser()
        self.chunker = LangChainChunker(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        self.embedder = EmbeddingService()
        self.retriever = PgVectorRetriever()
        self.prompt_builder = PromptBuilder()
        self.guardrails = GuardrailsService()
        self.llm = LiteLLMChatService()
        self.model_name = settings.RAG_LLM_MODEL

    def ingest(self, document) -> list:
        """Parse, chunk, embed, and store a document.

        V4.2 KB-V4.2-BATCH-006: Added extracted text size limit.
        V4.2 KB-V4.2-BATCH-009: Added metadata sanitization via bleach.
        V4.2 KB-V4.2-BATCH-012: Zero-vector detection + failure marking.

        Args:
            document: Django Document model instance.

        Returns:
            List of created DocumentChunk instances.
        """
        from apps.knowledge.models import DocumentChunk

        # Parse document
        raw_text, page_metadata = self.parser.parse(document.file.path, document.file_type)

        # V4.2 KB-V4.2-BATCH-006: Extracted text size limit
        max_text_size = getattr(settings, "MAX_EXTRACTED_TEXT_SIZE", 10_000_000)
        if len(raw_text) > max_text_size:
            logger.warning(
                f"[BATCH-006] Extracted text from '{document.title}' is "
                f"{len(raw_text)} bytes — exceeds limit of {max_text_size} bytes. "
                f"Truncating to limit."
            )
            raw_text = raw_text[:max_text_size]
            document.processing_error = "Extracted text exceeds size limit — truncated."
            document.save(update_fields=["processing_error"])

        # Chunk
        chunks = self.chunker.split(raw_text, page_metadata)

        # V4.2 KB-V4.2-BATCH-006: Chunk count limit per document
        max_chunks = getattr(settings, "MAX_CHUNKS_PER_DOCUMENT", 500)
        if len(chunks) > max_chunks:
            logger.warning(
                f"[BATCH-006] Document '{document.title}' produces {len(chunks)} chunks — "
                f"exceeds limit of {max_chunks}. Truncating."
            )
            chunks = chunks[:max_chunks]
            document.processing_error = (
                f"Document produces too many chunks ({len(chunks)}) — truncated to {max_chunks}."
            )
            document.save(update_fields=["processing_error"])

        # Embed in batches
        texts = [c["text"] for c in chunks]
        embeddings = self.embedder.embed_batch(texts)

        # V4.2 KB-V4.2-BATCH-012: Zero-vector detection
        # Count how many embeddings are zero vectors (failed)
        zero_vector_count = sum(1 for emb in embeddings if is_zero_vector(emb))

        # If >50% of embeddings are zero vectors, mark document as failed
        if zero_vector_count > len(embeddings) * 0.5 and len(embeddings) > 0:
            document.status = "failed"
            document.processing_error = (
                f"Embedding failure: {zero_vector_count}/{len(embeddings)} chunks "
                f"returned zero vectors (>50%). Document may not be searchable."
            )
            document.save(update_fields=["status", "processing_error"])
            logger.error(
                f"[BATCH-012] Document '{document.title}' has {zero_vector_count} zero vectors "
                f"out of {len(embeddings)} — marked as failed."
            )
            # Still create chunks but mark them with metadata
            for chunk, embedding in zip(chunks, embeddings):
                chunk["metadata"]["embedding_failed"] = is_zero_vector(embedding)
            # Return early — don't store these chunks as they're unusable
            return []

        # Store chunks with sanitized metadata
        document_chunks = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # V4.2 KB-V4.2-BATCH-009: Sanitize metadata before storing
            raw_metadata = chunk.get("metadata", {})
            clean_metadata = sanitize_metadata(raw_metadata)

            # V4.2 KB-V4.2-BATCH-012: Mark individual failed embeddings
            if is_zero_vector(embedding):
                clean_metadata["embedding_failed"] = True
                logger.warning(
                    f"[BATCH-012] Chunk {i} of '{document.title}' has zero vector — marked."
                )

            doc_chunk = DocumentChunk.objects.create(
                document=document,
                # V6.0: denormalize the document's space onto the chunk so the
                # retriever can filter by space_id directly (isolation).
                space_id=document.space_id,
                content=chunk["text"],
                chunk_index=i,
                page_number=clean_metadata.get("page"),
                metadata=clean_metadata,
                embedding=embedding,
            )
            # V4.3 UAT FIX: Sync JSON embedding to pgvector embedding_vector column.
            # The ingest creates chunks with the JSON embedding field, but the retriever's
            # _search_pgvector() queries the embedding_vector (VectorField) column which
            # has an HNSW index. Without this sync, newly ingested chunks are invisible
            # to the retriever — it returns 0 results even when chunks exist.
            # Migration 0004 handles existing data, but new ingests need this immediate sync.
            if embedding and not is_zero_vector(embedding):
                from django.db import connection
                with connection.cursor() as cursor:
                    vector_str = '[' + ','.join(str(v) for v in embedding) + ']'
                    cursor.execute(
                        "UPDATE knowledge_documentchunk SET embedding_vector = %s::vector WHERE id = %s",
                        [vector_str, str(doc_chunk.id)]
                    )
            document_chunks.append(doc_chunk)

        logger.info(f"Ingested {len(document_chunks)} chunks from {document.title}")
        return document_chunks

    def retrieve_and_generate(
        self,
        query: str,
        user_profile,
        conversation_history: list,
        language: str = "en",
        space_id: str | None = None,
    ):
        """Full RAG: retrieve context, build prompt, call LLM, stream response.

        Args:
            space_id: V6.0 — restrict retrieval (and therefore citations) to the
                active knowledge space. When ``None`` no space filter is applied
                (used only by non-scoped callers / tests).

        Yields:
            Dicts with 'event' and 'data' keys for SSE streaming.
        """
        # Step 1: Guardrails - check for injection
        try:
            if not self.guardrails.check_input(query):
                yield {"event": "token", "data": {"token": self.guardrails.generate_fallback(language)}}
                yield {"event": "done", "data": {}}
                return
        except Exception as e:
            logger.error("Guardrails check error: %s", e, exc_info=True)
            # V4.3 UAT: If guardrails service fails, proceed anyway —
            # guardrails is a safety enhancement, not a hard gate.
            pass

        # Step 2: Retrieve relevant chunks
        # V4.3 UAT: Wrap retrieval in try/except — if retriever/embedding fails
        # (e.g., PgVector not configured, DashScope embedding API unavailable),
        # return graceful degraded response instead of uncaught exception that
        # causes SSE "error" event → frontend shows "当前无法获取响应".
        try:
            chunks = self.retriever.search(
                query=query,
                top_k=TOP_K,
                similarity_threshold=SIMILARITY_THRESHOLD,
                space_id=space_id,  # V6.0 space isolation
            )
        except Exception as e:
            logger.error("Retrieval error: %s", e, exc_info=True)
            dashscope_breaker.record_failure()  # Count as failure for circuit breaker
            degraded_msg = (
                "抱歉，知识检索服务暂时不可用，请稍后重试。" if language == "zh"
                else "Sorry, the knowledge retrieval service is temporarily unavailable. Please try again later."
            )
            yield {"event": "token", "data": {"token": degraded_msg}}
            yield {"event": "citations", "data": []}
            yield {"event": "done", "data": {}}
            return

        # V4.2 SYS-V4.2-014: Circuit breaker check — fail fast if DashScope is down
        if not dashscope_breaker.allow_request():
            degraded_msg = (
                "服务暂时不可用，请稍后重试。" if language == "zh"
                else "Service temporarily unavailable, please try again later."
            )
            logger.warning("DashScope circuit breaker OPEN — returning degraded response")
            yield {"event": "token", "data": {"token": degraded_msg}}
            yield {"event": "done", "data": {}}
            return
        # Prevents Prompt Injection via malicious content stored in knowledge chunks.
        # Each chunk's content is checked against guardrails; injection-pattern lines
        # are stripped to prevent the LLM from following embedded instructions.
        sanitized_chunks = []
        for chunk in chunks:
            content = chunk["content"]
            if not self.guardrails.check_input(content):
                content = self._sanitize_content(content)
            sanitized_chunks.append({**chunk, "content": content})
        chunks = sanitized_chunks

        # Step 2b: If no good results, return fallback
        if not chunks:
            fallback = (
                "我没有足够的信息来回答此问题，请联系您的人力资源伙伴或HR团队。"
                if language == "zh"
                else "I don't have enough information to answer this question. Please contact your HR buddy or HR team."
            )
            yield {"event": "token", "data": {"token": fallback}}
            yield {"event": "citations", "data": []}
            yield {"event": "done", "data": {}}
            return

        # Step 3: Build citations data
        citations = self._build_citations(chunks)
        yield {"event": "citations", "data": citations}

        # Step 4: Build system prompt
        # V4.3 UAT: Wrap prompt building in try/except — if prompt builder fails,
        # return graceful degraded response instead of uncaught exception.
        try:
            system_prompt = self.prompt_builder.build(
                context_chunks=chunks,
                conversation_history=conversation_history[-8:],  # Last 8 turns
                user_profile=user_profile,
                language=language,
            )
        except Exception as e:
            logger.error("Prompt builder error: %s", e, exc_info=True)
            dashscope_breaker.record_failure()
            degraded_msg = (
                "抱歉，系统暂时无法处理您的请求，请稍后重试。" if language == "zh"
                else "Sorry, the system is temporarily unable to process your request. Please try again later."
            )
            yield {"event": "token", "data": {"token": degraded_msg}}
            yield {"event": "citations", "data": citations}
            yield {"event": "done", "data": {}}
            return

        # Step 5: Stream LLM response — V4.2 SYS-V4.2-014: circuit breaker wraps the call
        # On success: record_success() closes the circuit.
        # On failure: record_failure() counts toward opening the circuit.
        llm_success = False
        try:
            for token in self.llm.stream_chat(system_prompt, query):
                llm_success = True  # At least one token received = API is working
                yield {"event": "token", "data": {"token": token}}
            # Full success — record it to close/reset the circuit breaker
            if llm_success:
                dashscope_breaker.record_success()
        except Exception as e:
            # V4.2 SYS-V4.2-014: Record failure to count toward circuit opening
            dashscope_breaker.record_failure()
            logger.error("DashScope stream error: %s", e, exc_info=True)
            degraded_msg = (
                "服务暂时不可用，请稍后重试。" if language == "zh"
                else "Service temporarily unavailable, please try again later."
            )
            yield {"event": "token", "data": {"token": degraded_msg}}

        yield {"event": "done", "data": {}}

    def _build_citations(self, chunks):
        """Build citation data from retrieved chunks."""
        return [
            {
                "document_id": chunk["document_id"],
                "document_title": chunk["document_title"],
                "page_number": chunk.get("page_number"),
                "score": round(chunk["score"], 3),
                "quoted_text": chunk["content"][:200],
                "chunk_id": chunk["id"],
            }
            for chunk in chunks
        ]

    def _sanitize_content(self, content: str) -> str:
        """Remove injection-pattern lines from retrieved content — V4.1 KB-V4.1-005.

        Checks each line individually against guardrails. Lines that trigger
        injection detection (system commands, role overrides, etc.) are stripped.
        If all lines are flagged, returns a truncated safe excerpt.
        """
        lines = content.split("\n")
        clean_lines = [line for line in lines if self.guardrails.check_input(line)]
        if clean_lines:
            return "\n".join(clean_lines)
        # Fallback: if every line was flagged, return truncated content
        return content[:200] + "..."


class DocumentParser:
    """Parse documents using Docling with Unstructured fallback."""

    def parse(self, file_path: str, file_type: str) -> tuple[str, list[dict]]:
        """Parse a document file.

        Args:
            file_path: Path to the document file.
            file_type: File type ('pdf', 'docx', 'html', 'txt').

        Returns:
            Tuple of (full_text, list_of_page_metadata).
        """
        try:
            return self._parse_with_docling(file_path)
        except Exception as e:
            logger.warning(f"Docling failed: {e}, falling back to Unstructured")
            try:
                return self._parse_with_unstructured(file_path)
            except Exception as e2:
                logger.error(f"Both parsers failed: {e2}")
                return self._parse_as_text(file_path)

    def _parse_with_docling(self, file_path: str) -> tuple[str, list[dict]]:
        """Parse using Docling (best for PDF/DOCX)."""
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(file_path)

        # Get markdown text
        text = result.document.export_to_markdown()

        # Extract page metadata if available
        metadata = [{"page": None}]
        try:
            pages = getattr(result.document, "pages", None) or getattr(result, "pages", None)
            if pages:
                metadata = [{"page": i + 1} for i in range(len(pages))]
        except Exception:
            pass

        if not metadata:
            metadata = [{"page": None}]

        return text, metadata

    def _parse_with_unstructured(self, file_path: str) -> tuple[str, list[dict]]:
        """Fallback parsing using Unstructured."""
        from unstructured.partition.auto import partition

        elements = partition(filename=file_path)
        text = "\n".join([str(el) for el in elements])

        metadata = [{"page": getattr(el, "metadata", {}).get("page_number")} for el in elements]
        if not metadata:
            metadata = [{"page": None}]

        return text, metadata

    def _parse_as_text(self, file_path: str) -> tuple[str, list[dict]]:
        """Read as plain text file."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return text, [{"page": None}]
