"""Expire old compliance export jobs and remove their generated files."""

import os

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.chat.models import ComplianceExportJob


class Command(BaseCommand):
    help = "Mark expired export jobs and remove their generated result files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be cleaned without mutating jobs or files.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()
        jobs = ComplianceExportJob.objects.filter(
            expires_at__lt=now,
        ).exclude(status=ComplianceExportJob.STATUS_EXPIRED)
        scanned = jobs.count()
        marked = 0
        removed_files = 0

        for job in jobs:
            result_file = job.result_file
            if dry_run:
                continue
            if result_file and os.path.exists(result_file):
                os.remove(result_file)
                removed_files += 1
            job.status = ComplianceExportJob.STATUS_EXPIRED
            job.result_file = ""
            job.save(update_fields=["status", "result_file", "updated_at"])
            marked += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Export cleanup dry_run={dry_run} scanned={scanned} "
                "marked_expired={marked} removed_files={removed}".format(
                    dry_run=str(dry_run).lower(),
                    scanned=scanned,
                    marked=marked,
                    removed=removed_files,
                )
            )
        )
