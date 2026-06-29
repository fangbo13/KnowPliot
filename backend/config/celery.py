"""Celery configuration."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
# V6.0: crawler tasks removed from autodiscovery (Web crawler feature retired).
app.autodiscover_tasks(lambda: ["apps.rag"])
