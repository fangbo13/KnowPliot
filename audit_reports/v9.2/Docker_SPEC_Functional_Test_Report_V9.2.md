# Docker SPEC Functional Test Report / V9.2 Closure

Date: 2026-07-03

Branch: `Version_9.2`

Runtime under test:

- Docker Compose services: PostgreSQL pgvector, Redis, backend, Celery worker,
  frontend nginx.
- Frontend URL: `http://127.0.0.1:3003`
- Backend URL: `http://127.0.0.1:8000`
- QA admin account: `codex.qa.admin@example.test`

## Summary

Result: PASS.

This report supersedes the earlier local-environment limitation notes for the
current closure audit. The local Python virtual environment now has
`psycopg[binary]` installed, production deploy check returns no issues, Docker
health is `up`, V9 smoke passes against the running Docker backend, frontend
build completes without Vite warnings, and browser validation screenshots were
captured for the newly added SPEC functionality.

## Docker environment

| Check | Result |
| --- | --- |
| `docker compose up -d` | PASS; db/redis/backend/celery-worker/frontend running |
| `docker compose exec -T backend python manage.py check --settings=config.settings.docker` | PASS; no issues |
| `docker compose exec -T backend python manage.py makemigrations --check --dry-run --settings=config.settings.docker` | PASS; no changes detected |
| Docker admin health API | PASS; `overall=up`, `readiness=up`, database/redis/celery/vector DB all up |
| V9 smoke API against Docker backend | PASS; health, admin metrics, quality report, export jobs, notifications, review queue all HTTP 200 |
| Celery worker runtime | PASS; worker starts with `--uid=nobody --gid=nogroup`; recent Docker logs contain no root/security warning |

Docker volume repair note: the existing local PostgreSQL volume contained
tables owned by an old `ey_onboarding` role. Ownership was reassigned to
`knowpilot` so current migrations can run normally with the compose user.

## Automated gates

Commands executed from `D:\Github\Onborading-AI` unless noted.

| Gate | Result |
| --- | --- |
| `backend\venv\Scripts\python.exe backend\manage.py test apps --settings=config.settings.local_test -v 1` | PASS, 163 tests |
| `backend\venv\Scripts\python.exe backend\manage.py test apps.spaces.test_phase6a_hardening apps.spaces.test_phase7a_long_run_ops --settings=config.settings.local_test -v 1` | PASS, 7 focused health tests |
| `backend\venv\Scripts\python.exe backend\manage.py check --settings=config.settings.local_test` | PASS, no issues |
| `backend\venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run --settings=config.settings.local_test` | PASS, no changes detected |
| `backend\venv\Scripts\python.exe backend\manage.py check --deploy --settings=config.settings.prod` | PASS, no issues |
| `.\node_modules\.bin\vitest.cmd run --pool=threads` from `frontend/` | PASS, 49 tests |
| `npm --prefix frontend run check:i18n` | PASS, 52 source files checked |
| `npm --prefix frontend run typecheck` | PASS |
| `npm --prefix frontend run build` | PASS, no Vite warnings |

The default `npm --prefix frontend run test` command timed out once on Windows
without producing test output. Residual local Node worker processes were
stopped, then the same Vitest suite was executed directly via the local
`vitest.cmd` binary and passed 49/49.

## Browser validation evidence

Screenshots captured with Playwright CLI and stored under `output/playwright/`:

| Screenshot | Evidence |
| --- | --- |
| `02-chat-welcome.png` | Docker frontend loads after QA admin login; chat shell and welcome flow render |
| `04-admin-dashboard-health-up.png` | Admin Dashboard loads from Docker frontend after health repair |
| `05-answer-quality-empty.png` | Answer Quality page loads with review queue, quality summary, async export controls |
| `06-answer-quality-export-job.png` | Async feedback export creates a `succeeded` job with Download action |
| `07-notifications-feed.png` | Notification bell shows export-complete notification |
| `08-knowledge-base.png` | Knowledge Base lists protected documents and Download/Reindex/Archive actions |

## SPEC feature coverage

| SPEC area | Browser/API evidence | Result |
| --- | --- | --- |
| V9 long-run operations health | Admin health API reports `overall=up`, `readiness=up`, `long_run_operations.status=configured` | PASS |
| Background worker readiness | Admin health API reports `celery=up` and `background_worker_health.status=up` | PASS |
| Production deploy readiness | `config.settings.prod` deploy check returns no issues after installing `psycopg[binary]` | PASS |
| Async export operations | Answer Quality browser flow creates a succeeded export job and notification | PASS |
| Quality report / review queue APIs | V9 smoke returns HTTP 200 for quality report and review queue | PASS |
| Notifications | Browser notification popover shows export-complete message; V9 smoke notification feed HTTP 200 | PASS |
| Knowledge Base protected actions | Browser shows Knowledge Base document table with protected Download/Reindex/Archive actions | PASS |
| Frontend build integrity | Host production build and Docker frontend rebuild completed from current `frontend/dist` | PASS |

## Residual risk

- The existing Docker volume required ownership repair because it was created
  by an older role. Fresh compose volumes initialized from the current
  `docker-compose.yml` should not reproduce that owner mismatch.

## Verdict

PASS. Current Docker validation, automated gates, browser screenshots, and API
smoke evidence prove the V9.2 SPEC functionality runs end-to-end without the
previous phase-level non-PASS environment limitation.
