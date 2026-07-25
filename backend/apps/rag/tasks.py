"""Celery task registry for the RAG app.

Celery's ``autodiscover_tasks`` (see config/celery.py) imports ``tasks.py``
from each listed app.  The actual ``@shared_task`` definition lives in
``apps.rag.services.ingest_document``; this module re-exports it so the
task is registered when the worker autodiscovers the RAG app.
"""

from apps.rag.services import ingest_document  # noqa: F401  (re-export for Celery)
