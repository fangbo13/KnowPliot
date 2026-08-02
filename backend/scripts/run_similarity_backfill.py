"""One-off runner: backfill document similarities + CJK tokens (P1).

Usage (inside backend container):
    python scripts/run_similarity_backfill.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")

import django  # noqa: E402

django.setup()

from apps.knowledge.tasks import backfill_document_similarities  # noqa: E402

print(json.dumps(backfill_document_similarities()))
