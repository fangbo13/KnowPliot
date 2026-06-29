# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Celery configuration."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
# V6.0: crawler tasks removed from autodiscovery (Web crawler feature retired).
app.autodiscover_tasks(lambda: ["apps.rag"])
