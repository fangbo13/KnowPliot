"""Provision the isolated Phase 8A retrieval benchmark corpus."""

import json

from django.core.management.base import BaseCommand

from apps.rag.evaluation import seed_evaluation_corpus


class Command(BaseCommand):
    help = "Idempotently seed the versioned Phase 8A RAG evaluation corpus."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(seed_evaluation_corpus(), sort_keys=True))
