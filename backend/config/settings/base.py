# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

import json
import os
import warnings
from pathlib import Path

from .parsing import env_bool, validate_capacity_settings

# Load .env file
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Core settings — V4.1 SYS-V4.1-003: SECRET_KEY must be >= 32 bytes for HMAC security
# Old default "change-me-to-a-random-string" was only 26 bytes (InsecureKeyLengthWarning).
# Now: if env var is set and >= 32 bytes → use it; if unset → auto-generate (dev safe);
# if set but < 32 bytes → warn but still use it (dev friendly, not blocking startup).
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    warnings.warn(
        "DJANGO_SECRET_KEY not set — using auto-generated temporary key. "
        "Set DJANGO_SECRET_KEY in .env for persistent security (sessions/JWT survive restarts).",
        RuntimeWarning,
    )
    import secrets
    SECRET_KEY = secrets.token_urlsafe(50)
elif len(SECRET_KEY) < 32:
    warnings.warn(
        "DJANGO_SECRET_KEY is %d bytes — minimum 32 bytes recommended for HMAC security. "
        "Current key may be vulnerable to brute-force attacks." % len(SECRET_KEY),
        RuntimeWarning,
    )
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "corsheaders",
    "django_celery_results",
    "django_celery_beat",
    "pgvector",
    "rest_framework_simplejwt.token_blacklist",
]

LOCAL_APPS = [
    "apps.core",
    "apps.users",
    "apps.spaces",  # V6.0: multi-space platform (orgs, business lines, spaces)
    "apps.chat",
    "apps.knowledge",
    "apps.rag",
    "apps.audit",
    "apps.rbac",
    "apps.notifications",  # V7.0: in-app notifications + announcements
    "apps.scenario_templates",  # V7.1: Scenario templates center
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.prometheus.PrometheusRequestMiddleware",
    "apps.core.middleware.SafeErrorResponseMiddleware",  # V4.1 SYS-V4.1-002: intercept ALL 500 errors
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.RbacCacheMiddleware",  # V4.2 SYS-V4.2-006: RBAC request-level cache
    "apps.core.middleware.AuthenticatedMediaMiddleware",  # V4.1 KB-V4.1-007: auth required for /media/
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "knowpilot"),
        "USER": os.environ.get("POSTGRES_USER", "knowpilot"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "knowpilot_password"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        # V4.2 SYS-V4.2-012: Connection pool — persistent DB connections
        # Previous: CONN_MAX_AGE=0 (Django default) → new TCP connection per request
        # ~8-10ms overhead per connection (TCP+auth handshake). At 50 QPS that's
        # 400-500ms/sec wasted on connection setup alone.
        # Now: CONN_MAX_AGE=60 → connections reused for 60 seconds, ~90% reuse rate
        # CONN_HEALTH_CHECKS=True → Django validates stale connections before use
        "CONN_MAX_AGE": int(os.environ.get("CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
        "DISABLE_SERVER_SIDE_CURSORS": env_bool(
            "DISABLE_SERVER_SIDE_CURSORS",
            default=False,
        ),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Custom user model
AUTH_USER_MODEL = "users.User"

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Site framework
SITE_ID = 1

# Django REST Framework
REST_FRAMEWORK = {
    # ``format`` is a business query parameter for compliance and chat exports.
    # Do not reserve it for renderer selection.
    "URL_FORMAT_OVERRIDE": None,
    # V4.2 SYS-V4.2-020: Use custom auth class that checks blacklist table.
    # Default JWTAuthentication only validates signature + expiry, ignoring
    # blacklisted_tokens — meaning blacklisted access tokens remain valid
    # for their full 15-minute lifetime after logout.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.BlacklistCheckingJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # V4.1 SYS-V4.1-004: Added AnonRateThrottle (100/min per IP) alongside UserRateThrottle
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.core.throttling.AuthenticatedReadSustainedThrottle",
        "apps.core.throttling.AuthenticatedReadBurstThrottle",
        "apps.core.throttling.AuthenticatedMutationThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "navigation_read_sustained": "240/minute",
        "navigation_read_burst": "60/10seconds",
        "user_mutation": "30/minute",
        "anon": "100/minute",  # Per IP — prevents mass registration + API abuse
        # V4.2 KB-V4.2-BATCH-004: Dedicated upload throttle rates
        "document_upload": "10/minute",  # Per user — prevents API resource exhaustion
        "batch_upload": "3/minute",  # Per user — stricter limit for batch ZIP uploads
        # V7.0: registration / admin-code throttle — stricter than anon to deter
        # account-farming and admin-code brute force.
        "signup": "5/minute",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
}

# JWT Settings
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# django-allauth
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "optional"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
MFA_ENCRYPTION_KEY = os.environ.get("MFA_ENCRYPTION_KEY", "")
PASSWORD_RESET_TIMEOUT = 30 * 60

# CORS
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

# Celery — V4.1 SYS-V4.1-010: Redis now requires password
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    os.environ.get("REDIS_URL", "redis://:sys_redis_pass_2026@redis:6379/0"),
)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "django-db")
CELERY_BEAT_SCHEDULE = {
    "notification-action-outbox-sweep": {
        "task": "apps.notifications.tasks.sweep_action_outbox",
        "schedule": 60.0,
    },
    # Knowledge iteration spec §4 L3: nightly stale-document scan.
    "knowledge-stale-document-scan": {
        "task": "apps.knowledge.tasks.scan_stale_documents",
        "schedule": 60.0 * 60 * 24,
    },
}
ACTION_OUTBOX_DELIVERY_ADAPTER = os.environ.get(
    "ACTION_OUTBOX_DELIVERY_ADAPTER",
    "",
)
CHAT_COORDINATION_REDIS_URL = os.environ.get("CHAT_COORDINATION_REDIS_URL", CELERY_BROKER_URL)
CHAT_EVENTS_REDIS_URL = os.environ.get(
    "CHAT_EVENTS_REDIS_URL",
    CHAT_COORDINATION_REDIS_URL,
)
CHAT_CAPACITY_REDIS_URL = os.environ.get(
    "CHAT_CAPACITY_REDIS_URL",
    CHAT_EVENTS_REDIS_URL,
)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("RATE_LIMIT_REDIS_URL", CELERY_BROKER_URL),
        "KEY_PREFIX": "knowpilot",
    }
}
CHAT_TURN_IDEMPOTENCY = env_bool("CHAT_TURN_IDEMPOTENCY", default=False)
CHAT_STREAM_V2 = os.environ.get("CHAT_STREAM_V2", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

PROMETHEUS_METRICS_TOKEN = os.environ.get("PROMETHEUS_METRICS_TOKEN", "")
CAPACITY_SEED_ALLOWED = env_bool("CAPACITY_SEED_ALLOWED", default=False)
CHAT_STREAM_V3 = env_bool("CHAT_STREAM_V3", default=False)
CHAT_GENERATION_TARGET_ACTIVE = int(
    os.environ.get("CHAT_GENERATION_TARGET_ACTIVE", "500")
)
CHAT_GENERATION_MAX_OUTSTANDING = int(
    os.environ.get("CHAT_GENERATION_MAX_OUTSTANDING", "625")
)
CHAT_GENERATION_RESERVATION_TTL_SECONDS = int(
    os.environ.get("CHAT_GENERATION_RESERVATION_TTL_SECONDS", "180")
)
CHAT_GENERATION_RETRY_AFTER_SECONDS = int(
    os.environ.get("CHAT_GENERATION_RETRY_AFTER_SECONDS", "5")
)
CHAT_GENERATION_WORKER_CONCURRENCY = int(
    os.environ.get("CHAT_GENERATION_WORKER_CONCURRENCY", "25")
)
CHAT_EVENT_V3_TTL_SECONDS = int(
    os.environ.get("CHAT_EVENT_V3_TTL_SECONDS", "900")
)
CHAT_EVENT_V3_MAXLEN = int(os.environ.get("CHAT_EVENT_V3_MAXLEN", "4096"))
PROVIDER_HTTP_MAX_CONNECTIONS = int(
    os.environ.get("PROVIDER_HTTP_MAX_CONNECTIONS", "32")
)
PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS = int(
    os.environ.get("PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS", "16")
)
PROVIDER_MAX_OUTPUT_TOKENS = int(
    os.environ.get("PROVIDER_MAX_OUTPUT_TOKENS", "2000")
)
validate_capacity_settings(
    target_active=CHAT_GENERATION_TARGET_ACTIVE,
    max_outstanding=CHAT_GENERATION_MAX_OUTSTANDING,
    reservation_ttl_seconds=CHAT_GENERATION_RESERVATION_TTL_SECONDS,
    retry_after_seconds=CHAT_GENERATION_RETRY_AFTER_SECONDS,
    worker_concurrency=CHAT_GENERATION_WORKER_CONCURRENCY,
    event_ttl_seconds=CHAT_EVENT_V3_TTL_SECONDS,
    event_max_length=CHAT_EVENT_V3_MAXLEN,
    provider_max_connections=PROVIDER_HTTP_MAX_CONNECTIONS,
    provider_max_keepalive_connections=PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS,
)
CAPABILITY_NAV = env_bool("CAPABILITY_NAV", default=False)
DEEP_ANSWER_MODE = env_bool("DEEP_ANSWER_MODE", default=False)
THINKING_MODE = env_bool("THINKING_MODE", default=False)
WORKSPACE_CREATION_APPROVAL = env_bool("WORKSPACE_CREATION_APPROVAL", default=False)
# Historical Phase-8 asset copying is permanently outside the v3 template
# contract.  If an old deployment enables it, readiness and template-backed
# creation both fail closed.
TEMPLATE_ASSET_COPY_ENABLED = env_bool("TEMPLATE_ASSET_COPY_ENABLED", default=False)
WORKSPACE_JOIN_V2 = env_bool("WORKSPACE_JOIN_V2", default=False)
WORKSPACE_PERMANENT_DELETE = env_bool("WORKSPACE_PERMANENT_DELETE", default=True)
SPACE_CREDENTIAL_PEPPER_VERSION = int(
    os.environ.get("SPACE_CREDENTIAL_PEPPER_VERSION", "1")
)
try:
    SPACE_CREDENTIAL_PEPPERS = {
        int(version): str(secret)
        for version, secret in json.loads(
            os.environ.get("SPACE_CREDENTIAL_PEPPERS", "{}")
        ).items()
        if str(secret)
    }
except (TypeError, ValueError, json.JSONDecodeError):
    SPACE_CREDENTIAL_PEPPERS = {}
SPACE_INVITATION_ENCRYPTION_KEY = os.environ.get(
    "SPACE_INVITATION_ENCRYPTION_KEY", ""
).strip()
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
# V4.1 SYS-V4.1-009: Task timeout — prevents worker slot exhaustion from large PDFs
# V4.2 KB-V4.2-BATCH-005: Extended timeout for batch ingestion (large ZIP with many docs)
CELERY_TASK_TIME_LIMIT = 1800  # 30 min hard timeout (was 300/5min) — batch docs need more time
CELERY_TASK_SOFT_TIME_LIMIT = 1500  # 25 min soft timeout (was 240/4min)
CELERY_TASK_MAX_RETRIES = 3
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 180,
}
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# V4.2 SYS-V4.2-013: Queue routing — critical tasks get dedicated slots
# Previous: all tasks in single default queue, competing for 4 slots equally.
CELERY_TASK_ROUTES = {
    "apps.chat.tasks.generate_chat_turn_v3": {"queue": "chat_generation"},
    "apps.knowledge.tasks.*": {"queue": "default"},
    "apps.rag.tasks.*": {"queue": "default"},
}

# pgvector
PGVECTOR_DIMENSION = 1024  # Qwen text-embedding-v4

# RAG Settings
RAG_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "500"))
RAG_CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "50"))

# ── V7.0 Identity & Governance ───────────────────────────────────────
# When True, self-registered regular users land in a "pending" state and must
# be approved by an admin in the console before they can sign in.
REQUIRE_SIGNUP_APPROVAL = os.environ.get("REQUIRE_SIGNUP_APPROVAL", "false").lower() == "true"

# When False, public_demo spaces are NOT auto-joinable as guest — the space
# switcher then lists only spaces the user joined / was invited to / administers.
ENABLE_PUBLIC_DEMO_SPACES = os.environ.get("ENABLE_PUBLIC_DEMO_SPACES", "true").lower() == "true"

# Default knowledge-space code a new user is placed in, keyed by Service Line.
# Falls back to DEFAULT_SPACE_CODE ("general") when the line has no mapping.
SERVICE_LINE_DEFAULT_SPACE = {
    "assurance": "assurance-onboarding",
    "consulting": "consulting-onboarding",
    "tax": "tax-onboarding",
    "strategy_transactions": "sat-onboarding",
    "core": "general",
}
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "8"))
RAG_SIMILARITY_THRESHOLD = float(os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.55"))
QWEN_CHAT_MODEL = os.environ.get("QWEN_CHAT_MODEL", "qwen3.6-flash")
RAG_LLM_MODEL = QWEN_CHAT_MODEL
RAG_EMBEDDING_MODEL = os.environ.get("QWEN_EMBEDDING_MODEL", "text-embedding-v4")
RAG_EMBEDDING_DIM = 1024

# DashScope / LiteLLM
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
LITELLM_API_KEY = DASHSCOPE_API_KEY
LITELLM_BASE_URL = os.environ.get(
    "LITELLM_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).rstrip("/")
TEST_PRINCIPAL_LEGACY_ALLOWLIST = tuple(
    value.strip()
    for value in os.environ.get("TEST_PRINCIPAL_LEGACY_ALLOWLIST", "").split(",")
    if value.strip()
)

# File Upload
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "50"))

# V4.2 KB-V4.2-BATCH-004/005/006: Batch upload settings
BULK_UPLOAD_MAX_DOCUMENTS = int(os.environ.get("BULK_UPLOAD_MAX_DOCUMENTS", "100"))  # Max files per ZIP
BULK_UPLOAD_TOTAL_SIZE_MB = int(os.environ.get("BULK_UPLOAD_TOTAL_SIZE_MB", "500"))  # Max ZIP total size MB
MAX_EXTRACTED_TEXT_SIZE = 10_000_000  # 10MB — max extracted text size per document (BATCH-006)
MAX_CHUNKS_PER_DOCUMENT = 500  # Max chunks per document (BATCH-006)
MAX_CHUNKS_PER_BATCH = 5000  # Max total chunks per batch (BATCH-005)

# SSL Verification (for LLM API calls)
SSL_VERIFY = os.environ.get("SSL_VERIFY", "true").lower() == "true"

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "apps.rag": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
