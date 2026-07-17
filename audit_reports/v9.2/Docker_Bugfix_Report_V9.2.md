# Docker Bugfix Report / V9.2 Closure

Date: 2026-07-03

Branch: `Version_9.2`

## Summary

The Docker validation pass found real environment/configuration defects that
kept the V9 phase line from being cleanly PASS in a Docker-backed run. All
blocking defects below were fixed or repaired and then retested.

## Fixed issues

| ID | Symptom | Root cause | Fix | Verification |
| --- | --- | --- | --- | --- |
| BUG-V9.2-001 | `check --deploy --settings=config.settings.prod` previously failed on missing PostgreSQL driver | Local `backend\venv` did not have `psycopg` installed even though `backend/pyproject.toml` declares `psycopg[binary]` | Installed `psycopg[binary]>=3.2` into `backend\venv` | Prod deploy check now returns `System check identified no issues` |
| BUG-V9.2-002 | Local/prod Django checks emitted django-allauth deprecation warnings | Deprecated `ACCOUNT_EMAIL_REQUIRED`, `ACCOUNT_USERNAME_REQUIRED`, and `ACCOUNT_AUTHENTICATION_METHOD` settings remained in `base.py` | Replaced with `ACCOUNT_LOGIN_METHODS` and `ACCOUNT_SIGNUP_FIELDS` | Local check, prod deploy check, and 163 backend tests pass with no system-check issues |
| BUG-V9.2-003 | Prod deploy check emitted HSTS warning | `config.settings.prod` did not set `SECURE_HSTS_SECONDS` | Added environment-overridable HSTS settings in `prod.py` | Prod deploy check returns no issues |
| BUG-V9.2-004 | Frontend production build emitted Vite warnings | `i18n` was dynamically imported in `App.tsx`/`LoginPage.tsx` while statically imported elsewhere; Ant Design chunk exceeded default threshold | Switched i18n usage to static imports and set explicit `chunkSizeWarningLimit` for the known Ant Design bundle | `npm --prefix frontend run build` exits 0 with no warnings |
| BUG-V9.2-005 | Docker backend failed migrations with `must be owner of table audit_auditlog` | Existing local PostgreSQL volume tables were owned by old role `ey_onboarding`, while current compose connects as `knowpilot` | Reassigned public schema table/sequence/type ownership to `knowpilot` | Backend starts, migrations apply, `showmigrations` shows current audit/chat/knowledge/notifications migrations applied |
| BUG-V9.2-006 | Docker admin health reported `celery=down` even though worker was running | Health check used global `celery.current_app`, which attempted the default localhost broker instead of the project Celery app | Changed health probe to import `config.celery.app` and ping with the configured Redis broker | Docker admin health reports `celery=up`; V9 smoke health check PASS |
| BUG-V9.2-007 | Docker admin health reported `security_config=degraded` for local HTTP compose profile | Docker validation runs behind local nginx over HTTP, while production SSL checks belong to `config.settings.prod` | Added `HEALTH_REQUIRE_HTTPS_SECURITY=False` in `config.settings.docker`; prod remains strict | Docker health reports `security_config=configured`; prod deploy check remains no issues |
| BUG-V9.2-008 | Celery emitted a privileged-worker startup warning in the Docker worker container | Compose started the worker without an explicit non-root UID/GID | Updated the worker command to run with `--uid=nobody --gid=nogroup` | Restarted the worker, reran Docker health and V9 smoke, and confirmed recent Celery logs contain no privileged-worker warning |

## Retest evidence

- Backend full suite: PASS, 163 tests.
- Focused health suite: PASS, 7 tests.
- Local Django check: PASS, no issues.
- Production deploy check: PASS, no issues.
- Migration dry-run: PASS, no changes detected.
- Frontend Vitest: PASS, 49 tests.
- i18n check: PASS, 52 source files.
- TypeScript check: PASS.
- Frontend build: PASS, no Vite warnings.
- Docker Compose services: db/redis/backend/celery-worker/frontend running.
- Docker admin health: PASS, `overall=up`, `readiness=up`, Celery up.
- V9 Docker smoke: PASS for health, admin metrics, quality report, export jobs,
  notification feed, and review queue.
- Celery runtime logs: PASS, no root/security warning after non-root command
  change.
- Browser screenshots: saved under `output/playwright/`.

## Not carried as residual non-PASS

- No Docker/SPEC validation defect remains open in this pass. Historical
  environment-constraint results in earlier phase reports are superseded by the
  current Docker-backed retest evidence and updated phase-report closures.

## Verdict

All blocking Docker/SPEC validation bugs found during this pass are fixed and
verified. No phase-level non-PASS environment limitation remains for the current
V9.2 closure state.
