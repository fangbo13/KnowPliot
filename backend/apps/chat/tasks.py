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
