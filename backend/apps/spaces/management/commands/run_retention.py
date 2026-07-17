from django.core.management.base import BaseCommand
from apps.spaces.retention import run_retention


class Command(BaseCommand):
    help = "Preview or safely execute governed retention; default is dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=365)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        if options["days"] < 1:
            raise ValueError("--days must be positive")
        self.stdout.write(str(run_retention(days=options["days"], execute=options["execute"])))
