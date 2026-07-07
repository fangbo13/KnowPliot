# Phase 9A Account Security and User Preferences — Incomplete Audit V11.0

Date: 2026-07-04  
Branch: `Version_11.0`  
Baseline: `Version_10.2` / `a4fb4c4`

## Conclusion

**INCOMPLETE / NO-GO.** The local implementation and non-Docker regression
gates pass, but Docker CLI is unavailable in the current environment. Phase 9A
must not be marked actual PASS, committed, or used as the baseline for Phase 9B
until Docker configuration, build, service health, migrations, and smoke tests
have been executed successfully.

## Requirement evidence

- Password change and one-time, non-enumerating reset flow implemented.
- JWT access and refresh token families are bound to server-side sessions.
- Single-session and revoke-other-session operations are enforced by backend authentication.
- TOTP MFA uses an encrypted pending/active secret, one-time challenge, and hashed recovery codes.
- Language, theme, default space, and notification preferences are server persisted.
- Default space authorization and notification preference allowlists are enforced server-side.
- Login MFA, password reset, profile security, MFA setup, and active-session UI paths are present.
- Security events are audited without storing passwords, tokens, MFA secrets, or recovery codes.

## Commands and results

| Gate | Result |
| --- | --- |
| Phase 9A backend security tests | PASS — 4 tests |
| Full backend suite | PASS — 197 tests |
| Django system check | PASS |
| Migration dry-run | PASS — no changes detected |
| Production deploy check | PASS |
| Frontend tests | PASS — 53 tests |
| Frontend i18n check | PASS |
| Frontend typecheck | PASS |
| Frontend production build | PASS |
| `docker compose config` | NOT RUN — Docker CLI unavailable |
| Docker build/start/health/migrations/smoke | NOT RUN — Docker CLI unavailable |

## Negative security coverage

- Unknown notification preference keys are rejected.
- A default space outside the user's effective access is rejected.
- Revoked sessions reject both existing access and refresh tokens.
- Password reset responses do not reveal whether an account exists.
- A reset token cannot be replayed after password change.
- MFA challenge and recovery code replay are rejected.

## Environment and unrelated files

The repository's `backend/venv/pyvenv.cfg` contains a corrupted encoded home
path. Tests were run with the installed Python 3.13 executable and the existing
repository site-packages. Existing user changes to `backend/db.sqlite3`,
`frontend/tsconfig.tsbuildinfo`, token/session files, screenshots, Playwright
artifacts, and other untracked files were not staged or overwritten.

## Required closure

1. Restore Docker CLI availability.
2. Run `docker compose config`.
3. Run `docker compose up -d --build`.
4. Verify PostgreSQL, Redis, Celery, backend, and frontend health.
5. Run migrations and Phase 9A smoke tests in the backend container.
6. Replace this report with the PASS report only after every result is recorded.
