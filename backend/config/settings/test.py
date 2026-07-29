# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from .base import *  # noqa: F401,F403

# Test settings
DEBUG = True
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Use in-memory cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Celery eager mode for tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Hermetic tests must not depend on the host WORKSPACE_PERMANENT_DELETE env var
# (base.py defaults it to True). The capability/archived-scope matrices assert
# the base locked matrix without workspace.delete.permanent; tests that need it
# enabled override this locally via @override_settings(WORKSPACE_PERMANENT_DELETE=True).
WORKSPACE_PERMANENT_DELETE = False
