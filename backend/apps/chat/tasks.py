"""Dedicated Celery execution for protocol-v3 chat generation."""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.prometheus import (
    GENERATION_ACTIVE,
    GENERATION_DURATION,
    GENERATION_OUTSTANDING,
    GENERATION_QUEUED,
    LEASE_LOSSES,
    QUEUE_WAIT,
    TASK_RETRIES,
)
from .capacity import (
    GenerationCapacityController,
    GenerationCapacityUnavailable,
)
from .generation import RedisCancellationProbe, iter_chat_turn
from .metrics import merge_turn_metrics
from .models import ChatTurn
from .services import InvalidTurnTransitionError, transition_chat_turn
from .stream_events import EventStoreUnavailableError
from .stream_events_v3 import AnswerDeltaBatcher, RedisTurnStreamV3

logger = logging.getLogger(__name__)


class TransientGenerationInfrastructureError(RuntimeError):
    pass


class GenerationReservationLost(RuntimeError):
    def __init__(self, turn_id):
        super().__init__("generation_reservation_lost")
        self.turn_id = str(turn_id)


@lru_cache(maxsize=4)
def _shared_redis_client(url: str):
    from redis import Redis

    return Redis.from_url(
        url,
        decode_responses=False,
        socket_connect_timeout=2,
        socket_timeout=20,
        health_check_interval=30,
    )


def generation_capacity_controller() -> GenerationCapacityController:
    return GenerationCapacityController(
        _shared_redis_client(settings.CHAT_CAPACITY_REDIS_URL),
        max_outstanding=settings.CHAT_GENERATION_MAX_OUTSTANDING,
        ttl_seconds=settings.CHAT_GENERATION_RESERVATION_TTL_SECONDS,
        retry_after_seconds=settings.CHAT_GENERATION_RETRY_AFTER_SECONDS,
    )


def v3_event_store(turn_id) -> RedisTurnStreamV3:
    return RedisTurnStreamV3(
        _shared_redis_client(settings.CHAT_EVENTS_REDIS_URL),
        turn_id,
        ttl_seconds=settings.CHAT_EVENT_V3_TTL_SECONDS,
        max_length=settings.CHAT_EVENT_V3_MAXLEN,
        checkpoint=lambda sequence: ChatTurn.objects.filter(
            pk=turn_id,
            last_event_seq__lt=sequence,
        ).update(last_event_seq=sequence),
    )


def cancel_probe(turn_id) -> RedisCancellationProbe:
    return RedisCancellationProbe(
        _shared_redis_client(settings.CHAT_EVENTS_REDIS_URL),
        turn_id,
        ttl_seconds=settings.CHAT_EVENT_V3_TTL_SECONDS,
    )


def _mark_task_failed(turn_id, error_code):
    try:
        turn = ChatTurn.objects.get(pk=turn_id)
        if turn.status not in {
            ChatTurn.STATUS_ACCEPTED,
            ChatTurn.STATUS_RETRIEVING,
            ChatTurn.STATUS_REASONING,
            ChatTurn.STATUS_ANSWERING,
            ChatTurn.STATUS_SAVING,
        }:
            return
        transition_chat_turn(turn, ChatTurn.STATUS_FAILED, error_code=error_code)
    except (ChatTurn.DoesNotExist, InvalidTurnTransitionError):
        return
    except Exception:
        logger.error(
            "generation_task_failure_persist_failed turn_id=%s code=persistence_error",
            turn_id,
        )


def _record_task_metrics(turn_id, **values):
    try:
        turn = ChatTurn.objects.get(pk=turn_id)
        merge_turn_metrics(turn, **values)
    except Exception:
        logger.warning(
            "generation_task_metrics_failed turn_id=%s code=persistence_error",
            turn_id,
        )


def _task_attempt(task) -> int:
    retries = getattr(getattr(task, "request", None), "retries", 0)
    return max(1, int(retries) + 1)


@shared_task(
    bind=True,
    name="apps.chat.tasks.generate_chat_turn_v3",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(TransientGenerationInfrastructureError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=90,
    time_limit=100,
)
def generate_chat_turn_v3(self, turn_id: str):
    """Generate one Turn and publish recoverable, batched v3 events."""

    turn_id = str(turn_id)
    capacity = generation_capacity_controller()
    stream = v3_event_store(turn_id)
    probe = cancel_probe(turn_id)
    batch = AnswerDeltaBatcher(max_delay_seconds=0.05, max_chars=256)
    delta_batch_count = 0
    attempt = _task_attempt(self)
    task_started = time.monotonic()
    if attempt == 1:
        GENERATION_QUEUED.dec()
    GENERATION_ACTIVE.inc()
    if attempt > 1:
        TASK_RETRIES.inc()

    try:
        if not capacity.renew(turn_id):
            LEASE_LOSSES.inc()
            _mark_task_failed(turn_id, "worker_lost")
            raise GenerationReservationLost(turn_id)

        try:
            turn = ChatTurn.objects.only("started_at").get(pk=turn_id)
            queue_wait_ms = max(
                0,
                int((timezone.now() - turn.started_at).total_seconds() * 1000),
            )
        except Exception:
            queue_wait_ms = 0
        _record_task_metrics(
            turn_id,
            queue_wait_ms=queue_wait_ms,
            task_attempt=attempt,
            worker_recovered=attempt > 1,
        )
        QUEUE_WAIT.observe(queue_wait_ms / 1000)

        existing = stream.replay()
        has_queued = any(
            event.name == "phase" and event.data == {"phase": "queued"}
            for event in existing
        )
        has_terminal = bool(existing and existing[-1].name in {"done", "error"})
        if has_terminal:
            return {"status": "already_terminal", "turn_id": turn_id}
        if not has_queued:
            stream.append("phase", {"phase": "queued"})

        terminal_written = False
        for event in iter_chat_turn(
            turn_id,
            cancellation_probe=probe,
            _deadline_seconds=90,
        ):
            if event.name == "answer_delta":
                text = batch.push(event.data.get("text", ""))
                if text:
                    stream.append("answer_delta", {"text": text})
                    delta_batch_count += 1
                continue

            pending = batch.flush()
            if pending:
                stream.append("answer_delta", {"text": pending})
                delta_batch_count += 1
            stream.append(event.name, event.data, terminal=event.terminal)
            terminal_written = terminal_written or event.terminal

        pending = batch.flush()
        if pending:
            stream.append("answer_delta", {"text": pending})
            delta_batch_count += 1
        _record_task_metrics(turn_id, delta_batch_count=delta_batch_count)
        return {
            "status": "completed" if terminal_written else "no_op",
            "turn_id": turn_id,
        }
    except EventStoreUnavailableError:
        _mark_task_failed(turn_id, "coordination_unavailable")
        raise
    except GenerationCapacityUnavailable as exc:
        _mark_task_failed(turn_id, "coordination_unavailable")
        raise TransientGenerationInfrastructureError(
            "generation_capacity_unavailable"
        ) from exc
    finally:
        GENERATION_ACTIVE.dec()
        GENERATION_DURATION.observe(time.monotonic() - task_started)
        try:
            capacity.release(turn_id)
            read_outstanding = getattr(capacity, "outstanding", None)
            if callable(read_outstanding):
                GENERATION_OUTSTANDING.set(read_outstanding())
        except GenerationCapacityUnavailable:
            logger.warning(
                "generation_capacity_release_failed turn_id=%s code=coordination_unavailable",
                turn_id,
            )
        try:
            probe.clear()
        except Exception:
            logger.warning(
                "generation_cancel_clear_failed turn_id=%s code=coordination_unavailable",
                turn_id,
            )


def enqueue_chat_turn_v3(turn_id):
    return generate_chat_turn_v3.apply_async(
        args=[str(turn_id)],
        queue="chat_generation",
    )


# ── Session long-term memory (rolling summary) ──

# Freshest messages stay verbatim-only; the summary lags slightly behind so
# it never has to describe the exchange still fully present in the window.
_MEMORY_KEEP_RECENT = 4
_MEMORY_TRANSCRIPT_MESSAGE_CHARS = 800
_MEMORY_SUMMARY_MAX_CHARS = 4000
_MEMORY_MAX_KEY_FACTS = 12

_MEMORY_SYSTEM_PROMPT = (
    "You maintain the rolling memory of one assistant conversation. Merge the "
    "previous summary with the new transcript into an updated memory. Keep "
    "user-stated constraints, entities, decisions, numbers and open questions; "
    "drop pleasantries. Write summary and key_facts in the SAME language the "
    "transcript itself is written in (e.g. Chinese transcript -> Chinese "
    "summary), at most 300 tokens. Respond with ONLY a JSON object: "
    '{"summary": "...", "key_facts": ["...", "..."]} — key_facts is a list of '
    "at most 12 short standalone facts."
)


def _parse_memory_payload(raw: str) -> tuple[str, list[str]] | None:
    """Extract {summary, key_facts} from an LLM reply, tolerating code fences."""
    import json as _json

    text = (raw or "").strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            data = _json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict):
            summary = str(data.get("summary") or "").strip()
            facts_raw = data.get("key_facts")
            facts = []
            if isinstance(facts_raw, list):
                facts = [
                    str(fact).strip()[:300]
                    for fact in facts_raw
                    if str(fact).strip()
                ][:_MEMORY_MAX_KEY_FACTS]
            if summary:
                return summary[:_MEMORY_SUMMARY_MAX_CHARS], facts
    # Degenerate reply: treat the whole text as the summary, keep old facts.
    return text[:_MEMORY_SUMMARY_MAX_CHARS], []


@shared_task(
    bind=True,
    name="apps.chat.tasks.update_session_memory",
    max_retries=0,
    soft_time_limit=60,
    time_limit=75,
)
def update_session_memory(self, session_id: str):
    """Fold messages beyond the watermark into the rolling session summary.

    Idempotent per watermark; any LLM failure leaves the previous summary
    untouched and the next completed turn retries naturally.
    """
    from django.db import transaction

    from .models import ChatSession, Message, SessionMemory

    if not getattr(settings, "CHAT_MEMORY_ENABLED", False):
        return {"status": "disabled"}

    session = ChatSession.objects.filter(pk=session_id).first()
    if session is None:
        return {"status": "session_missing"}

    memory, _created = SessionMemory.objects.get_or_create(
        session=session,
        defaults={"space": session.space},
    )

    pending_qs = Message.objects.filter(session=session).order_by("created_at")
    if memory.summarized_until is not None:
        pending_qs = pending_qs.filter(created_at__gt=memory.summarized_until)
    pending = list(pending_qs.values("role", "content", "created_at"))

    trigger = getattr(settings, "CHAT_MEMORY_SUMMARY_TRIGGER", 8)
    if len(pending) < trigger:
        return {"status": "below_trigger", "pending": len(pending)}

    to_summarize = pending[:-_MEMORY_KEEP_RECENT] if len(
        pending
    ) > _MEMORY_KEEP_RECENT else pending
    if not to_summarize:
        return {"status": "below_trigger", "pending": len(pending)}

    transcript = "\n".join(
        f"{item['role']}: {(item['content'] or '')[:_MEMORY_TRANSCRIPT_MESSAGE_CHARS]}"
        for item in to_summarize
    )
    previous_block = memory.summary or "(none)"
    facts_block = "\n".join(f"- {fact}" for fact in (memory.key_facts or [])) or "(none)"
    user_prompt = (
        f"[Previous summary]\n{previous_block}\n\n"
        f"[Previous key facts]\n{facts_block}\n\n"
        f"[New transcript]\n{transcript}"
    )

    try:
        from apps.rag.guardrails import get_llm_service

        raw = get_llm_service().complete(
            _MEMORY_SYSTEM_PROMPT,
            user_prompt,
            max_tokens=500,
            temperature=0.0,
            timeout=45,
        )
    except Exception:
        # Keep the previous summary intact — the next turn retries naturally.
        logger.warning(
            "session_memory_llm_failed session_id=%s code=provider_unavailable",
            session_id,
        )
        return {"status": "llm_failed"}

    parsed = _parse_memory_payload(raw)
    if parsed is None:
        logger.warning(
            "session_memory_empty_reply session_id=%s code=provider_empty_answer",
            session_id,
        )
        return {"status": "empty_reply"}
    new_summary, new_facts = parsed
    if not new_facts:
        new_facts = list(memory.key_facts or [])[:_MEMORY_MAX_KEY_FACTS]
    watermark = to_summarize[-1]["created_at"]

    with transaction.atomic():
        locked = SessionMemory.objects.select_for_update().get(pk=memory.pk)
        if locked.summarized_until != memory.summarized_until:
            # A concurrent run already advanced the watermark — idempotent exit.
            return {"status": "already_updated"}
        locked.summary = new_summary
        locked.key_facts = new_facts
        locked.summarized_until = watermark
        locked.summary_version += 1
        locked.save(
            update_fields=[
                "summary",
                "key_facts",
                "summarized_until",
                "summary_version",
                "updated_at",
            ]
        )
    return {
        "status": "updated",
        "version": locked.summary_version,
        "summarized": len(to_summarize),
    }


# ── RAG optimization spec Phase 7: feedback-driven retrieval signal ──

# Weights for the per-document feedback score. Incorrect feedback is the
# strongest negative signal (it means the cited document misled the answer).
_FEEDBACK_WEIGHTS = {
    "helpful": 1.0,
    "unhelpful": -1.0,
    "incorrect": -2.0,
    "outdated": -1.0,
    "missing_source": 0.0,
}


@shared_task(name="apps.chat.tasks.recompute_document_feedback_scores")
def recompute_document_feedback_scores() -> dict:
    """Aggregate Feedback→Message→Citation→Document into Document.feedback_score.

    score = clamp((Σ weighted feedback) / max(count, 1), -1, 1). Applied as an
    ordering-only retrieval boost (see hybrid._apply_query_signals) so good
    documents surface higher and repeatedly-wrong ones sink — without ever
    touching the calibrated rerank_score / confidence thresholds.
    """
    from collections import defaultdict

    from django.db.models import Count

    from apps.knowledge.models import Document

    from .models import Citation, Feedback

    # message_id -> {feedback_type: count}
    per_message: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    feedback_rows = (
        Feedback.objects.exclude(message_id=None)
        .values("message_id", "feedback_type")
        .annotate(n=Count("id"))
    )
    for row in feedback_rows:
        per_message[str(row["message_id"])][row["feedback_type"]] += row["n"]
    if not per_message:
        return {"status": "no_feedback", "documents": 0}

    # document_id -> [weighted_sum, count]
    doc_acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    citations = Citation.objects.filter(
        message_id__in=per_message.keys()
    ).values("message_id", "document_id")
    for citation in citations:
        if citation["document_id"] is None:
            continue
        counts = per_message.get(str(citation["message_id"]), {})
        for feedback_type, n in counts.items():
            weight = _FEEDBACK_WEIGHTS.get(feedback_type, 0.0)
            acc = doc_acc[str(citation["document_id"])]
            acc[0] += weight * n
            acc[1] += n

    updated = 0
    for document_id, (weighted_sum, count) in doc_acc.items():
        if count == 0:
            continue
        score = max(-1.0, min(1.0, weighted_sum / count))
        updated += Document.objects.filter(id=document_id).update(
            feedback_score=round(score, 4)
        )
    logger.info("[feedback-score] documents=%d", updated)
    return {"status": "ok", "documents": updated}

