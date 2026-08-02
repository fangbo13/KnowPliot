"""Provision the isolated Phase 8A retrieval benchmark corpus."""

import json

from django.core.management.base import BaseCommand

from apps.rag.evaluation import seed_evaluation_corpus, seed_ragopt_corpus


class Command(BaseCommand):
    help = "Idempotently seed the versioned Phase 8A RAG evaluation corpus."

    def add_arguments(self, parser):
        # RAG optimization spec Phase 0: opt into the expanded bilingual
        # corpus (tables / tolerances / conflict pair) instead of phase8a.
        parser.add_argument("--ragopt", action="store_true")

    def handle(self, *args, **options):
        seeder = seed_ragopt_corpus if options["ragopt"] else seed_evaluation_corpus
        self.stdout.write(json.dumps(seeder(), sort_keys=True))
