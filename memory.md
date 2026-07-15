# KnowPilot Delivery Memory

- **Last updated:** 2026-07-16
- **Current phase:** Task 3A — durable ChatTurn identity and idempotency (complete and verified); Task 3B is next.
- **Active branch/commit:** `codex/knowpilot-optimization` / Task 3A implementation `f2650a7`
- **Primary spec:** [2026-07-16 KnowPilot Optimization Specification Addendum](docs/specs/2026-07-16-knowpilot-optimization-spec.md)
- **Deployment target:** 筼筜（远端运行环境；主机、路径与凭据未提供）
- **Environment status:** Not started. Docker and the deployed 筼筜 environment must remain stopped for this work.

## 1 Current Objective

Continue from the verified frontend chat stability containment and durable
ChatTurn identity. The next bounded objective is Task 3B: add the renewable
Redis session lock, SSE v2 event identity/replay, and explicit worker-loss
recovery while preserving the current v1 stream contract.

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
- Database uniqueness: `(user, client_request_id)`.
- Completed duplicates return the existing result; active duplicates return
  `turn_in_progress`; retryable failures reuse the question and increment the
  attempt count.
- `GET /api/v1/chat/turns/{turn_id}/` returns owner-scoped safe status and the
  completed answer. Other users are filtered at lookup and are not revealed.
- The frontend sends and retains one `client_request_id` per send invocation;
  it still never automatically retries the POST.

### SSE

- v2 events: `meta`, `phase`, `answer_delta`, `citations`, `quality`, `usage`,
  `done`, `error`.
- `meta` precedes retrieval. Event IDs increase monotonically and support replay.
- EOF, parse failure, cancellation, navigation, and unmount retain partial
  content and expose recovery/terminal state without a replacement POST.

### Capability

- Planned authority endpoint:
  `GET /api/v1/rbac/me/capabilities/?space_id={id}`.
- Response fields: `scopes`, flat `capabilities`, and `default_console`.
- Workbench families: `/platform-admin/*`, `/governance/*`, and
  `/workspace/:spaceId/manage/*`.

### Feature flags

| Flag | Current state | Enable gate |
|---|---|---|
| `CHAT_TURN_IDEMPOTENCY` | Implementation complete; not enabled in the unstarted deployment | Apply `0013`, pass PostgreSQL-backed concurrency tests, then enable. |
| `CHAT_STREAM_V2` | Planned; disabled/not implemented | Turn durability/recovery and dual-protocol tests pass. |
| `CAPABILITY_NAV` | Planned; disabled/not implemented | Role matrix, scoped API, route, and navigation tests pass. |
| `DEEP_ANSWER_MODE` | Planned; disabled/not implemented | Governed model/privacy/mode tests and fast fallback pass. |

Enable in the table order. Roll back in reverse order.

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
- Task 3A implementation `f2650a7`: additive ChatTurn model/migration,
  transactionally serialized begin/reuse service, stable duplicate outcomes,
  owner recovery endpoint, primary-key history exclusion, session timestamp
  touches, completed-result v1 replay, and frontend request identity.

### In Progress

- None. Task 3A is committed and verified within the available environment.

### Next

- **Single next action:** Start Task 3B with failing database-free tests for a
  180-second Redis session lock that renews every 30 seconds and releases on
  every stream exit path, followed by SSE v2 event IDs and 15-minute replay.

### Deferred

- Task 3B and Tasks 4–8: Redis locking/SSE v2 replay, capability consoles,
  fast/deep execution, design convergence, product closure, and compatibility
  cleanup.
- Deployed 筼筜 validation and deployment-server migration require separate
  authorization and environment details.

## 7 Known Issues

| Group | Open IDs | State |
|---|---|---|
| Chat stability/data | `KP-C01`–`KP-C06`, `KP-C08`–`KP-C10` | Implemented with database-free/frontend coverage; deployed validation remains. |
| Chat lock/replay | `KP-C07`, remaining `KP-C11` recovery | Task 3B pending: Redis lease/renewal, event replay, and worker-loss closure. |
| Authorization/governance | `KP-A01`–`KP-A04` | Audited; implementation not started. |
| Product closure | `KP-U01`, `KP-U02` | Audited; implementation not started. |
| Design system | `KP-D01`, `KP-D02` | Audited; implementation not started. |
| Environment | Backend DB tests blocked because hostname `db` is unavailable. | Do not claim PostgreSQL coverage until the host is available. |

## 8 Database and Migration State

- Additive migration `backend/apps/chat/migrations/0013_chatturn.py` creates the
  durable record and its `(user, client_request_id)` unique constraint.
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
| Task 3A backend pure/SimpleTestCase | 12 passed | Model, serializer, transition, atomic begin/reuse, duplicate, status-owner, and no-RAG replay contracts; no PostgreSQL required. |
| Django system check | PASS | `System check identified no issues (0 silenced)` with test settings. |
| Migration consistency | PASS with environment warning | `No changes detected`; migration-history lookup warned that `db` is unavailable. |
| PostgreSQL-backed API test | BLOCKED | Setup failed only because hostname `db` could not be resolved; no assertion ran. |
| Frontend full suite | 110 passed in 18 files | Includes retained `client_request_id` and v2 request-body coverage. |
| Frontend typecheck | PASS | `tsc --noEmit`. |
| Frontend production build | PASS | `tsc -b && vite build`; 4000 modules transformed. Generated `tsconfig.tsbuildinfo` was restored and not committed. |
| Ruff changed-file check | PASS | All Task 3A Python implementation/test files passed. |
| `git diff --check` | PASS | Exit 0 before the Task 3A implementation commit. |

## 10 Deployment and Rollback

- Deployment target: 筼筜（远端运行环境；主机、路径与凭据未提供）.
- Environment remains unstarted; no deployment or remote mutation is authorized.
- Enable order: `CHAT_TURN_IDEMPOTENCY` → `CHAT_STREAM_V2` → `CAPABILITY_NAV`
  → `DEEP_ANSWER_MODE`.
- Rollback reverses that order and preserves additive `ChatTurn` data,
  migrations, v1 streaming, and the one-release legacy authorization fallback.
- Code rollback may disable the idempotent path while leaving the additive
  `chat_chatturn` table intact; do not reverse `0013` after production data is
  written without a separate data-retention decision.
- Do not delete v1 routes or legacy fallback in this branch.

## 11 Handoff Checklist

- [x] Active branch and Task 3A implementation commit recorded.
- [x] Primary addendum and implementation plan identified.
- [x] 筼筜 target recorded without inventing host, path, or credentials.
- [x] Environment-not-started state recorded.
- [x] Locked decisions, contracts, matrix, feature flags, and issues recorded.
- [x] Task 2 and Task 3A evidence plus DB-test limitation recorded honestly.
- [x] Additive migration and owner-visible recovery contract recorded.
- [x] Exactly one bounded Task 3B action identified.
- [x] Generated build metadata excluded from the implementation commit.
- [x] Task 3A commit SHA is ready for coordinating-agent review.
