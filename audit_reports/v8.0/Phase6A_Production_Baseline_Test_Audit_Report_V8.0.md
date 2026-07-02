# Phase 6A Production Baseline Test Audit Report V8.0

Date: 2026-07-03  
Branch: `Version_8.0`  
Baseline: `Version_7.8` commit `eb3571d`  
Final status: PASS with documented local production-check environment limitation

## Scope

Phase 6A establishes the production hardening baseline:

- Expanded admin health payload with production readiness checks.
- Stable safe API error response shape with `detail`, `code`, and backward-compatible `error`.
- Admin dashboard readiness detail display.
- Bilingual labels for newly surfaced readiness fields.

## Implementation Evidence

Changed areas:

- `backend/apps/spaces/admin_operations.py`
- `backend/apps/core/exceptions.py`
- `backend/apps/spaces/test_phase6a_hardening.py`
- `frontend/src/api/admin.ts`
- `frontend/src/pages/admin/AdminDashboardPage.tsx`
- `frontend/src/i18n/locales/en/common.json`
- `frontend/src/i18n/locales/zh/common.json`

No schema migration was required for Phase 6A.

## Requirement Traceability

| Requirement | Evidence |
| --- | --- |
| Health distinguishes configured/degraded/down | `collect_system_health()` now includes readiness services and degrades overall when any service is degraded |
| Migration status | `migrations` service checks unapplied migrations with `MigrationExecutor` |
| Static/media config | `static_files` and `media_storage` services report configured/degraded |
| Security config without secret leakage | `security_config` reports missing setting names only; tested |
| Export limit visibility | `export_limits.max_sync_rows` exposes configured synchronous export cap |
| Stable API errors | custom exception handler returns `detail`, `code`, `error`, `errors`; tested for permission denied |
| Admin UI readiness detail | dashboard renders new health services dynamically |
| i18n | English and Chinese readiness labels added; i18n check PASS |

## Command Results

```text
backend\venv\Scripts\python.exe backend\manage.py test apps.spaces.test_phase6a_hardening --settings=config.settings.local_test -v 1
Result: PASS, 3 tests
```

```text
backend\venv\Scripts\python.exe backend\manage.py test apps.spaces.test_phase6a_hardening apps.spaces.test_phase4b_operations --settings=config.settings.local_test -v 1
Result: PASS, 13 tests
```

```text
backend\venv\Scripts\python.exe backend\manage.py test apps --settings=config.settings.local_test -v 1
Result: PASS, 145 tests
```

```text
backend\venv\Scripts\python.exe backend\manage.py check --settings=config.settings.local_test
Result: PASS with known allauth deprecation warnings
```

```text
backend\venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run --settings=config.settings.local_test
Result: PASS, no changes detected
```

```text
npm --prefix frontend run test
Result: PASS, 49 tests
```

```text
npm --prefix frontend run check:i18n
Result: PASS
```

```text
npm --prefix frontend run typecheck
Result: PASS
```

```text
npm --prefix frontend run build
Result: PASS
```

```text
backend\venv\Scripts\python.exe backend\manage.py check --deploy --settings=config.settings.prod
Result: ENVIRONMENT-LIMITED FAIL
Reason: local virtual environment lacks PostgreSQL driver (`psycopg` / `psycopg2`), so Django cannot initialize the production database backend.
```

## Warnings

- Django continues to report known allauth deprecation warnings under local test settings.
- Vite continues to report known chunk-size and i18n dynamic/static import advisories.
- Production deploy check was executed but cannot pass in this local venv without PostgreSQL driver installation.

## Residual Risks

- Phase 6A does not add async export or SLA notifications; those are Phase 6B.
- Health checks report configuration readiness but do not provision missing production dependencies.
- `check --deploy` requires a production-like environment with PostgreSQL driver installed for a true PASS.

## Audit Conclusion

Phase 6A / V8.0 passes targeted tests, full backend regression, frontend regression, i18n, typecheck, build, Django system check, and migration consistency. The production deploy check was run and failed only because this local venv lacks PostgreSQL driver support; this is recorded as an environment limitation, not a false PASS.
