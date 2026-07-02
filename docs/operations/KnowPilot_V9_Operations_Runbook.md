# KnowPilot V9 Operations Runbook

This runbook covers the Phase 7 / V9.0–V9.2 long-run operations path.

## health degraded

1. Open the admin dashboard and inspect system health.
2. Check `readiness`, `liveness`, `dependency_health`, and
   `background_worker_health`.
3. If `long_run_operations` is degraded, inspect the listed missing setting
   names and configure retention/cleanup values.
4. Re-run:

```powershell
backend\venv\Scripts\python.exe backend\manage.py check --settings=config.settings.local_test
```

Do not paste secrets, connection strings, prompt text, or export content into
incident notes.

## export job failed

1. Open Answer Quality -> Async exports.
2. Read only the safe error summary and error code.
3. Use Retry for failed jobs when the scope and dataset are correct.
4. Confirm a new retry job is created and the original failed job remains
   unchanged for audit evidence.
5. If generated export files are expired, run:

```powershell
backend\venv\Scripts\python.exe backend\manage.py cleanup_export_jobs --dry-run
backend\venv\Scripts\python.exe backend\manage.py cleanup_export_jobs
```

## SLA backlog

1. Estimate impact before creating notifications:

```powershell
backend\venv\Scripts\python.exe backend\manage.py scan_quality_sla --dry-run
```

2. If the candidate count is expected, run:

```powershell
backend\venv\Scripts\python.exe backend\manage.py scan_quality_sla
```

3. Re-running the command should skip duplicate notifications.

## migration

Before deployment:

```powershell
backend\venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run --settings=config.settings.local_test
backend\venv\Scripts\python.exe backend\manage.py migrate --plan --settings=config.settings.prod
```

Apply migrations only during an approved deployment window.

## deploy check

Run:

```powershell
backend\venv\Scripts\python.exe backend\manage.py check --deploy --settings=config.settings.prod
```

If the local workstation lacks `psycopg` / `psycopg2`, record the result as an
environment limitation and rerun in a production-like environment.

## smoke script

Build-artifact check:

```powershell
backend\venv\Scripts\python.exe backend\scripts\smoke_v9_operations.py --check-build-only --frontend-dist frontend\dist
```

Authenticated API smoke:

```powershell
backend\venv\Scripts\python.exe backend\scripts\smoke_v9_operations.py --frontend-dist frontend\dist --base-url http://127.0.0.1:8000/api/v1/ --token <access-token>
```

The script returns JSON and fails safely without stack traces.

## rollback

1. Stop background workers if the incident involves repeated exports or SLA
   scans.
2. Revert the latest phase commit.
3. Run migration rollback only if the reverted commit introduced migrations and
   the rollback has been approved.
4. Re-run backend checks, frontend build, and V9 smoke.
5. Preserve audit records and failed job evidence for incident review.
