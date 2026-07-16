# KnowPilot Delivery Memory

- **Last updated:** 2026-07-17
- **Current phase:** Task 3B2 — frontend dual-protocol stream consumption and GET-only recovery (complete and verified); Task 4 capability service is next.
- **Active branch/commit:** `codex/knowpilot-optimization` / current HEAD is the commit containing this handoff; Task 3B2 is layered on the reviewed Task 3B1 backend
- **Primary spec:** [2026-07-16 KnowPilot Optimization Specification Addendum](docs/specs/2026-07-16-knowpilot-optimization-spec.md)
- **Deployment target:** 筼筜（远端运行环境；主机、路径与凭据未提供）
- **Environment status:** Not started. Docker and the deployed 筼筜 environment must remain stopped for this work.

## 1 Current Objective

Continue from the verified end-to-end ChatTurn stream and recovery contract.
The next bounded objective is Task 4: implement the server capability endpoint
and capability-derived frontend authorization before creating scoped consoles.

## 2 Locked Decisions

| Decision | Locked value |
|---|---|
| Delivery order | Stability/data correctness → capabilities → model/performance → design/product closure. |
| Session reselection | Reselecting the active session is a no-op. |
| Turn identity | One `(user, client_request_id)` produces at most one user question. |
| Stream outcome | Every stream reaches or can recover to an explicit terminal/recoverable state; partial content survives. |
| Authorization source | Server capabilities replace frontend role guesses after the one-release compatibility window. |
| Scope boundary | Scoped administrators use only scoped endpoints and cannot grant upward. |
| Answer policy | `fast` is default; `deep` is opt-in and capability-governed; guests are fast-only. |
| Reasoning privacy | Raw provider reasoning is never persisted, logged, audited, or sent to the browser. |
| Design | Warm editorial system, restrained motion, and global reduced-motion support. |
| Deployment | Do not start Docker or the deployed 筼筜 environment in this branch. |
| Sensitive data | No secrets, PII, credentials, raw reasoning, prompts, or connection details in handoff artifacts. |

## 3 System Invariants

- Session switching cannot abort another session's Turn or leak stream state.
- Question POSTs are never automatically retried; recovery reuses the Turn.
- Duplicate active/completed requests do not create messages or workers.
- A Redis session lock uses a 180-second lease, renews every 30 seconds, and is
  released on every exit path.
- SSE v2 uses monotonic per-Turn sequence IDs and a 15-minute replay buffer.
- Space, membership, and chat capabilities protect list/history/send/share/export.
- Additive migrations and compatibility fallbacks precede feature enablement.

## 4 Contracts

### ChatTurn

- Additive UUID record is implemented in migration `chat.0013_chatturn`, with
  `client_request_id`, session/space/user, question/assistant messages, status,
  answer mode, model ID, attempt count, last sequence, safe error code, and
  timestamps.
- Turn space is required. User and space are derived from the user-locked,
  session-locked database row; independently supplied scope values are not
  accepted.
- Database uniqueness: `(user, client_request_id)`.
- Completed duplicates return the existing result; active duplicates return
  `turn_in_progress`; retryable failures reuse the question and increment the
  attempt count.
- `GET /api/v1/chat/turns/{turn_id}/` returns owner-scoped safe status and the
  completed answer. Other users are filtered at lookup and are not revealed.
- Status and event recovery converge an active Turn older than 180 seconds to
  `failed/worker_lost` only when Redis definitively proves its session lease is
  absent. Redis failure is not treated as lease absence.
- The frontend sends and retains one `client_request_id` per send invocation;
  it still never automatically retries the POST.

### SSE

- v2 events: `meta`, `phase`, `answer_delta`, `citations`, `quality`, `usage`,
  `done`, `error`.
- `meta` precedes retrieval. Event IDs increase monotonically and support replay.
- `GET /api/v1/chat/turns/{turn_id}/events/?after={seq}` replays safe events;
  `Last-Event-ID` is the fallback cursor. Owner and an active, unexpired
  `SpaceMembership` are rechecked before Redis access, with non-disclosing 404
  responses.
- Redis keys are `chat:session:{session_id}:turn` for the renewable lease and
  `chat:turn:{turn_id}:events|seq` for replay and sequence identity. Event
  payloads expire after 15 minutes; the safe integer sequence counter does not
  share that TTL and is seeded from the durable Turn checkpoint if recreated.
- Retry attempts clear prior-attempt event payloads without resetting the Turn
  checkpoint or Redis sequence counter, so per-Turn IDs stay monotonic without
  replaying a stale terminal error before the new attempt.
- EOF, parse failure, cancellation, navigation, and unmount retain partial
  content and expose recovery/terminal state without a replacement POST.
- The frontend stores Turn id, client request id, protocol version, last applied
  sequence, and recovery state under the owning session/generation. It consumes
  chunked v1/v2 SSE (including CRLF, multiline data, comments, and EOF tails),
  validates header/meta/status identities, ignores replayed sequence IDs, and
  performs at most three authenticated GET recovery attempts with per-response
  deadlines. A question POST is issued exactly once.

### Capability

- Planned authority endpoint:
  `GET /api/v1/rbac/me/capabilities/?space_id={id}`.
- Response fields: `scopes`, flat `capabilities`, and `default_console`.
- Workbench families: `/platform-admin/*`, `/governance/*`, and
  `/workspace/:spaceId/manage/*`.

### Feature flags

| Flag | Current state | Enable gate |
|---|---|---|
| `CHAT_TURN_IDEMPOTENCY` | No flag is implemented. Deploying this backend after applying `0013` activates idempotency immediately. | Pass PostgreSQL-backed concurrency tests; add a compatibility flag before deployment if staged activation is required. |
| `CHAT_STREAM_V2` | Implemented; environment-parsed and default `false`. v2 requires both this flag and request `protocol_version=2`; all other requests preserve v1. | Frontend dual-parser/GET recovery is complete; keep disabled until PostgreSQL/Redis integration validation passes. |
| `CAPABILITY_NAV` | Planned; disabled/not implemented | Role matrix, scoped API, route, and navigation tests pass. |
| `DEEP_ANSWER_MODE` | Planned; disabled/not implemented | Governed model/privacy/mode tests and fast fallback pass. |

The idempotency row documents rollout state, not a callable flag. Actual
deployment and rollback order is recorded in section 10.

## 5 Role and Capability State

| Level | Role | Approved authority | Current delivery state |
|---|---|---|---|
| 1 | Super admin | Platform global. | Matrix specified; capability service not implemented. |
| 2 | Organization admin | Own organization settings, business lines, scoped users, templates, metrics, audit, and model binding; never super grant. | Matrix specified; capability service not implemented. |
| 3 | Business-line admin | Own business-line spaces, users, templates, metrics, and audit; no cross-line or upward grant. | Matrix specified; capability service not implemented. |
| 4 | Space owner | Members, invites, access requests, knowledge, quality, audit, settings, and lifecycle in one space. | Matrix specified; capability service not implemented. |
| 4 | Knowledge admin | Document ingestion/index and quality in one space. | Matrix specified; capability service not implemented. |
| 4 | Reviewer | Quality and read-only audit in one space. | Matrix specified; capability service not implemented. |
| 4 | Member | Chat, history, share, and export; deep only with governed `chat.deep`. | Existing behavior requires capability convergence. |
| 4 | Guest | Fast chat only. | Existing behavior requires capability convergence. |

## 6 Delivery State

### Completed

- Approved implementation plan committed at baseline `1e408df`.
- Task 1 optimization addendum, durable memory, and root-spec pointer authored.
- Task 1 scope, link/path, structure, and diff checks passed.
- Task 2 frontend containment: session-keyed stream state, stale-load guards,
  pagination/deduplication, recoverable partials, History routing, and no POST
  retry. Full frontend suite reached 109 passing before Task 3A.
- Task 3A implementation `f2650a7`, amended by `ca77299`: additive ChatTurn model/migration,
  transactionally serialized begin/reuse service, stable duplicate outcomes,
  owner recovery endpoint, primary-key history exclusion, session timestamp
  touches, completed-result v1 replay, and frontend request identity.
- Task 3A review amendment serializes legacy session creation under the user
  lock, requires/derives Turn scope from the locked session, guards history
  evaluation, and verifies distinct request IDs remain session-owned.
- Task 3B1 backend coordination/recovery: injectable Redis lease with a
  180-second TTL and 30-second background renewal, compare-token Lua renew and
  release, fail-closed 409/503 outcomes, managed never-started/terminal cleanup,
  v1/v2 negotiation, monotonic safe SSE events, 15-minute replay, Turn sequence
  checkpoints, terminal timestamps, stale-worker convergence, recovery headers,
  and owner/membership-scoped event replay.
- Task 3B1 independent-review amendment: atomic Lua event append/retention,
  durable monotonic sequence seeding, renewal-start cleanup, optimistic stale
  convergence, strict active-membership recovery, untrusted replay validation,
  stable-code logging without raw exception text, and a conditional database
  checkpoint that cannot regress when stream callbacks finish out of order.
- Task 3B2 frontend dual-protocol recovery: incremental SSE parsing across
  chunks/CRLF/multiline data/comments/EOF, v1 compatibility, v2 identity and
  phase/event handling, monotonic event deduplication, per-session Turn state,
  GET-only events/status convergence, completed-answer fallback after replay
  expiry, bounded request/body deadlines, cancellation, and session isolation.
- Task 3B2 independent-review amendment: standards-correct event dispatch no
  longer treats network chunks as SSE boundaries; a bounded legacy-v1 adapter
  preserves delimiter-less adjacent events; shared live/replay validation now
  rejects missing/unsafe IDs, unknown events, malformed payloads, incomplete
  v2 meta/done identities, and missing recovery identity headers before any
  content or replay cursor can advance. A per-event explicit-ID marker prevents
  SSE's sticky last-event-id value from disguising a missing v2 `id:` field.

### In Progress

- None. Task 3B2 is implemented and verified within the available environment.

### Next

- **Single next action:** Start Task 4 with failing backend capability-matrix
  tests for `GET /api/v1/rbac/me/capabilities/?space_id={id}` before changing
  frontend routes or navigation.

### Deferred

- Tasks 4–8: capability consoles, fast/deep execution, design convergence,
  product closure, and compatibility cleanup.
- Deployed 筼筜 validation and deployment-server migration require separate
  authorization and environment details.

## 7 Known Issues

| Group | Open IDs | State |
|---|---|---|
| Chat stability/data | `KP-C01`–`KP-C06`, `KP-C08`–`KP-C10` | Implemented with database-free/frontend coverage; deployed validation remains. |
| Chat lock/replay | `KP-C07`, `KP-C11` recovery | Backend Task 3B1 and frontend Task 3B2 are implemented with database-free/frontend coverage; deployed Redis/PostgreSQL validation remains. |
| Authorization/governance | `KP-A01`–`KP-A04` | Audited; implementation not started. |
| Product closure | `KP-U01`, `KP-U02` | Audited; implementation not started. |
| Design system | `KP-D01`, `KP-D02` | Audited; implementation not started. |
| Environment | Backend DB tests blocked because hostname `db` is unavailable. | Do not claim PostgreSQL coverage until the host is available. |

## 8 Database and Migration State

- Additive migration `backend/apps/chat/migrations/0013_chatturn.py` creates the
  durable record, required space relation, and its
  `(user, client_request_id)` unique constraint.
- Migration model state is consistent: `makemigrations --check --dry-run`
  reported `No changes detected`; its database-history probe separately warned
  that host `db` could not be resolved.
- Existing data must remain intact through rollout and rollback.
- Migration `0013` was not applied. One PostgreSQL-backed API test was attempted
  and blocked at setup with `failed to resolve host 'db': [Errno 11001]
  getaddrinfo failed`. Do not start Docker to bypass this constraint.

## 9 Verification Ledger

| Evidence | Result | Provenance / limitation |
|---|---|---|
| Task 3A backend pure/SimpleTestCase | 17 passed | Includes locked session resolution, required/derived scope, history-failure recovery, model, serializer, transition, duplicate, status-owner, and no-RAG replay contracts. |
| Task 3A + Task 3B1 backend pure/SimpleTestCase | 61 passed (+ 5 subtests) | Includes NX/compare-token lease behavior, renewal-start failure, blocked-provider renewal, every stream cleanup class, v1 bytes, v2 negotiation/event mapping, meta-first ordering, atomic replay retention, durable sequence seeding, non-regressing database checkpoints, malicious-record denial, retry pruning, active-membership denial, log sanitization, Redis failure, and optimistic stale-worker convergence. |
| Django system check | PASS | `System check identified no issues (0 silenced)` with test settings. |
| Migration consistency | PASS with environment warning | `No changes detected`; migration-history lookup warned that `db` is unavailable. |
| PostgreSQL-backed API test | BLOCKED | Setup failed only because hostname `db` could not be resolved; no assertion ran. |
| Frontend full suite | 151 passed in 21 files | Covers v1/v2 happy paths, strict live/replay event and identity validation, explicit per-v2-event IDs despite sticky SSE last-event-id semantics, chunk/CRLF/multiline parsing without chunk-boundary dispatch, legacy adjacent-event adaptation, unsafe/unknown event denial without cursor advance, replay deduplication, events/status recovery, POST-once proof, bounded header/body stalls, cancellation, deletion, and cross-session isolation. |
| Frontend typecheck | PASS | `tsc --noEmit` after Task 3B2. |
| Frontend production build | PASS | `tsc -b && vite build`; 4002 modules transformed. The generated `tsconfig.tsbuildinfo` diff was reversed with a scoped patch and not committed. |
| Ruff changed-file check | PASS | All changed chat implementation/test files passed; `base.py` passed with its pre-existing B028/UP031/E402 findings excluded. |
| `git diff --check` | PASS | Exit 0 after implementation and handoff updates. |

## 10 Deployment and Rollback

- Deployment target: 筼筜（远端运行环境；主机、路径与凭据未提供）.
- Environment remains unstarted; no deployment or remote mutation is authorized.
- Idempotency deployment order is migration `0013` first, then backend code;
  there is currently no flag gate between those steps. Keep `CHAT_STREAM_V2=false`
  through the Task 3B1 backend rollout; later flags remain
  `CHAT_STREAM_V2` → `CAPABILITY_NAV` → `DEEP_ANSWER_MODE`.
- `CHAT_COORDINATION_REDIS_URL` defaults to `CELERY_BROKER_URL`. Session locking
  is always active for newly generated Turns and deliberately fails closed when
  Redis is unavailable; `CHAT_STREAM_V2=false` disables only the v2 envelope,
  not the lease.
- Enabling v2 requires setting `CHAT_STREAM_V2=true` and having the client send
  `protocol_version=2`. Roll back the envelope instantly with
  `CHAT_STREAM_V2=false`; v1 response bytes remain supported for one release.
- If the lease itself must be rolled back, redeploy the reviewed Task 3A backend
  rather than changing the v2 flag. Preserve migration `0013` and ChatTurn data.
  Redis lease/event keys are ephemeral and expire/release without a data migration.
- Idempotency rollback requires redeploying the prior backend code while
  preserving additive `ChatTurn` data and v1 streaming. A compatibility flag
  remains pending if staged activation or instant flag rollback is required.
- Backend rollback leaves the additive
  `chat_chatturn` table intact; do not reverse `0013` after production data is
  written without a separate data-retention decision.
- Do not delete v1 routes or legacy fallback in this branch.

## 11 Handoff Checklist

- [x] Active branch, reviewed implementation parent, and self-referential handoff HEAD recorded without a stale hash.
- [x] Primary addendum and implementation plan identified.
- [x] 筼筜 target recorded without inventing host, path, or credentials.
- [x] Environment-not-started state recorded.
- [x] Locked decisions, contracts, matrix, feature flags, and issues recorded.
- [x] Task 2, Task 3A, Task 3B1, and Task 3B2 evidence plus DB-test limitation recorded honestly.
- [x] Additive migration and owner-visible recovery contract recorded.
- [x] Absence of an idempotency feature flag and its real rollback consequence recorded.
- [x] Exact v2 flag, Redis fallback, recovery route, and rollback boundaries recorded.
- [x] Exactly one bounded Task 4 action identified.
- [x] Generated build metadata excluded from the implementation commit.
- [x] Task 3B2 implementation is ready for coordinating-agent review.
