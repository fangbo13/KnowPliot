"""Docker-specific settings: uses PostgreSQL (pgvector) while keeping DEBUG=True.

This is the correct settings module for running the app inside Docker Compose,
where PostgreSQL with pgvector extension is available but we still want dev-friendly
settings (debug, CORS allow-all, console email).
"""

from .base import *  # noqa: F401,F403

# Keep debug enabled for local Docker development
DEBUG = True
ALLOWED_HOSTS = ["*"]

# CORS for local dev
CORS_ALLOW_ALL_ORIGINS = True

# Email backend for local dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailEmailBackend"

# Database: Use PostgreSQL from Docker Compose (with pgvector support)
# This is inherited from base.py — no override needed!
# The base.py DATABASES config uses env vars that docker-compose provides:
#   POSTGRES_DB=ey_onboarding, POSTGRES_USER=ey_onboarding, etc.
# The pgvector migration (0004) will now run successfully.

# SSL verify off for local Docker (DashScope API calls)
SSL_VERIFY = False
