# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from .base import *  # noqa: F401,F403

# Development overrides
DEBUG = True
ALLOWED_HOSTS = ["*"]

# CORS for local dev
CORS_ALLOW_ALL_ORIGINS = True

# Email backend for local dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Use SQLite for local development (override PostgreSQL from .env)
DATABASES = {  # noqa: F405
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# Override Redis-backed cache with local memory cache for local dev
# (avoids requiring a Redis server when running outside Docker)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "knowpilot-dev",
    }
}

# Disable Celery broker Redis URL for local dev (tasks run synchronously)
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memcached://"

# Override chat coordination Redis URL — use a no-op/empty string so any direct
# Redis import falls back to synchronous mode instead of connecting to docker hostname
CHAT_COORDINATION_REDIS_URL = ""

# Clear Redis env vars to prevent any code reading os.environ directly
import os as _os
_os.environ["REDIS_URL"] = ""
_os.environ["RATE_LIMIT_REDIS_URL"] = ""

# Disable pgvector for SQLite dev mode
# The pgvector field will be stored as JSON in SQLite
