# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

import os
import warnings
from pathlib import Path

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
    # apps.crawler retained inert (V6.0): tables/migrations kept, no API/UI/tasks.
    "apps.crawler",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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

# V6.0: Web crawler settings removed — the crawler feature has been retired.
# Knowledge is now sourced only from admin uploads and manually maintained
# documents (see SPEC.MD M4 / M5).

# Django REST Framework
REST_FRAMEWORK = {
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
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "30/minute",
        "anon": "100/minute",  # Per IP — prevents mass registration + API abuse
        # V4.2 KB-V4.2-BATCH-004: Dedicated upload throttle rates
        "document_upload": "10/minute",  # Per user — prevents API resource exhaustion
        "batch_upload": "3/minute",  # Per user — stricter limit for batch ZIP uploads
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

ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_VERIFICATION = "optional"

# CORS
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

# Celery — V4.1 SYS-V4.1-010: Redis now requires password
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://:sys_redis_pass_2026@redis:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
# V4.1 SYS-V4.1-009: Task timeout — prevents worker slot exhaustion from large PDFs
# V4.2 KB-V4.2-BATCH-005: Extended timeout for batch ingestion (large ZIP with many docs)
CELERY_TASK_TIME_LIMIT = 1800  # 30 min hard timeout (was 300/5min) — batch docs need more time
CELERY_TASK_SOFT_TIME_LIMIT = 1500  # 25 min soft timeout (was 240/4min)
CELERY_TASK_MAX_RETRIES = 3
# V4.2 SYS-V4.2-013: Queue routing — critical tasks get dedicated slots
# Previous: all tasks in single default queue, competing for 4 slots equally.
# Now: critical queue for fast/important tasks (crawl, reindex), default for slow tasks (ingest).
# Two workers each handle 2 slots — total capacity unchanged (4 slots), but isolation prevents
# slow ingest tasks from blocking critical crawl/reindex tasks.
CELERY_TASK_ROUTES = {
    # V6.0: crawler queue route removed (Web crawler feature retired).
    "apps.knowledge.tasks.*": {"queue": "default"},
    "apps.rag.tasks.*": {"queue": "default"},
}

# pgvector
PGVECTOR_DIMENSION = 1024  # Qwen text-embedding-v4

# RAG Settings
RAG_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "500"))
RAG_CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "50"))
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "8"))
RAG_SIMILARITY_THRESHOLD = float(os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.55"))
RAG_LLM_MODEL = os.environ.get("QWEN_CHAT_MODEL", "qwen-plus")
RAG_EMBEDDING_MODEL = os.environ.get("QWEN_EMBEDDING_MODEL", "text-embedding-v4")
RAG_EMBEDDING_DIM = 1024

# DashScope / LiteLLM
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
LITELLM_API_KEY = DASHSCOPE_API_KEY
LITELLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

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
