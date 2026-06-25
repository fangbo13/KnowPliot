"""Docker-specific settings: uses PostgreSQL (pgvector) while keeping DEBUG=True.

This is the correct settings module for running the app inside Docker Compose,
where PostgreSQL with pgvector extension is available but we still want dev-friendly
settings (debug, CORS whitelist, console email).

V4.1 SYS-V4.1-001: Removed CORS_ALLOW_ALL_ORIGINS — it overrides
CORS_ALLOWED_ORIGINS from base.py, allowing any domain to make cross-origin
requests with a stolen JWT. Now using explicit whitelist instead.
V4.1 SYS-V4.1-002: Restricted ALLOWED_HOSTS from ["*"] to specific hosts.
"""

from .base import *  # noqa: F401,F403

# Keep debug enabled for local Docker development (V4.1 decision: dev priority)
DEBUG = True
# V4.1 SYS-V4.1-002: Restrict ALLOWED_HOSTS (was ["*"] — Host header injection risk)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "backend", "0.0.0.0"]

# V4.1 SYS-V4.1-001: CORS whitelist (was CORS_ALLOW_ALL_ORIGINS = True)
# Explicit whitelist replaces the dangerous allow-all setting.
# SYS domain uses ports 3030 (frontend) and 8030 (backend).
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3030",
    "http://127.0.0.1:3030",
    "http://localhost:8030",
    "http://127.0.0.1:8030",
]

# Email backend for local dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Database: Use PostgreSQL from Docker Compose (with pgvector support)
# This is inherited from base.py — no override needed!
# The base.py DATABASES config uses env vars that docker-compose provides:
#   POSTGRES_DB=ey_onboarding, POSTGRES_USER=ey_onboarding, etc.
# The pgvector migration (0004) will now run successfully.

# V4.1 SYS-V4.1-011: Removed SSL_VERIFY = False override.
# base.py now correctly reads SSL_VERIFY from env (default: true).
# Dockerfile has been updated with ca-certificates for HTTPS support.

