"""Dispatch due v3 workspace purge jobs."""

from django.core.management.base import BaseCommand

from apps.spaces.purge_services import dispatch_due_purges


class Command(BaseCommand):
    help = "Claim and resume due, retention-eligible workspace purge jobs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        results = dispatch_due_purges(limit=options["limit"])
        completed = sum(row.get("status") == "completed" for row in results)
        failed = sum(row.get("status") in {"failed", "not_claimed"} for row in results)
        self.stdout.write(
            self.style.SUCCESS(
                f"workspace purge dispatch: candidates={len(results)} "
                f"completed={completed} failed_or_skipped={failed}"
            )
        )
