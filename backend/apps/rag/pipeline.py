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
import threading
import time
from dataclasses import dataclass

from django.conf import settings

from apps.core.circuit_breaker import dashscope_breaker  # V4.2 SYS-V4.2-014
from apps.knowledge.batch import is_zero_vector, sanitize_metadata  # V4.2 BATCH-009/012

from .config import CHUNK_OVERLAP, CHUNK_SIZE, SIMILARITY_THRESHOLD, TOP_K
from .cjk import cjk_token_text
from .embedding import EmbeddingService
from .errors import ProviderGenerationError
from .guardrails import GuardrailsService, get_llm_service
from .hybrid import HybridRetriever, classify_confidence
from .prompt_builder import PromptBuilder
from .retriever import PgVectorRetriever

logger = logging.getLogger(__name__)


def _document_term_codes(document) -> list[str]:
    """Spec §2: sorted controlled-term codes for chunk metadata (best-effort)."""
    try:
        from apps.knowledge.models import DocumentTag

        return sorted(
            DocumentTag.objects.filter(
                document=document, term__status="active"
            ).values_list("term__code", flat=True)
        )
    except Exception:
        logger.warning("document_term_codes_lookup_failed", exc_info=True)
        return []


@dataclass(frozen=True)
class _SharedChatServices:
    embedder: EmbeddingService
    retriever: HybridRetriever
    prompt_builder: PromptBuilder
    guardrails: GuardrailsService


_shared_chat_services = None
_shared_chat_services_lock = threading.Lock()


def _sync_pgvector_column(pairs: list[tuple[str, list[float]]]) -> None:
    """Batch-sync JSON embeddings into the pgvector ``embedding_vector`` column.

    V4.3 UAT FIX kept the retriever's HNSW index in sync but issued one raw
    UPDATE per chunk (N round-trips). P1 §B4: a single ``executemany`` batch
    (psycopg3 pipelines it) replaces the loop. No-op on SQLite, where the
    vector column does not exist.
    """
    if not pairs:
        return
    from django.db import connection

    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.executemany(
            "UPDATE knowledge_documentchunk SET embedding_vector = %s::vector WHERE id = %s",
            [
                ("[" + ",".join(str(v) for v in embedding) + "]", chunk_id)
                for chunk_id, embedding in pairs
            ],
        )


def get_shared_chat_services() -> _SharedChatServices:
    """Reuse immutable/stateless chat services across concurrent requests."""

    global _shared_chat_services
    if _shared_chat_services is None:
        with _shared_chat_services_lock:
            if _shared_chat_services is None:
                embedder = EmbeddingService()
                _shared_chat_services = _SharedChatServices(
                    embedder=embedder,
                    retriever=HybridRetriever(
                        vector_retriever=PgVectorRetriever(embedder=embedder)
                    ),
                    prompt_builder=PromptBuilder(),
                    guardrails=GuardrailsService(),
                )
    return _shared_chat_services


class RAGPipeline:
    """Orchestrates the full RAG lifecycle: ingest, retrieve, generate."""

    def __init__(self, *, ingestion=False):
        shared = get_shared_chat_services()
        self.retriever = shared.retriever
        self.prompt_builder = shared.prompt_builder
        self.guardrails = shared.guardrails
        self.llm = get_llm_service()
        self.model_name = settings.RAG_LLM_MODEL
        self.answer_mode = "fast"
        self.thinking_enabled = False
        self.thinking_budget = None
        if ingestion:
            from .chunker import LangChainChunker

            self.parser = DocumentParser()
            self.chunker = LangChainChunker(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
            )
            self.embedder = EmbeddingService()

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

        if not hasattr(self, "parser") or not hasattr(self, "chunker"):
            raise RuntimeError("ingestion_pipeline_required")

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

        # Chunk — P2 §A7: markdown files use structure-aware heading splits.
        if (document.file_type or "").lower() in ("md", "markdown"):
            chunks = self.chunker.split_markdown(raw_text)
        else:
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
        vector_sync_pairs: list[tuple[str, list[float]]] = []
        # Spec §2: redundantly write controlled term codes onto every chunk so
        # retrieval can filter/boost without extra joins.
        document_term_codes = _document_term_codes(document)
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # V4.2 KB-V4.2-BATCH-009: Sanitize metadata before storing
            raw_metadata = chunk.get("metadata", {})
            clean_metadata = sanitize_metadata(raw_metadata)
            if document_term_codes:
                clean_metadata["terms"] = document_term_codes

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
                # P1 §A6: CJK-bigram token text for Chinese-capable FTS.
                content_tokens=cjk_token_text(f"{document.title}\n{chunk['text']}"),
                chunk_index=i,
                page_number=clean_metadata.get("page"),
                metadata=clean_metadata,
                embedding=embedding,
            )
            if embedding and not is_zero_vector(embedding):
                vector_sync_pairs.append((str(doc_chunk.id), embedding))
            document_chunks.append(doc_chunk)

        # V4.3 UAT FIX + P1 §B4: sync JSON embeddings to the pgvector column in
        # ONE batched round-trip (was one raw UPDATE per chunk).
        _sync_pgvector_column(vector_sync_pairs)

        logger.info(f"Ingested {len(document_chunks)} chunks from {document.title}")
        self._refresh_similarity(document)
        return document_chunks

    # ── Part 1 (KB version化): text_content-based ingest ──────────────
    def ingest_text_content(self, document) -> list:
        """Chunk, embed, and store a document based on its ``text_content``.

        Part 1 (SPEC §1.2 / §1.3): Version creation and rollback re-chunk +
        re-embed the document's editable canonical markdown ``text_content``,
        bypassing the file parser.  Called inside the version-switching
        transaction so new chunks land atomically with version metadata.

        V4.2 KB-V4.2-BATCH-006/009/012 protections are reused (text size
        limit, chunk count limit, metadata sanitization, zero-vector
        detection) so inline-created / edited documents are guarded by the
        same safety net as file-based ingests.

        Args:
            document: Django ``Document`` model instance with populated
                ``text_content``.

        Returns:
            List of created ``DocumentChunk`` instances.
        """
        from apps.knowledge.models import DocumentChunk

        if not hasattr(self, "chunker") or not hasattr(self, "embedder"):
            raise RuntimeError("ingestion_pipeline_required")

        raw_text = document.text_content or ""

        # V4.2 KB-V4.2-BATCH-006: Extracted text size limit
        max_text_size = getattr(settings, "MAX_EXTRACTED_TEXT_SIZE", 10_000_000)
        if len(raw_text) > max_text_size:
            logger.warning(
                f"[BATCH-006] text_content for '{document.title}' is "
                f"{len(raw_text)} bytes — exceeds limit of {max_text_size} bytes. "
                f"Truncating to limit."
            )
            raw_text = raw_text[:max_text_size]
            document.processing_error = "text_content exceeds size limit — truncated."
            document.save(update_fields=["processing_error"])

        # Chunk — P2 §A7: text_content is canonical markdown, use
        # structure-aware heading splits (falls back when no headings).
        chunks = self.chunker.split_markdown(raw_text)

        max_chunks = getattr(settings, "MAX_CHUNKS_PER_DOCUMENT", 500)
        if len(chunks) > max_chunks:
            logger.warning(
                f"[BATCH-006] Document '{document.title}' produces {len(chunks)} chunks — "
                f"exceeds limit of {max_chunks}. Truncating."
            )
            chunks = chunks[:max_chunks]
            document.processing_error = (
                f"Document produces too many chunks — truncated to {max_chunks}."
            )
            document.save(update_fields=["processing_error"])

        # Embed in batches
        texts = [c["text"] for c in chunks]
        embeddings = self.embedder.embed_batch(texts)

        # V4.2 KB-V4.2-BATCH-012: Zero-vector detection
        zero_vector_count = sum(1 for emb in embeddings if is_zero_vector(emb))
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
            return []

        # Store chunks with sanitized metadata + pgvector sync
        document_chunks = []
        vector_sync_pairs: list[tuple[str, list[float]]] = []
        # Spec §2: redundantly write controlled term codes onto every chunk.
        document_term_codes = _document_term_codes(document)
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            raw_metadata = chunk.get("metadata", {})
            clean_metadata = sanitize_metadata(raw_metadata)
            if document_term_codes:
                clean_metadata["terms"] = document_term_codes
            if is_zero_vector(embedding):
                clean_metadata["embedding_failed"] = True
                logger.warning(
                    f"[BATCH-012] Chunk {i} of '{document.title}' has zero vector — marked."
                )
            doc_chunk = DocumentChunk.objects.create(
                document=document,
                space_id=document.space_id,
                content=chunk["text"],
                # P1 §A6: CJK-bigram token text for Chinese-capable FTS.
                content_tokens=cjk_token_text(f"{document.title}\n{chunk['text']}"),
                chunk_index=i,
                page_number=clean_metadata.get("page"),
                metadata=clean_metadata,
                embedding=embedding,
            )
            if embedding and not is_zero_vector(embedding):
                vector_sync_pairs.append((str(doc_chunk.id), embedding))
            document_chunks.append(doc_chunk)

        # P1 §B4: one batched pgvector sync instead of per-chunk UPDATEs.
        _sync_pgvector_column(vector_sync_pairs)

        logger.info(
            f"Ingested {len(document_chunks)} chunks from text_content of {document.title}"
        )
        self._refresh_similarity(document)
        return document_chunks

    @staticmethod
    def _refresh_similarity(document) -> None:
        """P1 §B2: refresh pooled embedding + precomputed graph similarity edges.

        Best-effort — the helper swallows its own errors, and this wrapper
        guards against import-time failures so ingest never breaks.
        P3 §B1: also resolves other documents' gray links pointing at this
        document's title now that it exists in the index.
        """
        try:
            from apps.knowledge.similarity import refresh_document_similarity

            refresh_document_similarity(document)
        except Exception:
            logger.warning("similarity_refresh_failed", exc_info=True)
        try:
            from apps.knowledge.links import resolve_unresolved_links_to

            resolve_unresolved_links_to(document)
        except Exception:
            logger.warning("unresolved_link_resolution_failed", exc_info=True)

    def retrieve_and_generate(
        self,
        query: str,
        user_profile,
        conversation_history: list,
        *,
        space_id: str,
        language: str = "en",
    ):
        """Full RAG: retrieve context, build prompt, call LLM, stream response.

        Args:
            space_id: V6.0 — restrict retrieval (and therefore citations) to the
                active knowledge space. The pipeline no longer supports
                unscoped callers.

        Yields:
            Dicts with 'event' and 'data' keys for SSE streaming.
        """
        # Step 1: Guardrails - check for injection
        try:
            if not self.guardrails.check_input(query):
                yield {"event": "token", "data": {"token": self.guardrails.generate_fallback(language)}}
                yield {"event": "done", "data": {}}
                return
        except Exception:
            logger.error("chat_guardrails_failed code=guardrails_error")
            # V4.3 UAT: If guardrails service fails, proceed anyway —
            # guardrails is a safety enhancement, not a hard gate.
            pass

        # Step 2: Retrieve relevant chunks
        # V4.3 UAT: Wrap retrieval in try/except — if retriever/embedding fails
        # (e.g., PgVector not configured, DashScope embedding API unavailable),
        # return graceful degraded response instead of uncaught exception that
        # causes SSE "error" event → frontend shows "当前无法获取响应".
        retrieval_started = time.monotonic()
        # KB optimization spec §3.3 + P2 §A1: expand retrieval to opted-in
        # reference libraries, ROUTED by query signals (library name /
        # category keywords) instead of unconditionally searching every
        # library. RAG_LIBRARY_ROUTING_ENABLED=False restores full fan-out.
        reference_space_ids: list[str] = []
        library_name_by_space: dict[str, str] = {}
        try:
            from apps.spaces.models import KnowledgeSpace

            from .library_routing import route_reference_libraries

            active_space = KnowledgeSpace.objects.filter(pk=space_id).first()
            if active_space is not None:
                reference_space_ids, library_name_by_space = route_reference_libraries(
                    query, active_space
                )
        except Exception:
            logger.warning("reference_library_resolve_failed", exc_info=True)
            reference_space_ids = []
            library_name_by_space = {}
        space_ids = [space_id, *reference_space_ids]
        try:
            chunks = self.retriever.search(
                query=query,
                top_k=TOP_K,
                similarity_threshold=SIMILARITY_THRESHOLD,
                space_id=space_id,  # V6.0 space isolation
                space_ids=space_ids,  # KB spec §3.3 cross-library retrieval
            )
        except Exception:
            logger.error("chat_retrieval_failed code=retrieval_error")
            dashscope_breaker.record_failure()  # Count as failure for circuit breaker
            degraded_msg = (
                "抱歉，知识检索服务暂时不可用，请稍后重试。" if language == "zh"
                else "Sorry, the knowledge retrieval service is temporarily unavailable. Please try again later."
            )
            retrieval_latency_ms = int((time.monotonic() - retrieval_started) * 1000)
            yield {
                "event": "quality",
                "data": {
                    "confidence": "insufficient",
                    "score": 0.0,
                    "needs_human_review": True,
                    "retrieval_mode": "hybrid",
                    "retrieval_latency_ms": retrieval_latency_ms,
                },
            }
            yield {"event": "token", "data": {"token": degraded_msg}}
            yield {"event": "citations", "data": []}
            yield {"event": "done", "data": {}}
            return

        # V4.2 SYS-V4.2-014: Circuit breaker check — fail fast if DashScope is down
        if not dashscope_breaker.allow_request():
            if getattr(self, "answer_mode", "fast") == "deep":
                logger.warning(
                    "provider_circuit_open code=provider_unavailable"
                )
                raise ProviderGenerationError("provider_unavailable")
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
            # KB optimization spec §3.3: attach reference-library provenance.
            source_library = library_name_by_space.get(str(chunk.get("space_id")))
            sanitized_chunks.append({**chunk, "content": content, "source_library": source_library})
        chunks = sanitized_chunks
        # P2 §A8: optional LLM rerank of the final top-k (default off).
        if getattr(settings, "RAG_LLM_RERANK_ENABLED", False) and chunks:
            from .llm_rerank import llm_rerank

            chunks = llm_rerank(query, chunks, self.llm)
        retrieval_latency_ms = int((time.monotonic() - retrieval_started) * 1000)
        quality = classify_confidence(chunks)
        yield {
            "event": "quality",
            "data": {
                "confidence": quality.label,
                "score": quality.score,
                "needs_human_review": quality.needs_human_review,
                "retrieval_mode": "hybrid",
                "retrieval_latency_ms": retrieval_latency_ms,
            },
        }

        # Step 2b: Refuse when evidence is absent or too weak. Low-confidence
        # retrieval must never be promoted into an uncited deterministic claim.
        if not chunks or quality.label in {"low", "insufficient"}:
            # P0 fix (KB/RAG audit spec §C): domain-neutral refusal copy — the
            # legacy HR wording predates the audit/accounting positioning.
            fallback = (
                "我没有足够的信息来回答此问题，请补充相关知识文档或联系知识库管理员。"
                if language == "zh"
                else "I don't have enough information to answer this question. Please add the relevant knowledge documents or contact your knowledge base administrator."
            )
            yield {"event": "token", "data": {"token": fallback}}
            yield {
                "event": "citations",
                "data": self._build_citations(chunks) if chunks else [],
            }
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
        except Exception:
            logger.error("chat_prompt_build_failed code=prompt_build_error")
            dashscope_breaker.record_failure()
            degraded_msg = (
                "抱歉，系统暂时无法处理您的请求，请稍后重试。" if language == "zh"
                else "Sorry, the system is temporarily unable to process your request. Please try again later."
            )
            yield {"event": "token", "data": {"token": degraded_msg}}
            yield {"event": "citations", "data": citations}
            yield {"event": "done", "data": {}}
            return

        # V4 Part 3: Emit "thinking" phase when thinking mode is enabled.
        # Sends a progressive safe-label via SSE so the frontend ProcessingPanel
        # can display "正在思考..." without exposing raw CoT or timing.
        if getattr(self, "thinking_enabled", False):
            yield {"event": "phase", "data": {"phase": "thinking"}}

        # Step 5: Stream LLM response — V4.2 SYS-V4.2-014: circuit breaker wraps the call
        # On success: record_success() closes the circuit.
        # On failure: record_failure() counts toward opening the circuit.
        llm_success = False
        try:
            stream_parts = getattr(self.llm, "stream_chat_parts", None)
            if callable(stream_parts):
                for part in stream_parts(
                    system_prompt,
                    query,
                    model_id=self.model_name,
                    thinking_enabled=getattr(self, "thinking_enabled", False),
                    thinking_budget=getattr(self, "thinking_budget", None),
                ):
                    if part.kind == "reasoning_duration":
                        yield {
                            "event": "metrics",
                            "data": {"reasoning_ms": part.duration_ms or 0},
                        }
                    elif part.kind == "answer_delta":
                        llm_success = True
                        yield {"event": "token", "data": {"token": part.text}}
            else:
                for token in self.llm.stream_chat(system_prompt, query):
                    llm_success = True
                    yield {"event": "token", "data": {"token": token}}
            # Full success — record it to close/reset the circuit breaker
            if not llm_success:
                raise ProviderGenerationError("provider_empty_answer")
            dashscope_breaker.record_success()
        except Exception as exc:
            # V4.2 SYS-V4.2-014: Record failure to count toward circuit opening
            dashscope_breaker.record_failure()
            logger.error("provider_stream_failed code=provider_unavailable")
            if getattr(self, "answer_mode", "fast") == "deep":
                raise ProviderGenerationError("provider_unavailable") from exc
            degraded_msg = (
                "服务暂时不可用，请稍后重试。" if language == "zh"
                else "Service temporarily unavailable, please try again later."
            )
            yield {"event": "token", "data": {"token": degraded_msg}}

        yield {"event": "done", "data": {}}

    def _build_citations(self, chunks):
        """Build citation data from retrieved chunks.

        Spec §3/§4 L5: citations carry version + updated_by + updated_at so the
        frontend renders the "v{N} · {更新人} · {日期}" watermark, and a stale
        flag drives the "内容可能过期" badge.
        """
        doc_meta: dict[str, dict] = {}
        try:
            from apps.knowledge.models import Document

            from .hybrid import _valid_uuid_subset

            # Guard: synthetic/legacy chunk ids must not break the UUID query.
            doc_ids = _valid_uuid_subset(
                str(chunk["document_id"]) for chunk in chunks
            )
            for doc in Document.objects.filter(id__in=doc_ids).select_related(
                "updated_by", "uploaded_by"
            ):
                editor = doc.updated_by or doc.uploaded_by
                doc_meta[str(doc.id)] = {
                    "version": doc.version,
                    "updated_by": (editor.username or editor.email) if editor else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                    "stale": doc.status == "stale",
                }
        except Exception:
            logger.warning("citation_version_lookup_failed", exc_info=True)
        return [
            {
                "document_id": chunk["document_id"],
                "document_title": chunk["document_title"],
                "page_number": chunk.get("page_number"),
                # P2 §A7: heading path for structure-aware chunks ("H1 > H2").
                "section": (chunk.get("metadata") or {}).get("section"),
                "score": round(chunk["score"], 3),
                "quoted_text": chunk["content"][:200],
                "chunk_id": chunk["id"],
                "source_library": chunk.get("source_library"),
                **doc_meta.get(
                    str(chunk["document_id"]),
                    {"version": None, "updated_by": None, "updated_at": None, "stale": False},
                ),
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
