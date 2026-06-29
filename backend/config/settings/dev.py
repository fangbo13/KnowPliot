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

# Disable pgvector for SQLite dev mode
# The pgvector field will be stored as JSON in SQLite
