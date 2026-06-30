# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Docker-specific settings: uses PostgreSQL (pgvector) with DEBUG=False.

This is the correct settings module for running the app inside Docker Compose,
where PostgreSQL with pgvector extension is available.

V4.1 SYS-V4.1-001: Removed CORS_ALLOW_ALL_ORIGINS — explicit whitelist instead.
V4.1 SYS-V4.1-002: Restricted ALLOWED_HOSTS from ["*"] to specific hosts.
V4.2 SYS-V4.2-010: Set DEBUG=False — prevents middleware-layer stack trace leaks.
  Previous: DEBUG=True allowed Django to return full HTML stack traces for
  middleware-layer exceptions (DisallowedHost etc.) that SafeErrorResponseMiddleware
  could not intercept (it only catches view-layer exceptions via process_exception).
  Now: DEBUG=False ensures Django never returns stack trace HTML to the client,
  regardless of which layer the exception occurs in. SafeErrorResponseMiddleware
  still provides JSON-formatted error responses for view-layer exceptions.
  A custom 500.html template is added for any remaining Django error pages.
"""

from .base import *  # noqa: F401,F403

# V4.2 SYS-V4.2-010: DEBUG=False — prevents middleware-layer stack trace leaks
# Previous: DEBUG=True with comment "V4.1 decision: dev priority" — but this
# allowed Django to return full HTML stack traces for exceptions in middleware
# layers (CommonMiddleware DisallowedHost, SecurityMiddleware, etc.) that
# SafeErrorResponseMiddleware.process_exception() cannot intercept.
# Now: DEBUG=False ensures no stack traces are ever returned to clients.
# SafeErrorResponseMiddleware still handles view-layer exceptions (returns JSON).
# For middleware-layer exceptions, Django's default 500 handler returns the
# custom 500.html template (no stack traces, no settings, no SQL).
DEBUG = False
# V4.1 SYS-V4.1-002: Restrict ALLOWED_HOSTS (was ["*"] — Host header injection risk)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "backend", "0.0.0.0"]

# V4.1 SYS-V4.1-001: CORS whitelist (was CORS_ALLOW_ALL_ORIGINS = True)
# Explicit whitelist replaces the dangerous allow-all setting.
# SYS domain uses ports 3030/8030, KB domain uses ports 3020/8020.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3003",
    "http://127.0.0.1:3003",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3030",
    "http://127.0.0.1:3030",
    "http://localhost:8030",
    "http://127.0.0.1:8030",
    "http://localhost:3020",
    "http://127.0.0.1:3020",
    "http://localhost:8020",
    "http://127.0.0.1:8020",
]

# Email backend for local dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Database: Use PostgreSQL from Docker Compose (with pgvector support)
# This is inherited from base.py — no override needed!
# The base.py DATABASES config uses env vars that docker-compose provides:
#   POSTGRES_DB=knowpilot, POSTGRES_USER=knowpilot, etc.
# The pgvector migration (0004) will now run successfully.

# V4.1 SYS-V4.1-011: Removed SSL_VERIFY = False override.
# base.py now correctly reads SSL_VERIFY from env (default: true).
# Dockerfile has been updated with ca-certificates for HTTPS support.

