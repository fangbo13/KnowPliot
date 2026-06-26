"""Crawler app configuration — V4.1 KB-V4.1-011~017."""

from django.apps import AppConfig


class CrawlerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crawler"
    verbose_name = "Web Crawler"
