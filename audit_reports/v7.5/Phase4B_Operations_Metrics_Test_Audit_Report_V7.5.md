# Phase 4B Operations and Metrics Test Audit Report — V7.5

**Date:** 2026-07-02

**Baseline commit:** `d06683f`

**Phase commit subject:** `feat(admin): add health metrics and document lifecycle`

**Environment:** Windows, Django local-test settings with SQLite fallback,
Python virtual environment, React/Vite/Vitest frontend.

## Scope and interfaces

- Added authenticated `GET /api/v1/admin/health/`.
- Added authenticated and administrator-scoped `GET /api/v1/admin/metrics/`.
- Added `stale` and `archived` document states plus migration
  `knowledge.0008_document_lifecycle_statuses`.
- Added idempotent `mark_stale_documents` management command.
- Existing document `DELETE` now archives by default. `?hard=true` is
  platform-superuser-only and rejects cited documents with HTTP 409.
- Archived documents are hidden from default lists, excluded from Phase 3C
  retrieval, and cannot be re-indexed.

## Requirement traceability

| Requirement | Evidence | Result |
| --- | --- | --- |
| Health uses real checks, not audit-log inference | Dedicated backend collector, API tests, dashboard component test | PASS |
| Database/Redis/Celery/vector/LLM states are honest | Bounded checks and explicit configured/not-configured states | PASS |
| Metrics respect administrator scope | Cross-organization metrics test | PASS |
| Usage and quality metrics are calculated | Session/question/citation/latency/no-evidence/citation-coverage assertions | PASS |
| Ingestion and stale signals are visible | Processing/failed/stale/expiring aggregates | PASS |
| Archive preserves answer provenance | Chunk and citation preservation test | PASS |
| Hard deletion is tightly restricted | Member 403, cited superuser 409, uncited superuser deletion tests | PASS |
| Stale transition is idempotent | Two-run management-command test | PASS |
| Archived documents stay retired | Default-list exclusion and re-index conflict tests | PASS |
| Frontend uses real operations APIs | API and dashboard component tests | PASS |
| Lifecycle labels/actions are localized | English/Chinese keys and i18n validation | PASS |

## Verification evidence

```text
Backend focused Phase 4B: 10 tests passed.

Backend full explicit regression:
117 tests passed in 105.253s.

Django system check:
Passed with 3 previously documented django-allauth deprecation warnings.

Migration dry-run:
No changes detected.

Python compileall:
Exit code 0.

Frontend:
6 test files, 47 tests passed.
i18n validation passed.
TypeScript typecheck passed.
Vite production build passed.
```

## Negative and failure-mode testing

- Regular members receive 403 from health and metrics endpoints.
- A health-response audit-write failure is logged but does not turn the
  diagnostics response into HTTP 500.
- Cross-organization data is excluded from scoped metrics.
- Members cannot request physical deletion.
- Cited sources cannot be physically deleted even by a platform superuser.
- Archived documents are hidden by default and cannot be re-indexed.
- The frontend test proves the dashboard does not query `/audit/logs/` to infer
  service status.

## Known warnings and residual risk

- The three django-allauth setting deprecations predate this phase.
- Vite reports the existing dynamic/static i18n import and large-chunk warnings.
- No live PostgreSQL/pgvector, Redis, or Celery worker was available in this
  workstation audit. The endpoint reports unavailable services honestly;
  live dependency integration remains a production-hardening gate.
- Failed-task listing/retry, model/API error rate, token usage, and deeper
  document-quality analytics remain Phase 4C.
- `SPEC.MD` contains legacy non-UTF-8 bytes and was not rewritten to avoid an
  unsafe whole-file encoding conversion. The UTF-8 implementation tracker and
  this versioned audit are the current evidence.
- Pre-existing user-owned `db.sqlite3`, build metadata, screenshots, token-file
  deletions, and untracked assets were not staged.

## Verdict

**PASS** — Phase 4B MVP satisfies its operations, scoped metrics, and governed
document-lifecycle gate. Phase 4C may begin in a later approved work session.
