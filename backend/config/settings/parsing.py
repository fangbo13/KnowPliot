# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Small, pure helpers shared by environment-backed settings."""

from __future__ import annotations

import os
from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured


def env_bool(
    name: str,
    *,
    default: bool = False,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Read a boolean flag; only explicit true spellings enable it."""

    source = os.environ if environ is None else environ
    value = source.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def validate_capacity_settings(
    *,
    target_active: int,
    max_outstanding: int,
    reservation_ttl_seconds: int,
    retry_after_seconds: int,
    worker_concurrency: int,
    event_ttl_seconds: int,
    event_max_length: int,
    provider_max_connections: int,
    provider_max_keepalive_connections: int,
) -> None:
    """Fail startup when chat-capacity limits cannot be satisfied safely."""

    values = {
        "CHAT_GENERATION_TARGET_ACTIVE": target_active,
        "CHAT_GENERATION_MAX_OUTSTANDING": max_outstanding,
        "CHAT_GENERATION_RESERVATION_TTL_SECONDS": reservation_ttl_seconds,
        "CHAT_GENERATION_RETRY_AFTER_SECONDS": retry_after_seconds,
        "CHAT_GENERATION_WORKER_CONCURRENCY": worker_concurrency,
        "CHAT_EVENT_V3_TTL_SECONDS": event_ttl_seconds,
        "CHAT_EVENT_V3_MAXLEN": event_max_length,
        "PROVIDER_HTTP_MAX_CONNECTIONS": provider_max_connections,
        "PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS": (
            provider_max_keepalive_connections
        ),
    }
    non_positive = [name for name, value in values.items() if value <= 0]
    if non_positive:
        raise ImproperlyConfigured(
            f"Capacity settings must be positive: {', '.join(non_positive)}"
        )
    if target_active > max_outstanding:
        raise ImproperlyConfigured(
            "CHAT_GENERATION_TARGET_ACTIVE cannot exceed "
            "CHAT_GENERATION_MAX_OUTSTANDING"
        )
    if provider_max_connections < worker_concurrency:
        raise ImproperlyConfigured(
            "PROVIDER_HTTP_MAX_CONNECTIONS cannot be lower than "
            "CHAT_GENERATION_WORKER_CONCURRENCY"
        )
    if provider_max_keepalive_connections > provider_max_connections:
        raise ImproperlyConfigured(
            "PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS cannot exceed "
            "PROVIDER_HTTP_MAX_CONNECTIONS"
        )
