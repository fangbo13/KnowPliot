# Phase 7A / V9.0 Long-Run Operations Baseline Audit Report

Date: 2026-07-03

Branch: `Version_9.0`

Baseline: `Version_8.2` commit `95f3be5`

Final local commit: produced after this report is staged; see the Git commit on
`Version_9.0` with message `chore(ops): add long-run operations baseline`.

## Scope

Phase 7A establishes a long-run operations baseline for production operations:
safe readiness/liveness summaries, dependency/background-worker visibility,
long-run cleanup configuration, expired export cleanup, and admin dashboard
visibility.

## Implementation evidence

- Extended admin health with top-level `readiness`, `liveness`,
  `dependency_health`, and `background_worker_health` fields.
- Added `long_run_operations` health service with safe `status`, `code`,
  `detail`, `last_checked_at`, `latency_bucket`, retention settings,
  cleanup counts, and backlog counts.
- Added `cleanup_export_jobs` management command with `--dry-run` support.
- The cleanup command marks only expired export jobs and clears result-file
  references after removing existing generated files.
- Extended frontend admin health types and dashboard readiness labels for
  long-run operations.
- Added English and Chinese i18n keys for long-run operations health labels.

## Verification

Commands executed from `D:\Github\Onborading-AI`:

| Gate | Result |
| --- | --- |
| `backend\venv\Scripts\python.exe backend\manage.py test apps.spaces.test_phase7a_long_run_ops --settings=config.settings.local_test -v 1` | PASS, 4 tests |
| `npm --prefix frontend run test -- AdminDashboardPage` | PASS, 1 test |
| `backend\venv\Scripts\python.exe backend\manage.py test apps --settings=config.settings.local_test -v 1` | PASS, 155 tests |
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
- Cleanup currently targets export artifacts only. Broader notification/audit
  retention automation remains for later Phase 7 work.

## Rollback recommendation

Revert the Phase 7A commit. No schema migration is introduced in this phase.
Rollback removes the new health fields, cleanup command, frontend labels, and
guard tests.

## Verdict

Phase 7A / V9.0 is PASS for long-run operations baseline readiness. The
earlier local production-check environment limitation has been removed by the
V9.2 Docker closure retest.
