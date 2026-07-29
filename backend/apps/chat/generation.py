"""Transport-neutral, re-entrant execution of one durable chat Turn."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.db.models import Max
from django.utils import timezone

from apps.rag.errors import ProviderGenerationError
from apps.rag.language import resolve_reply_language

from .coordination import (
    CoordinationUnavailableError,
    LeaseLostError,
    RedisSessionLease,
    create_redis_client,
)
from .memory import build_memory_context, estimate_tokens
from .metrics import ChatStreamMetrics, merge_turn_metrics
from .models import ChatSession, ChatTurn, Citation, Message, ModelInvocation
from .services import InvalidTurnTransitionError, transition_chat_turn

logger = logging.getLogger(__name__)


class GenerationCancelled(RuntimeError):
    def __init__(self):
        super().__init__("generation_cancelled")


class GenerationCancellationUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("generation_cancellation_unavailable")


class SessionBusyError(RuntimeError):
    def __init__(self):
        super().__init__("chat_session_busy")


@dataclass(frozen=True)
class GenerationEvent:
    name: str
    data: dict[str, Any] | list[Any]
    terminal: bool = False


@dataclass(frozen=True)
class CompletedTurnPersistence:
    message: Message
    token_count: int
    timings: dict[str, Any]


class NeverCancelled:
    def requested(self) -> bool:
        return False

    def raise_if_requested(self) -> None:
        return None

    def clear(self) -> bool:
        return False


class RedisCancellationProbe:
    def __init__(self, client, turn_id, *, ttl_seconds: int = 900):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.client = client
        self.key = f"chat:v3:turn:{turn_id}:cancel"
        self.ttl_seconds = int(ttl_seconds)

    def request(self) -> bool:
        try:
            return bool(self.client.set(self.key, "1", ex=self.ttl_seconds))
        except Exception as exc:
            raise GenerationCancellationUnavailable() from exc

    def requested(self) -> bool:
        try:
            return self.client.get(self.key) is not None
        except Exception as exc:
            raise GenerationCancellationUnavailable() from exc

    def raise_if_requested(self) -> None:
        if self.requested():
            raise GenerationCancelled()

    def clear(self) -> bool:
        try:
            return bool(self.client.delete(self.key))
        except Exception as exc:
            raise GenerationCancellationUnavailable() from exc


def _load_turn(turn_id):
    return ChatTurn.objects.select_related(
        "session",
        "space",
        "user",
        "question_message",
        "assistant_message",
    ).get(pk=turn_id)


def _make_lease(turn):
    return RedisSessionLease(create_redis_client(), turn.session_id)


def _refresh_db_connections() -> None:
    """close_old_connections, but never inside an atomic block.

    Long-lived SSE generators recycle stale connections between phases. In
    tests, however, the whole request runs inside the TestCase transaction —
    closing the shared connection there kills the test's own transaction
    (psycopg "the connection is closed"). Django's request signals skip this
    for the same reason; our explicit calls must too.
    """
    if connection.in_atomic_block:
        return
    close_old_connections()


def _maybe_open_knowledge_gap(turn, message) -> None:
    """KB/RAG audit spec P2 §B3: auto-open a gap ticket for insufficient answers.

    Idempotent per (space, normalized question) while a ticket is still in an
    open lifecycle. Matched taxonomy terms are recorded in suggested_source so
    term owners know where the gap sits. Best-effort — never breaks the turn.
    """
    try:
        if message.confidence_label != "insufficient" or turn.space_id is None:
            return
        from .models import KnowledgeGapTicket

        question = (turn.question_message.content or "").strip()[:2000]
        if not question:
            return
        question_hash = KnowledgeGapTicket.hash_question(question)
        if KnowledgeGapTicket.objects.filter(
            space_id=turn.space_id,
            normalized_question_hash=question_hash,
            status__in=[
                KnowledgeGapTicket.STATUS_OPEN,
                KnowledgeGapTicket.STATUS_IN_PROGRESS,
            ],
        ).exists():
            return
        suggested = "auto-created from an insufficient-confidence answer"
        try:
            from apps.rag.query_understanding import analyze_query

            signals = analyze_query(question, space_id=str(turn.space_id))
            if signals and signals.term_codes:
                suggested += " · matched terms: " + ", ".join(signals.term_codes)
        except Exception:
            pass
        ticket = KnowledgeGapTicket.objects.create(
            space=turn.space,
            question_snapshot=question,
            normalized_question_hash=question_hash,
            priority="medium",
            suggested_source=suggested,
        )
        from apps.audit.views import create_audit_log

        create_audit_log(
            user=turn.user,
            action="knowledge_gap_create",
            target_type="KnowledgeGapTicket",
            target_id=str(ticket.id),
            details={"auto": True, "space_id": str(turn.space_id)},
            space_id=turn.space_id,
        )
    except Exception:  # pragma: no cover — quality loop must not break chat
        logger.warning("auto_knowledge_gap_failed", exc_info=True)


def _conversation_history(session, question_message):
    """Layered session memory context (kept under the legacy name so existing
    test patches keep working). Single implementation: apps.chat.memory."""
    return build_memory_context(session, question_message)


def _estimate_token_count(text: str) -> int:
    return estimate_tokens(text)


def _schedule_memory_update(session_id) -> None:
    """Best-effort dispatch of the rolling-summary task after a turn lands."""
    if not getattr(settings, "CHAT_MEMORY_ENABLED", False):
        return
    try:
        from .tasks import update_session_memory

        update_session_memory.delay(str(session_id))
    except Exception:
        # A broker outage must never break a completed chat turn.
        logger.warning(
            "session_memory_dispatch_failed session_id=%s code=coordination_unavailable",
            session_id,
        )


def _save_citations(assistant_message, citations_data, space=None):
    from apps.knowledge.models import Document, DocumentChunk

    for citation in citations_data:
        try:
            document = Document.objects.get(id=citation.get("document_id"))
            if (
                space is not None
                and document.space_id is not None
                and document.space_id != space.id
            ):
                logger.warning(
                    "citation_scope_mismatch message_id=%s code=persistence_error",
                    assistant_message.id,
                )
                continue
            chunk = None
            if citation.get("chunk_id"):
                chunk = DocumentChunk.objects.filter(
                    id=citation["chunk_id"]
                ).first()
            Citation.objects.create(
                message=assistant_message,
                document=document,
                chunk=chunk,
                relevance_score=citation.get("score", 0),
                page_number=citation.get("page_number"),
                quoted_text=citation.get("quoted_text", ""),
                space=space,
            )
        except Exception:
            logger.warning(
                "citation_save_failed message_id=%s code=persistence_error",
                assistant_message.id,
            )


def _build_pipeline(turn):
    from apps.rag.pipeline import RAGPipeline

    pipeline = RAGPipeline()
    pipeline.model_name = turn.model_id
    pipeline.answer_mode = turn.answer_mode
    pipeline.thinking_enabled = turn.thinking_enabled
    pipeline.thinking_budget = turn.thinking_budget
    # Session-library-selection spec §5: a session that went through the
    # picker (non-null) pins retrieval to the turn's capped snapshot; a legacy
    # session (null) keeps keyword auto-routing (None sentinel).
    session_selection = getattr(turn.session, "reference_library_ids", None)
    if session_selection is None:
        pipeline.selected_library_ids = None
    else:
        pipeline.selected_library_ids = list(
            getattr(turn, "reference_library_ids", None) or []
        )
    return pipeline


def _record_invocation(
    turn,
    pipeline,
    started_at,
    invocation_status,
    *,
    error_code="",
    message=None,
    token_count=None,
):
    try:
        ModelInvocation.objects.create(
            session=turn.session,
            message=message,
            question_message=turn.question_message,
            space=turn.space,
            model=getattr(pipeline, "model_name", turn.model_id),
            status=invocation_status,
            token_count=token_count,
            latency_ms=int((time.time() - started_at) * 1000),
            error_code=error_code,
        )
    except Exception:
        logger.error(
            "model_invocation_persist_failed turn_id=%s code=persistence_error",
            turn.id,
        )


def _record_metrics(turn, *, increments=(), **values):
    try:
        merge_turn_metrics(turn, increments=increments, **values)
    except Exception:
        logger.warning(
            "turn_metrics_persist_failed turn_id=%s code=persistence_error",
            turn.id,
        )


def _mark_failed(turn, error_code):
    try:
        transition_chat_turn(turn, ChatTurn.STATUS_FAILED, error_code=error_code)
    except InvalidTurnTransitionError:
        logger.info("Turn %s was already terminal", turn.id)
    except Exception:
        logger.error(
            "turn_failure_state_persist_failed turn_id=%s code=persistence_error",
            turn.id,
        )


def _mark_cancelled(turn):
    try:
        transition_chat_turn(turn, ChatTurn.STATUS_CANCELLED)
    except InvalidTurnTransitionError:
        logger.info("Turn %s was already terminal", turn.id)
    except Exception:
        logger.error(
            "turn_cancel_state_persist_failed turn_id=%s code=persistence_error",
            turn.id,
        )


def _regenerate_source_for_turn(turn):
    source_turn = (
        ChatTurn.objects.filter(
            session_id=turn.session_id,
            question_message_id=turn.question_message_id,
            status=ChatTurn.STATUS_COMPLETED,
            assistant_message__isnull=False,
        )
        .exclude(pk=turn.pk)
        .select_related("assistant_message")
        .order_by("-started_at")
        .first()
    )
    return source_turn.assistant_message if source_turn else None


def _persist_completed_turn(
    turn,
    pipeline,
    *,
    response_tokens,
    citations_data,
    quality_data,
    started_at,
    stream_metrics,
    regenerate_source=None,
    citation_saver=None,
    token_counter=None,
):
    citation_saver = citation_saver or _save_citations
    token_counter = token_counter or _estimate_token_count
    assistant_content = "".join(response_tokens)
    token_count = token_counter(assistant_content)
    elapsed_ms = int((time.time() - started_at) * 1000)

    with transaction.atomic():
        if hasattr(turn, "_state"):
            locked_turn = (
                ChatTurn.objects.select_for_update()
                .get(pk=turn.pk)
            )
        else:
            # Database-free view contracts pass a faithful Turn double. Real
            # execution always takes the row lock above.
            locked_turn = turn
        if (
            locked_turn.status == ChatTurn.STATUS_COMPLETED
            and locked_turn.assistant_message is not None
        ):
            existing = locked_turn.assistant_message
            timings = stream_metrics.snapshot(now=time.monotonic())
            return CompletedTurnPersistence(existing, existing.token_count or 0, timings)

        source = regenerate_source
        if source is None and hasattr(locked_turn, "_state"):
            source = _regenerate_source_for_turn(locked_turn)
        version_values = {}
        if source is not None:
            max_version = Message.objects.filter(
                version_group_id=source.version_group_id,
            ).aggregate(value=Max("version_number"))["value"] or 1
            Message.objects.filter(
                version_group_id=source.version_group_id,
                is_current_version=True,
            ).update(is_current_version=False)
            version_values = {
                "version_group_id": source.version_group_id,
                "version_number": max_version + 1,
                "is_current_version": True,
                "supersedes_message": source,
            }

        assistant_message = Message.objects.create(
            session=locked_turn.session,
            role="assistant",
            content=assistant_content,
            token_count=token_count,
            model_used=pipeline.model_name,
            response_time_ms=elapsed_ms,
            retrieval_count=len(citations_data),
            confidence_score=quality_data.get("score"),
            confidence_label=quality_data.get("confidence", ""),
            needs_human_review=quality_data.get("needs_human_review", False),
            retrieval_mode=quality_data.get("retrieval_mode", ""),
            retrieval_latency_ms=quality_data.get("retrieval_latency_ms"),
            space=locked_turn.space,
            **version_values,
        )
        citation_saver(assistant_message, citations_data, locked_turn.space)
        # KB/RAG audit spec P2 §B3: quality loop — insufficient answers
        # automatically open a knowledge-gap ticket (idempotent, best-effort).
        _maybe_open_knowledge_gap(locked_turn, assistant_message)
        _record_invocation(
            locked_turn,
            pipeline,
            started_at,
            "success",
            message=assistant_message,
            token_count=token_count,
        )
        ChatSession.objects.filter(pk=locked_turn.session_id).update(
            updated_at=timezone.now()
        )
        transition_chat_turn(
            locked_turn,
            ChatTurn.STATUS_COMPLETED,
            assistant_message=assistant_message,
            model_id=pipeline.model_name,
        )

    turn.status = ChatTurn.STATUS_COMPLETED
    turn.assistant_message = assistant_message
    turn.model_id = pipeline.model_name
    timings = stream_metrics.snapshot(now=time.monotonic())
    timings["routing_decision"] = "retrieve"
    _record_metrics(turn, **timings)
    # Session memory: fold older rounds into the rolling summary off the
    # critical path (default queue, never chat_generation capacity).
    _schedule_memory_update(turn.session_id)
    return CompletedTurnPersistence(assistant_message, token_count, timings)


def _error_event(code: str, *, retryable: bool = True) -> GenerationEvent:
    return GenerationEvent(
        "error",
        {"code": code, "retryable": retryable},
        terminal=True,
    )


def iter_chat_turn(
    turn_id,
    *,
    cancellation_probe=None,
    _turn=None,
    _lease=None,
    _lease_preacquired=False,
    _lease_started=False,
    _release_lease=True,
    _history_loader=None,
    _citation_saver=None,
    _token_counter=None,
    _regenerate_source=None,
    _started_at=None,
    _stream_metrics=None,
    _deadline_seconds=90,
    _emit_transport_events=False,
    _query=None,
    _language=None,
):
    """Yield safe domain events while executing exactly one durable Turn."""

    turn = _turn or _load_turn(turn_id)
    if turn.status in {
        ChatTurn.STATUS_COMPLETED,
        ChatTurn.STATUS_CANCELLED,
    }:
        return

    probe = cancellation_probe or NeverCancelled()
    lease = _lease or _make_lease(turn)
    acquired_here = not _lease_preacquired
    started_at = _started_at if _started_at is not None else time.time()
    metrics = _stream_metrics or ChatStreamMetrics(started_at=time.monotonic())
    history_loader = _history_loader or _conversation_history
    pipeline = None
    response_tokens: list[str] = []
    citations_data: list[Any] = []
    quality_data: dict[str, Any] = {}
    answering_announced = False

    try:
        if acquired_here and not lease.acquire():
            raise SessionBusyError()
        if not _lease_started:
            lease.start_renewal()

        probe.raise_if_requested()
        lease.ensure_owned()
        history = history_loader(turn.session, turn.question_message)
        pipeline = _build_pipeline(turn)
        transition_chat_turn(
            turn,
            ChatTurn.STATUS_RETRIEVING,
            model_id=turn.model_id,
        )
        metrics.mark_first_event(time.monotonic())
        yield GenerationEvent("phase", {"phase": "retrieving"})

        query = _query
        if query is None:
            query = turn.question_message.content
        language = _language
        if language is None:
            language = resolve_reply_language(query, turn.user, turn.space)
        _refresh_db_connections()
        raw_events = pipeline.retrieve_and_generate(
            query=query,
            user_profile=turn.user,
            conversation_history=history,
            language=language,
            space_id=str(turn.space_id) if turn.space_id else None,
        )
        for raw_event in raw_events:
            probe.raise_if_requested()
            lease.ensure_owned()
            event_type = raw_event.get("event")
            data = raw_event.get("data", {})

            if event_type == "citations" and isinstance(data, list):
                citations_data = data
                metrics.mark_first_event(time.monotonic())
                metrics.mark_retrieval_result(len(data))
                yield GenerationEvent("citations", data)
            elif event_type == "quality" and isinstance(data, dict):
                quality_data = data
                metrics.mark_first_event(time.monotonic())
                retrieval_ms = data.get("retrieval_latency_ms")
                if isinstance(retrieval_ms, (int, float)) and not isinstance(
                    retrieval_ms, bool
                ):
                    metrics.mark_retrieval(retrieval_ms)
                yield GenerationEvent("quality", data)
            elif event_type == "metrics" and isinstance(data, dict):
                reasoning_ms = data.get("reasoning_ms")
                if isinstance(reasoning_ms, (int, float)) and not isinstance(
                    reasoning_ms, bool
                ):
                    metrics.mark_reasoning(reasoning_ms)
            elif event_type == "phase" and isinstance(data, dict):
                metrics.mark_first_event(time.monotonic())
                yield GenerationEvent("phase", data)
            elif event_type == "token" and isinstance(data, dict):
                if time.time() - started_at > _deadline_seconds:
                    raise TimeoutError("generation deadline exceeded")
                token = data.get("token", "")
                if not isinstance(token, str):
                    continue
                metrics.mark_first_answer(time.monotonic())
                if turn.status != ChatTurn.STATUS_ANSWERING:
                    transition_chat_turn(
                        turn,
                        ChatTurn.STATUS_ANSWERING,
                        model_id=pipeline.model_name,
                    )
                if _emit_transport_events and not answering_announced:
                    answering_announced = True
                    yield GenerationEvent("phase", {"phase": "answering"})
                response_tokens.append(token)
                yield GenerationEvent("answer_delta", {"text": token})

        probe.raise_if_requested()
        lease.ensure_owned()
        transition_chat_turn(turn, ChatTurn.STATUS_SAVING)
        if _emit_transport_events:
            yield GenerationEvent("phase", {"phase": "saving"})
        probe.raise_if_requested()
        lease.ensure_owned()
        persistence = _persist_completed_turn(
            turn,
            pipeline,
            response_tokens=response_tokens,
            citations_data=citations_data,
            quality_data=quality_data,
            started_at=started_at,
            stream_metrics=metrics,
            regenerate_source=_regenerate_source,
            citation_saver=_citation_saver,
            token_counter=_token_counter,
        )
        turn.status = ChatTurn.STATUS_COMPLETED
        turn.assistant_message = persistence.message
        if _emit_transport_events:
            yield GenerationEvent(
                "usage",
                {"output_tokens": persistence.token_count, **persistence.timings},
            )
        yield GenerationEvent(
            "done",
            {
                "message_id": str(persistence.message.id),
                "session_id": str(turn.session_id),
                "model": pipeline.model_name,
                "turn_id": str(turn.id),
                "client_request_id": str(turn.client_request_id),
            },
            terminal=True,
        )
    except GenerationCancelled:
        _mark_cancelled(turn)
        yield _error_event("cancelled", retryable=False)
    except ProviderGenerationError:
        if pipeline is not None:
            _record_invocation(
                turn,
                pipeline,
                started_at,
                "failure",
                error_code="provider_unavailable",
            )
        _mark_failed(turn, "provider_unavailable")
        yield _error_event("provider_unavailable")
    except LeaseLostError:
        if pipeline is not None:
            _record_invocation(
                turn,
                pipeline,
                started_at,
                "failure",
                error_code="lease_lost",
            )
        _mark_failed(turn, "lease_lost")
        yield _error_event("lease_lost")
    except (CoordinationUnavailableError, GenerationCancellationUnavailable):
        _mark_failed(turn, "coordination_unavailable")
        yield _error_event("coordination_unavailable")
    except TimeoutError:
        if pipeline is not None:
            _record_invocation(
                turn,
                pipeline,
                started_at,
                "timeout",
                error_code="stream_timeout",
            )
        _mark_failed(turn, "stream_timeout")
        yield _error_event("stream_timeout")
    except SessionBusyError:
        raise
    except Exception:
        code = (
            "answer_save_error"
            if turn.status == ChatTurn.STATUS_SAVING
            else "stream_error"
        )
        logger.exception(
            "chat_generation_failed turn_id=%s code=%s",
            turn.id,
            code,
        )
        if pipeline is not None:
            _record_invocation(
                turn,
                pipeline,
                started_at,
                "failure",
                error_code=code,
            )
        _mark_failed(turn, code)
        yield _error_event(code)
    finally:
        if _release_lease:
            try:
                lease.release()
            except CoordinationUnavailableError:
                logger.warning(
                    "lease_release_failed turn_id=%s code=coordination_unavailable",
                    turn.id,
                )
        try:
            probe.clear()
        except GenerationCancellationUnavailable:
            logger.warning(
                "cancel_probe_clear_failed turn_id=%s code=coordination_unavailable",
                turn.id,
            )
        _refresh_db_connections()
