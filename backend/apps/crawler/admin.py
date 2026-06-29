"""Crawler admin — V6.0: Web crawler feature retired.

The crawler models (CrawledDocument, CrawlTaskLog) are retained inert so that
existing `crawler_*` tables and migration history remain valid, but the crawler
feature is no longer part of the product: no API routes, no Celery tasks, no
frontend, and no Django admin registration. Knowledge is sourced only from
admin uploads and manually maintained documents.

To fully drop the historical tables in a future release, add a migration that
removes the models and then delete this app from INSTALLED_APPS.
"""

# V6.0: Intentionally no admin registrations — crawler models are hidden.
