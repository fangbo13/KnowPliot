# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

# Django project configuration
#
# Celery bootstrap (official convention): without this import, shared_task
# calls made from web processes (gunicorn) bind to an UNCONFIGURED default
# Celery app that falls back to amqp://localhost — every .delay() dispatched
# from a request (e.g. session-memory summarization) then fails with
# "Connection refused". Importing the app here wires the Redis broker into
# every process that imports the config package.
from .celery import app as celery_app

__all__ = ("celery_app",)
