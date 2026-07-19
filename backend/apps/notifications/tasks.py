"""Celery dispatchers for durable external notification delivery."""

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import ActionOutboxEvent
from .outbox_services import dispatch_action_outbox_event


def _configured_delivery_adapter(event):
    adapter_path = str(
        getattr(settings, "ACTION_OUTBOX_DELIVERY_ADAPTER", "") or ""
    ).strip()
    if not adapter_path:
        raise ImproperlyConfigured("ACTION_OUTBOX_DELIVERY_ADAPTER is not configured")
    import_string(adapter_path)(event)


@shared_task
def deliver_action_outbox_event(event_id):
    return dispatch_action_outbox_event(event_id, _configured_delivery_adapter)


@shared_task
def sweep_action_outbox(limit=100):
    """Wake due/retry/expired-lease rows; row claims prevent double delivery."""

    now = timezone.now()
    event_ids = list(
        ActionOutboxEvent.objects.filter(
            Q(
                state__in=[
                    ActionOutboxEvent.STATE_PENDING,
                    ActionOutboxEvent.STATE_FAILED,
                ],
                next_attempt_at__lte=now,
            )
            | Q(
                state=ActionOutboxEvent.STATE_DELIVERING,
                lease_expires_at__lte=now,
            )
        )
        .order_by("next_attempt_at", "created_at", "id")
        .values_list("id", flat=True)[: max(1, min(int(limit), 500))]
    )
    for event_id in event_ids:
        deliver_action_outbox_event.delay(str(event_id))
    return len(event_ids)
