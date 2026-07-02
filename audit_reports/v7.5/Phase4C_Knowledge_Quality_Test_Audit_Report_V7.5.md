# Phase 4C Knowledge Quality Test Audit Report — V7.5

**Date:** 2026-07-02
**Baseline commit:** `4eef4e116e7147ec6e03a23ab9f8c3df85004373`
**Release branch:** `Version_7.5`
**Environment:** Windows, Python 3.13.14, Django local-test settings with
SQLite fallback, Node.js 24.15.0, npm 11.12.1, React/Vite/Vitest frontend.

## Scope and interfaces

- Added durable `knowledge.IngestionJob` records and migration
  `knowledge.0009_ingestionjob`.
- Added safe model-call telemetry in `chat.ModelInvocation` and migration
  `chat.0004_modelinvocation`.
- Added the `ingestion_retry` audit action and migration
  `audit.0010_ingestion_retry_action`.
- Centralized supported upload, batch, re-index, and retry dispatch through
  `enqueue_document_ingestion()`.
- Added administrator-scoped interfaces:
  - `GET /api/v1/admin/ingestion-jobs/`
  - `POST /api/v1/admin/ingestion-jobs/{job_id}/retry/`
  - `GET /api/v1/admin/quality/documents/`
- Extended `GET /api/v1/admin/metrics/` with model/API, token-use, and
  knowledge-quality aggregates.
- Extended the admin dashboard with ingestion state, retry, model/token/error
  metrics, and document-quality drill-down.

## Requirement traceability

| Requirement | Evidence | Result |
| --- | --- | --- |
| Queue state survives Celery result expiry | First-party `IngestionJob` model and lifecycle task tests | PASS |
| Supported ingestion producers create the same durable job shape | Shared enqueue service used by upload, batch, re-index, and retry paths | PASS |
| Failed work is visible only within administrator scope | Cross-organization job-list API test | PASS |
| Retry is safe and history-preserving | Failed-only retry, immutable original row, linked retry row, archived/duplicate guards | PASS |
| Retry is auditable with immutable scope | `ingestion_retry` assertion for organization, space, actor, and success result | PASS |
| Task execution updates durable lifecycle state | Success, zero-chunk failure, and retry-transition task tests | PASS |
| Raw operational exceptions are not exposed in queue telemetry | Job stores the exception class, not the test exception message | PASS |
| Model/API success and failure are measurable | `ModelInvocation` success/failure/timeout/cancelled states and scoped metric assertions | PASS |
| Token use and per-model calls are measurable | Total/average token and grouped model-call assertions | PASS |
| Unused/high-use/stale-source documents are identifiable | Scoped quality API and aggregate metric assertions | PASS |
| Quality drill-down contains useful evidence | Citation count, average relevance, and last-cited timestamp assertions | PASS |
| Admin UI uses dedicated operations APIs | API-client and dashboard component tests | PASS |

## Migrations and schema

```text
python manage.py makemigrations --check --dry-run
No changes detected.

Fresh test database:
audit.0010_ingestion_retry_action OK
chat.0004_modelinvocation OK
knowledge.0009_ingestionjob OK
```

## Verification evidence

```text
backend\venv\Scripts\python.exe backend\manage.py test apps \
  --settings=config.settings.local_test -v 1
Result: 126 tests passed in 106.865s.

backend\venv\Scripts\python.exe backend\manage.py check \
  --settings=config.settings.local_test
Result: passed with 3 known django-allauth deprecation warnings.

backend\venv\Scripts\python.exe backend\manage.py makemigrations \
  --check --dry-run --settings=config.settings.local_test
Result: No changes detected.

npm --prefix frontend run test
Result: 6 test files, 49 tests passed.

npm --prefix frontend run check:i18n
Result: 51 source files checked; all keys present.

npm --prefix frontend run typecheck
Result: passed.

npm --prefix frontend run build
Result: production build passed; 3,594 modules transformed.
```

## Negative and failure-mode testing

- An organization administrator cannot list or retry another organization's
  ingestion jobs; the cross-scope retry returns 404.
- Queued, processing, retrying, and succeeded jobs cannot use the failed-job
  retry action.
- A document with existing active ingestion work rejects duplicate retry with
  HTTP 409.
- Archived documents reject retry.
- The original failed record remains terminal and unchanged after retry.
- A retry dispatch failure is converted into a terminal durable failure rather
  than an invisible queue loss, returns a sanitized 503, and records a scoped
  `failure` audit result.
- A zero-chunk pipeline result is terminal failure and never reports success.
- Cancelled model invocations are excluded from API-error denominators.
- Foreign-space model calls and documents are excluded from scoped metrics and
  quality results.
- Raw exception messages, prompts, answers, and credentials are not stored in
  `ModelInvocation`.

## Known warnings and residual risk

- Three django-allauth setting deprecations predate Phase 4C and do not block
  this gate.
- Vite retains the existing mixed dynamic/static i18n import warning and
  bundle-size warnings.
- The task lifecycle tests intentionally use synthetic documents without media
  files; the expected content-hash warning does not affect lifecycle evidence.
- This workstation audit uses SQLite and eager/mocked Celery execution. Live
  PostgreSQL/pgvector, Redis, Celery worker concurrency, broker redelivery,
  load, and recovery remain production-hardening gates.
- Token counts use the application's current estimator and are operational
  telemetry, not provider billing records.
- Pre-existing user-owned `db.sqlite3`, TypeScript build metadata, screenshots,
  deleted token files, and untracked assets were not included in the phase
  change set.

## Version correction

Phase 4A, Phase 4B, and Phase 4C are release slices of V7.5. Their reports are
stored together under `audit_reports/v7.5/`; current SPEC, progress, task plan,
and long-term roadmap nodes no longer identify completed Phase 4 work as V8.
Phase 5 is the first planned V8 release family.

## Verdict

**PASS** — Phase 4C satisfies the scoped ingestion visibility, safe retry,
model/API/token telemetry, and knowledge-quality analytics gate. Phase 4 is
complete at V7.5. Phase 5 may begin in a later approved work session.
