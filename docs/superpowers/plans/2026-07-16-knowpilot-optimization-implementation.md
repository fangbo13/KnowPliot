# KnowPilot Optimization Implementation Plan

> Status: Tasks 1–8 implemented and locally accepted on `codex/knowpilot-optimization`; production acceptance in 筼筜 remains pending.
>
> Execution constraint: follow test-first development for every behavior change. Do not start Docker or the deployed 筼筜 environment. Local acceptance uses the isolated test settings; PostgreSQL, Redis, provider, and authenticated browser evidence belongs to an authorized deployment window.

## Completion ledger

| Task | State | Closure evidence |
|---|---|---|
| 1. Specification and handoff | Locally accepted | Normative addendum, root pointer, `memory.md`, current progress report |
| 2. Frontend stability containment | Locally accepted | Session-keyed state, stale-request guards, POST-once recovery and complete frontend suite |
| 3. ChatTurn/idempotency/locking/SSE v2 | Locally accepted; live Redis pending | Migrations, Turn/replay/lease/error contracts and complete backend suite |
| 4. Capability service/consoles | Locally accepted; browser UAT pending | Exact capability matrix, scoped APIs, route/deny tests |
| 5. Fast/deep/performance | Locally accepted; live provider pending | Governed profiles, safe phases/metrics, privacy and mode tests |
| 6. Design convergence | Locally accepted; visual UAT pending | Typed tokens/primitives, convergence/reduced-motion tests and production build |
| 7. Product closure | Locally accepted | History, regenerate/version/branch/share/citation and space/governance workflows |
| 8. Verification/handoff | Locally accepted | 365 backend and 266 frontend tests, static/build/doc gates, compatibility/removal route, current memory and reports |

## Global Constraints

- Stability and data correctness precede permission restructuring, model work, and visual work.
- Reselecting the active session is a no-op. Session switching never aborts another session's turn or leaks its stream.
- Each `client_request_id` creates at most one user question. Every stream exits through an explicit terminal/recoverable state.
- Frontend authorization derives only from server capabilities after the compatibility window; scoped admins never call global endpoints.
- Default answer mode is `fast`; `deep` is opt-in. Raw provider reasoning is never persisted, logged, or sent to the browser.
- Preserve the warm editorial brand, use restrained motion, and support `prefers-reduced-motion`.
- No secrets, PII, raw reasoning, or environment credentials in specs, logs, tests, or `memory.md`.

## Task 1: Specification and durable handoff

Create `docs/specs/2026-07-16-knowpilot-optimization-spec.md` from the approved optimization specification. It must contain the audited issue IDs, ChatTurn and SSE v2 contracts, four-level role/capability matrix, fast/deep model policy, design direction, rollout phases, acceptance criteria, and compatibility/rollback rules.

Create root `memory.md` with the approved current-state template. Record the
current branch, normative spec, 筼筜 deployment target, environment-not-started
status, locked invariants, final local evidence, feature flags, known deployment
risks, and the single next action. Update `SPEC.MD` with a versioned pointer and
implementation-closure summary without rewriting historical audit content.

Verification: link/path checks and `git diff --check`. Documentation-only task; no product test required.

## Task 2: Frontend chat stability containment

Write failing Vitest tests first, then implement:

- Reselecting the active session preserves messages, pagination, loading state, and the current turn without issuing a reload.
- Message loads use request cancellation and/or sequence validation so a stale response cannot overwrite the newly selected session.
- Stream/composer/message-list state is gated by session ID. Switching A to B cannot display A's partial answer or disable B's composer.
- Cross-tab session selection does not abort this tab's stream; deletion and metadata synchronization remain.
- Unexpected SSE EOF, parse failure, navigation/unmount, and explicit cancellation always produce an explicit recoverable/terminal state and preserve partial content.
- Sending a question is never automatically retried as a new POST. Reconnection is separate from resubmission.
- Cursor envelopes for sessions and messages retain `next`; loading older messages deduplicates and preserves order.
- Wire the existing History page into routing and remove invalid raw JSX comments.

Keep compatibility with the current backend protocol while introducing frontend types needed by SSE v2 and Turn recovery. Run targeted tests, full frontend tests, typecheck, and build.

## Task 3: Backend ChatTurn, idempotency, locking, and SSE v2

Write failing Django/pure unit tests first. Add an additive `ChatTurn` model and migration with UUID `id`, UUID `client_request_id`, session/space/user links, question/assistant message links, status, answer mode, model ID, attempt count, last event sequence, error code, and timestamps. Enforce uniqueness on `(user, client_request_id)`.

Extend the send request to accept `client_request_id`, `answer_mode`, and `protocol_version`. Atomically create/reuse the Turn and user question. Duplicate completed requests return the existing result; active duplicates return `turn_in_progress`; retryable failures reuse the question and increment attempts.

Implement a Redis session lock with a 180-second lease and 30-second renewal, released in every exit path. Emit SSE v2 events with incrementing IDs: `meta`, `phase`, `answer_delta`, `citations`, `quality`, `usage`, `done`, `error`. Persist a 15-minute Redis replay buffer and add Turn status/event recovery endpoints. Unexpected EOF or worker loss must have a queryable state.

Also fix history exclusion to use the new question primary key, touch session `updated_at` when messages are created, and enforce space/member/chat capabilities on list/history/send/share/export paths. Retain v1 compatibility behind `CHAT_STREAM_V2` for one release.

Verification: targeted tests, the complete isolated Django suite, Django checks,
migration generation consistency, and changed-file static checks. Record live
PostgreSQL/Redis behavior as deployment evidence rather than inferring it from
local substitutes.

## Task 4: Capability service and four-level management consoles

Write failing backend and frontend tests first. Add `GET /api/v1/rbac/me/capabilities/?space_id={id}` returning scopes, a flat capability list, and `default_console`. Implement the locked role matrix for super admin, organization admin, business-line admin, space owner, knowledge admin, reviewer, member, and guest.

Frontend authorization, navigation, buttons, command palette, dashboard data sources, user management, knowledge, quality, and audit entry points must consume capabilities instead of role arrays, `role_level`, or `is_hr_admin`.

Create/route three workbench families: `/platform-admin/*`, `/governance/*`, and `/workspace/:spaceId/manage/*`. Old `/admin/*` routes redirect according to `default_console`. Scoped admins use scoped user/metrics/audit APIs only. Space owner/knowledge admin/reviewer receive the operational pages allowed by capabilities.

Add a migration/audit command for legacy `hr/is_hr_admin`: map only users with explicit scope; users without scope appear in an exception report and gain no new authority. Keep compatibility fallback behind `CAPABILITY_NAV` for one release.

Verification: role matrix allow/deny tests, frontend route/nav tests, typecheck, build, Django checks, and no hard-coded role-array authorization in active routes.

## Task 5: Fast/deep model modes and chat performance

Write failing tests first. Integrate `ModelProfile` and `GovernancePolicy` into the RAG execution path. Add `fast` as the default mode (`qwen-plus`, thinking disabled) and `deep` as opt-in (`qwen3.7-plus`, thinking enabled, initial budget 1024), while keeping model IDs and budgets configurable through governance.

Consume provider `reasoning_content` without persisting, logging, or forwarding it. Browser-visible progress is limited to application-known phases and citation-derived answer basis. Guests are fast-only; member deep access is governed by the `chat.deep` capability.

Remove ingestion-only parser/chunker initialization from chat, reuse model/embedding/HTTP clients, send `meta` before retrieval, separate frontend connection/idle/total timeouts, and record TTFE, retrieval, reasoning, first-answer-token, total duration, disconnect, recovery, and idempotency metrics. Do not migrate the deployment server in this task.

Expose fast/deep selection in the composer and a collapsible safe processing panel. Use `DEEP_ANSWER_MODE` for rollout and preserve the fast path if deep generation fails.

Verification: parser tests for reasoning/content separation, policy resolution tests, frontend mode tests, full frontend suite/typecheck/build, and backend static/pure tests.

## Task 6: Unified warm editorial design system

Write component tests where behavior changes, then create one typed token source that drives CSS variables, Ant Design theme values, and motion constants. Establish warm paper surfaces, terracotta accent, neutral status colors, 8px spacing grid, 760px reading width, and 1200px management width.

Add reusable `AppShell`, `PageHeader`, `Surface`, `EmptyState`, `Status`, `ActionBar`, and `ConfirmDialog` primitives. Standard motion durations are 120/180/240ms using opacity/transform only; remove decorative lift from static cards and globally honor `prefers-reduced-motion`.

Migrate the chat shell and the three management workbenches first, then login, history, quality, and template pages. Replace duplicated theme colors and the highest-density inline-style/hard-coded color sites without changing business behavior.

Verification: component tests, reduced-motion assertions, full frontend tests, typecheck, build, and style-token search showing no second active theme palette.

## Task 7: User and administrator product closure

Write failing API/UI tests first and complete the highest-impact missing workflows:

- Server-side conversation search/filter/cursor browsing and recovery-visible states.
- Regenerate creates a new assistant version for the same user message; branch creates a new session. Never duplicate the user question for regeneration.
- Citation title/snippet preview and permission-aware source access.
- Authenticated organization-only share objects, seven-day default expiry, revocation, `chat.share` enforcement, and guest denial.
- Space discovery, access request submission/status/reason, and scoped admin review queue.
- Frontend entry points for archive, restore, clone, transfer, owner transfer, and their confirmation/audit states.
- Model profile/governance pages in the correct scoped console.

Verification: targeted backend/frontend tests, capability denial cases, full frontend tests/typecheck/build, Django checks, and migration consistency.

## Task 8: Compatibility cleanup, verification, and handoff

Run the complete frontend and isolated Django suites, typecheck, i18n validation,
build, Django/static/migration checks, documentation link checks, and
`git diff --check`. Do not start the deployment environment. Record PostgreSQL,
Redis, provider, and browser evidence as deployment-pending in `memory.md`.

Review feature-flag defaults and rollback order: additive migration and backward-compatible backend first; dual-protocol frontend second; then enable `CHAT_TURN_IDEMPOTENCY`, `CHAT_STREAM_V2`, `CAPABILITY_NAV`, and `DEEP_ANSWER_MODE` in that order. Do not delete v1 routes or legacy authorization fallback in this branch; document their one-release removal gate.

Perform a whole-branch spec and quality review, fix Critical/Important findings, update `memory.md` to the final current state, and prepare the branch for user review without merging or pushing unless explicitly requested.
