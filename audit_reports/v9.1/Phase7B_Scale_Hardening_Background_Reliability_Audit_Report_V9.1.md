# Phase 7B / V9.1 Scale Hardening and Background Reliability Audit Report

Date: 2026-07-03

Branch: `Version_9.1`

Baseline: `Version_9.0` commit `d3ba7c1`

Final local commit: produced after this report is staged; see the Git commit on
`Version_9.1` with message
`feat(ops): harden background reliability and scale paths`.

## Scope

Phase 7B hardens background reliability and scale-sensitive operations:
failed export retry, SLA scanner dry-run/statistics, duplicate notification
avoidance visibility, scale-path indexes, and frontend retry affordances.

## Implementation evidence

- Added `ComplianceExportJob.retry_of` to preserve lineage for export retries.
- Added `POST /api/v1/admin/reports/export-jobs/{id}/retry/` for failed export
  jobs, scoped by existing export job access rules.
- Retry creates a new job, completes it through the existing export generation
  path, and preserves the original failed job status/error evidence.
- Added `export_job_retry` audit action.
- Added `--dry-run` and summary statistics to `scan_quality_sla`, reporting
  candidates/created/skipped/errors without creating notifications or audit
  logs during dry-run.
- Added scale-path indexes for notification feed, scoped audit queries, and
  ingestion job status/space lookups; export job scale index already existed.
- Extended the Answer Quality export job table with safe error summaries and a
  retry action for failed jobs.

## Verification

Commands executed from `D:\Github\Onborading-AI`:

| Gate | Result |
| --- | --- |
| `backend\venv\Scripts\python.exe backend\manage.py test apps.chat.test_phase7b_scale_reliability --settings=config.settings.local_test -v 1` | PASS, 4 tests |
| `backend\venv\Scripts\python.exe backend\manage.py test apps --settings=config.settings.local_test -v 1` | PASS, 159 tests |
| `backend\venv\Scripts\python.exe backend\manage.py check --settings=config.settings.local_test` | PASS, no issues after V9.2 Docker closure config cleanup |
| `backend\venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run --settings=config.settings.local_test` | PASS, no changes detected |
| `npm --prefix frontend run test` | PASS, 49 tests |
| `npm --prefix frontend run check:i18n` | PASS |
| `npm --prefix frontend run typecheck` | PASS |
| `npm --prefix frontend run build` | PASS, no Vite warnings after V9.2 Docker closure frontend cleanup |
| `backend\venv\Scripts\python.exe backend\manage.py check --deploy --settings=config.settings.prod` | PASS, no issues after installing `psycopg[binary]` and adding prod HSTS settings |

## Known warnings and residual risk

- V9.2 Docker closure removed the earlier local django-allauth deprecation
  warnings, Vite build warnings, and missing PostgreSQL driver limitation.
- Export retry currently executes through the local immediate-completion path;
  a future Celery-backed worker can reuse the same job lineage and audit
  contract.

## Rollback recommendation

Revert the Phase 7B commit. Database rollback drops the added retry lineage
field and scale-path indexes. Original failed export job evidence is preserved
by design.

## Verdict

Phase 7B / V9.1 is PASS for scale-hardening and background reliability. The
earlier local production-check environment limitation has been removed by the
V9.2 Docker closure retest.
