# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""
Local test settings - use SQLite instead of PostgreSQL for quick testing
本地测试设置 - 使用SQLite替代PostgreSQL进行快速测试
"""
from config.settings.base import *  # noqa: F401, F403

# Override database to use SQLite
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Disable Celery for testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Set DEBUG
DEBUG = True

# Allow all hosts for local testing
ALLOWED_HOSTS = ["*"]

# CORS - allow all for local testing
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"]

# Disable throttling for testing
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405

# Logging - more verbose
LOGGING["loggers"]["apps.rag"]["level"] = "DEBUG"  # noqa: F405
