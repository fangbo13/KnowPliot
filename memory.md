# KnowPilot Delivery Memory

- **Last updated:** 2026-07-16
- **Current phase:** Task 1 — Specification and durable handoff (complete and verified)
- **Active branch/commit:** `codex/knowpilot-optimization` / baseline `1e408df`
- **Primary spec:** [2026-07-16 KnowPilot Optimization Specification Addendum](docs/specs/2026-07-16-knowpilot-optimization-spec.md)
- **Deployment target:** 筼筜（远端运行环境；主机、路径与凭据未提供）
- **Environment status:** Not started. Docker and the deployed 筼筜 environment must remain stopped for this work.

## 1 Current Objective

Establish the approved optimization specification and a durable, safe handoff
baseline. Task 1 changes documentation only. The implementation sequence starts
with frontend chat stability containment before backend protocol, capability,
model, or visual rollout.

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

- Planned additive UUID record with `client_request_id`, session/space/user,
  question/assistant messages, status, answer mode, model ID, attempt count,
  last sequence, safe error code, and timestamps.
- Database uniqueness: `(user, client_request_id)`.
- Completed duplicates return the existing result; active duplicates return
  `turn_in_progress`; retryable failures reuse the question and increment the
  attempt count.

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
| `CHAT_TURN_IDEMPOTENCY` | Planned; disabled/not implemented | Additive Turn migration and idempotency tests pass. |
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

### In Progress

- None. Task 1 is ready for commit and coordinator handoff.

### Next

- **Single next action:** Start Task 2 by writing failing Vitest coverage for
  active-session reselection preserving messages, pagination, loading state,
  and the current Turn without issuing a reload.

### Deferred

- Tasks 3–8: ChatTurn/SSE v2, capability consoles, fast/deep execution, design
  convergence, product closure, and compatibility cleanup.
- Deployed 筼筜 validation and deployment-server migration require separate
  authorization and environment details.

## 7 Known Issues

| Group | Open IDs | State |
|---|---|---|
| Chat stability/data | `KP-C01`–`KP-C11` | Audited; implementation not started. |
| Authorization/governance | `KP-A01`–`KP-A04` | Audited; implementation not started. |
| Product closure | `KP-U01`, `KP-U02` | Audited; implementation not started. |
| Design system | `KP-D01`, `KP-D02` | Audited; implementation not started. |
| Environment | Backend DB tests blocked because hostname `db` is unavailable. | Do not claim PostgreSQL coverage until the host is available. |

## 8 Database and Migration State

- No Task 1 product code or migration change.
- `ChatTurn` and its additive migration are planned for Task 3 and do not yet
  exist at this baseline.
- Existing data must remain intact through rollout and rollback.
- PostgreSQL-dependent backend tests were not run: blocked because hostname
  `db` is unavailable. Do not start Docker to bypass this constraint.

## 9 Verification Ledger

| Evidence | Result | Provenance / limitation |
|---|---|---|
| Frontend baseline | 53 passed | Approved pre-task baseline; product tests are not required or rerun for Task 1. |
| Backend DB baseline | Not run / blocked | PostgreSQL hostname `db` is unavailable. |
| Task 1 product tests | Not run | Documentation-only task per approved plan. |
| Documentation path/link checks | PASS | 5 required paths resolved; 3 relative Markdown links resolved; 19 audited IDs and 11 ordered memory sections verified. |
| `git diff --check` | PASS | Exit 0 with the Task 1 report included in the checked diff. |

## 10 Deployment and Rollback

- Deployment target: 筼筜（远端运行环境；主机、路径与凭据未提供）.
- Environment remains unstarted; no deployment or remote mutation is authorized.
- Enable order: `CHAT_TURN_IDEMPOTENCY` → `CHAT_STREAM_V2` → `CAPABILITY_NAV`
  → `DEEP_ANSWER_MODE`.
- Rollback reverses that order and preserves additive `ChatTurn` data,
  migrations, v1 streaming, and the one-release legacy authorization fallback.
- Do not delete v1 routes or legacy fallback in this branch.

## 11 Handoff Checklist

- [x] Active branch and baseline commit recorded.
- [x] Primary addendum and implementation plan identified.
- [x] 筼筜 target recorded without inventing host, path, or credentials.
- [x] Environment-not-started state recorded.
- [x] Locked decisions, contracts, matrix, feature flags, and issues recorded.
- [x] Baseline evidence and DB-test limitation recorded honestly.
- [x] Exactly one next action identified.
- [x] Documentation path/link checks pass.
- [x] `git diff --check` passes with the Task 1 report included.
- [ ] Task 1 commit SHA is handed back to the coordinating agent.
