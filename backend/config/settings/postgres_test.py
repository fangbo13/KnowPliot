"""Hermetic Django test profile backed by a real PostgreSQL database.

PostgreSQL behavior (constraints, deferred triggers, row locks, pgvector) stays
real. Cache/throttle and Celery side effects remain process-local; their shared
worker semantics are covered by the explicit Redis integration profile.
"""

from config.settings.base import *  # noqa: F401,F403


DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = False  # noqa: F405

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "knowpilot-postgres-tests",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405

DEBUG = True
ALLOWED_HOSTS = ["*"]
