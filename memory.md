# KnowPilot Optimization Delivery Memory

- Last updated: 2026-07-17 (Asia/Shanghai)
- Branch: `codex/knowpilot-optimization`
- Handoff commit: the commit containing this file; resolve it with `git rev-parse HEAD`
- Primary specification: `docs/specs/2026-07-16-knowpilot-optimization-spec.md` v2; summarized by `SPEC.MD` sections 15–16
- Deployment target: 筼筜 (remote runtime; host, path, credentials, and provider configuration were not supplied)
- Environment state: not started and not contacted
- Delivery state: implementation and local verification complete; deployment validation pending

## 1. Next action

In an authorized 筼筜 deployment window, rehearse the additive sequence
`chat.0013`, `spaces.0008`, and `chat.0014` through `chat.0016` against a
PostgreSQL backup/clone, then run authenticated Redis, provider, capability, and
browser smoke checks with all new rollout flags still disabled. Do not infer
deployment credentials or start services from this handoff.

## 2. Locked decisions and invariants

- Reselecting the active session is a no-op. Obsolete session/message requests
  are aborted and stale responses cannot replace the current view.
- One `(user, client_request_id)` creates at most one user question. The frontend
  never automatically retries a question POST; replay/status recovery reuses the
  durable `ChatTurn`.
- Session-scoped renewable Redis leases prevent concurrent generation. Partial
  answers survive disconnects and every stream has an explicit recoverable or
  terminal state.
- Regenerate reuses the original question and creates a new assistant version.
  Branch creates a new session through a selected message. Neither duplicates
  the user question.
- Authorization is enforced by server capability and tenant scope. Frontend
  gates are UX only; scoped administrators cannot call global authority paths.
- Fast is the default answer mode. Deep is opt-in, capability/policy governed,
  and raw provider reasoning is never persisted, logged, audited, or returned.
- Conversation shares are authenticated, read-only, tenant-scoped, expire after
  seven days, and are revocable by their owner even after membership loss.
- Citation links are rendered only for server-issued internal source paths and
  only when the server grants document-download capability.
- The design direction is one warm editorial token system, consistent spacing
  and surfaces, restrained functional motion, and global reduced-motion support.
- Current product decisions require authenticated production join codes,
  versioned template overrides, single-space chat retrieval, spaces for long-
  running/confidential projects, and summarized answers with cited excerpts
  bounded to 280 plain-text characters.
- No secrets, PII, raw prompts/reasoning, connection strings, or invented 筼筜
  details belong in this file.

## 3. Implemented product surface

### Chat stability and recovery

- Durable `ChatTurn` identity, atomic question creation, session-scoped stream
  state, Redis lease renewal/release, SSE v1/v2 compatibility, monotonic replay,
  bounded GET-only recovery, safe error codes, partial-content retention, and
  session `updated_at` touches are implemented.
- Client stream budgets are 20 seconds for connection, 45 seconds idle, 180
  seconds total, and 5 seconds per recovery request. Server coordination uses a
  180-second lease renewed every 30 seconds and a 15-minute replay buffer.
- The final audit fixed the metrics allowlist so boolean
  `idempotency_rollout_enabled` is persisted beside the bounded idempotency
  disposition; integer lookalikes and unsupported metric keys remain rejected.
- History is server-filtered by query, time, recovery status, and opaque cursor.
  Search covers titles and message content without loading all sessions. Ordering
  is stable on pinned state, update time, and ID.
- History URL state is restorable. Obsolete list/detail requests are cancelled.
  Long conversations load older message cursor pages and remain chronological.
- Explicit history states cover loading, failure/retry, empty results, partial,
  recovering, recovered, failed, and terminal conversations.
- Session lists, message history, session detail, and export re-check current
  space capabilities. Guest/revoked access cannot recover protected history or
  use export merely because the session is still owned by that user.
- Active Turn status/replay remains available to an owner through effective
  `chat.ask`, including direct membership, public-demo guest access, and
  platform/governance scope. Terminal Turn recovery, regenerate, and branch
  require the same history policy exposed as `chat.history` and implemented as
  `CHAT_VIEW_HISTORY`/`chat.view_history`.

### Regenerate, versions, branch, citations, and sharing

- `POST /api/v1/chat/messages/{message_id}/regenerate/` reuses the persisted
  question and creates one idempotent Turn/new assistant version.
- Message versions have a durable group, monotonic version number, supersession
  link, and database constraints enforcing one version number and one current
  message per group. Normal reads hide superseded assistant versions.
- `POST /api/v1/chat/messages/{message_id}/branch/` is idempotent and copies only
  the selected/current path into a new same-space session. Each copied message
  receives an independent version group; citation scope is preserved.
- Citation serialization strips markup, bounds snippets, and emits an internal
  source URL only after server-side `DOCUMENT_DOWNLOAD` authorization.
- Share collection/create/revoke/view APIs persist seven-day links. Shared views
  are authenticated, read-only, sanitized, limited to current assistant versions,
  and non-disclosing for expired, revoked, cross-organization, or inaccessible
  tokens.

### Roles, consoles, workspace workflows, and governance

- Platform, organization, business-line, and workspace consoles/routes are
  capability-derived. Compatibility navigation remains behind default-off flags.
- User workflows include workspace discovery, member/guest access requests with
  reason/status, and explicit failure states.
- Workspace administrators can review reasons, approve or reject with a required
  reason, and use archive, restore, clone, business-line transfer, and owner
  transfer workflows with confirmations.
- Platform administrators manage model profiles. Organization administrators
  can read enabled profiles and create immutable model-policy revisions only in
  their own organization; cross-organization binding is rejected server-side.
- Fast/deep profile binding, deep thinking budget, retrieval count, model/mode
  snapshots, safe processing phases, and metrics are connected to generation.

### Design convergence

- Warm editorial tokens, semantic page/surface primitives, consistent hierarchy,
  whitespace, responsive action layout, focus states, restrained transitions,
  and `prefers-reduced-motion` behavior are applied to the prioritized chat,
  history, login, quality, template, and scoped-console surfaces.
- No live visual claim was made because starting the application server was
  explicitly out of scope. Static component/design tests and production build
  cover the implementation only.

## 4. Database and compatibility state

- `chat.0013_chatturn`: durable Turn identity, status, scope, sequence, and
  `(user, client_request_id)` uniqueness.
- `spaces.0008_organizationmembership_effectiveness`: active/expiry scope state.
- `chat.0014_chatturn_metrics_and_model_lengths`: safe Turn metrics and model
  identifier lengths.
- `chat.0015_message_versions_and_session_branches`: message lineage/current
  constraints, branch identity, and `ChatTurn.question_message` as a reusable
  foreign key. Its data migration assigns every existing message a unique
  version group in batches before adding non-null/unique constraints.
- `chat.0016_conversation_share`: tenant-scoped durable share/token/expiry/revoke
  state and owner request idempotency.
- Migrations are additive. Do not reverse `0013`-`0016` after production writes
  without a separate retention/export decision.
- v1 streaming and legacy navigation compatibility remain available for the
  rollout window. Do not remove them in the deployment change.

## 5. Feature flags and rollout

All new rollout flags default to false in `.env.example`:

1. `CHAT_TURN_IDEMPOTENCY=false`
2. `CHAT_STREAM_V2=false`
3. `CAPABILITY_NAV=false` and `VITE_CAPABILITY_NAV=false`
4. `DEEP_ANSWER_MODE=false` and `VITE_DEEP_ANSWER_MODE=false`

Important: durable Turn duplicate suppression is a safety invariant and remains
active regardless of `CHAT_TURN_IDEMPOTENCY`. That flag is an operational rollout
marker recorded in safe Turn metrics; it must not be used to re-enable duplicate
question creation.

Recommended deployment sequence:

1. Back up PostgreSQL and rehearse/apply additive migrations through `0016`.
2. Deploy backend and frontend with every flag false; validate v1 chat, recovery,
   scope denial, share expiry/revoke, and migration row counts.
3. Enable the idempotency rollout marker and observe duplicate/conflict metrics.
4. Enable `CHAT_STREAM_V2`; verify Redis lease/replay, disconnect recovery, and
   safe terminal events before expanding traffic.
5. Enable backend and frontend capability navigation together; verify one user
   for each platform/org/business/workspace role and revoked/expired membership.
6. Bind validated model profiles, then enable backend/frontend deep answer mode;
   confirm guests remain fast-only and no reasoning text reaches logs or clients.

Rollback flags in reverse order. Preserve additive tables/columns and existing
shares/Turns. A v2 rollback returns to v1; a capability-navigation rollback uses
legacy routes; a deep rollback preserves fast mode. If the Redis lease itself
must be removed, redeploy the reviewed pre-lease backend instead of misusing a
stream flag.

## 6. Verification ledger

Fresh final evidence from 2026-07-17:

| Gate | Result | Limitation |
|---|---:|---|
| Django complete suite | 365/365 passed | Local `config.settings.local_test` and SQLite; no PostgreSQL/Redis/provider service |
| Frontend complete suite | 266/266 passed in 45 files | jsdom/unit/integration; no live server |
| Frontend typecheck | Passed | `tsc --noEmit` |
| Frontend i18n | Passed | 82 source files, all referenced keys present |
| Frontend production build | Passed | 4,027 modules transformed |
| Django system check | Passed | 0 issues with local test settings |
| Migration drift | Passed | `No changes detected` |
| Ruff changed backend files | Passed | Base-settings historical warnings are outside changed-file lint gate |
| `git diff --check` | Passed | Only Git LF/CRLF notices |

ESLint was not available in the installed frontend dependencies, so no ESLint
pass is claimed. The production build reported large existing Ant Design/main
chunks but completed successfully.

## 7. Remaining deployment risks

- PostgreSQL migration duration/locking and the batched `0015` backfill have not
  been measured on production-scale data.
- Redis lease renewal, replay retention, worker loss, and multi-worker races were
  covered by local tests/mocks but not by a live Redis deployment in this work.
- Provider latency, model identifiers, policy bindings, deep budgets, and real
  streaming behavior require the actual 筼筜 provider configuration.
- Browser layout, reduced motion, clipboard/native share, downloads, and full
  role journeys require an authorized live-server smoke pass.
- Frontend bundle size remains a performance follow-up; route-level lazy loading
  can be planned after functional rollout evidence is collected.

## 8. Handoff checklist

- [x] Current branch, specification, environment state, and single next action recorded.
- [x] Stability, authorization, governance, product, model, and design invariants recorded.
- [x] New routes, migrations, constraints, flags, rollout, and rollback recorded.
- [x] Fresh full-suite/build evidence and honest limitations recorded.
- [x] No environment details, credentials, secrets, PII, or raw reasoning recorded.
- [ ] PostgreSQL migration rehearsal and production-scale timing completed.
- [ ] Live Redis/provider/authenticated browser smoke completed in 筼筜.
- [ ] Rollout evidence reviewed before each flag expansion.

## 9. Acceptance fixes (2026-07-18)

Local Docker acceptance of Version1.74.1 surfaced and fixed the following on
branch `fix/v1.74.1-acceptance-bugs` (off Version1.74.1; committed locally, not
yet pushed). The fixes are additive and do not weaken v1/legacy compatibility
(SPEC §11) or the §10.1 duplicate-suppression invariant.

- **Bug-1 (P0, chat send 500 on PostgreSQL)**: `select_for_update()` combined
  with `select_related(...)` on nullable FKs (`ChatSession.space`,
  `ChatTurn.assistant_message`, `Feedback.space`) produced LEFT OUTER JOINs that
  PostgreSQL rejects `FOR UPDATE` on. SQLite ignores this, so the prior
  SQLite-only suite missed it. Fixed by scoping `select_for_update(of=("self",))`
  at `apps/chat/services.py` (`find_session`, `lock_session`, `find_turn`) and
  `apps/chat/quality_views.py` (`FeedbackReviewDetailView.get_object`). Added a
  real-PostgreSQL regression test `apps/chat/test_pg_session_locking.py`
  (TransactionTestCase; 5/5 OK on PG). The DB row-lock is distinct from the SPEC
  §4.4 Redis lease (`RedisSessionLease`), so §10.1 duplicate suppression holds.
- **Bug-2 (P1, stale host dist)**: `frontend/Dockerfile` `final` stage now
  builds from source in-container (`COPY --from=builder`), removing the
  host-prebuilt `dist/` dependency; `frontend/.dockerignore` excludes `dist`.
- **Bug-3 (P2, blank capability routes)**: resolved by Bug-2 — the blank page
  was a stale-dist symptom; current source already redirects flag-off
  `/platform-admin`/`/governance`/`/workspace/:id/manage` (guarded by
  `App.test.tsx`), so no route change was made.
- **Bug-4 (P2, no governed models)**: new
  `apps/spaces/management/commands/seed_models.py` seeds `qwen-plus` and
  `qwen3.7-plus` ModelProfiles plus an org GovernancePolicy binding (fast=
  qwen-plus, deep=qwen3.7-plus, budget 1024, top_k 8). Deep execution still
  requires `DEEP_ANSWER_MODE=true` env + backend restart.
- **Bug-5 (P3, large frontend chunks)**: deferred per SPEC §15.1 (post-rollout
  route-level lazy loading) — not changed this branch.
- **Bug-6 (P3, Logout hit-area)**: raised `.sidebar` z-index 40→200 in
  `frontend/src/styles/chat.css` so the sidebar footer sits above the ChatPage
  fixed bottom bar (z-index 100); Logout is now clickable.

Verification: PG regression 5/5 OK; live chat send streams through DashScope
with no FOR UPDATE error; in-container frontend build OK + HTTP 200; flag-off
`/platform-admin` redirects to `/chat`; Logout logs out to `/login`; frontend
`tsc --noEmit` and `vite build` pass. The in-container SQLite subset run
(`apps.chat apps.spaces`, `local_test`) shows 8 pre-existing/environmental
failures (repo-root `SPEC.MD`/frontend smoke scripts absent from the backend
container; `.env` `QWEN_CHAT_MODEL=qwen3.6-flash` overrides the `qwen-plus`
default in `generation_policy` — proven: with `QWEN_CHAT_MODEL=qwen-plus` the
`test_generation_policy` suite passes 6/6); none are regressions from these
fixes (the changed locking paths have no existing real-ORM tests).

## 10. Crawler dead-code removal (2026-07-18)

The V6.0-retired web crawler had been retained "inert" (app code + tools + data
kept for historical/migration safety, with no routes/tasks/UI). On
`fix/v1.74.1-acceptance-bugs` the dead crawler code was fully removed:

- Deleted `backend/apps/crawler/` (app: models `CrawledDocument`/`CrawlTaskLog`,
  views/urls/services/tasks/serializers/validators/cleaners/admin + migration
  `0001_initial`), `backend/tools/ey_data_collector/` (standalone crawler CLI),
  `backend/crawled_knowledge/` (crawler output data), `backend/ingest_knowledge.py`
  (ingested crawled data), and root garbage `--selector`/`--viewport` PNGs.
- Removed `"apps.crawler"` from `LOCAL_APPS` and stale V6.0 "crawler retained /
  removed" comments in `config/settings/base.py`, `config/urls.py`,
  `config/celery.py`; fixed `ingest_onboarding_docs.py` docstring (it only reads
  `knowledge_docs/`, not crawled data).
- Finalized the user's pre-existing working-tree deletions (root `crawl_knowledge.py`,
  root `crawled_knowledge/`, `knowpilot-demo-video/`, `.playwright-cli/`,
  `generate_ppt.py`, `v42_audit_screenshot.js`, `verify_fixes.mjs`).
- Intentionally kept (harmless historical, no migration churn): the orphaned DB
  tables `crawler_crawleddocument`/`crawler_crawltasklog` (SPEC M5 "may remain for
  data retention"); `audit` action choices `document_crawl`/`document_crawl_withdraw`
  (locked in migrations 0004/0005); the `IngestionJob.trigger` `'crawler'` value in
  `frontend/src/api/admin.ts` (mirrors backend historical trigger); the
  `CrawlerRemovedTest` guard (asserts `/api/v1/crawl/` → 404); the `tests/` root
  v4.2 suite (left untouched per scope).

Verified: `manage.py check` 0 issues; `showmigrations` no longer lists crawler;
`makemigrations --check --dry-run` "No changes detected"; `CrawlerRemovedTest`
passes; live login works; gunicorn reloaded with no errors. No other app imported
crawler (confirmed zero external references), so removal is safe.
