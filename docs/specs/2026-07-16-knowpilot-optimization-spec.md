# KnowPilot Optimization Specification Addendum

> Version: 2026-07-16 v1
>
> Status: Approved implementation baseline
>
> Primary delivery plan: [KnowPilot Optimization Implementation Plan](../superpowers/plans/2026-07-16-knowpilot-optimization-implementation.md)
>
> Scope: stability, data correctness, authorization, model policy, product closure, and visual-system convergence

This addendum is the normative baseline for the KnowPilot optimization work. If
an implementation detail conflicts with this document, stop and resolve the
conflict before rollout. Existing `SPEC.MD` behavior remains in force unless
this addendum explicitly changes it.

## 1. Outcomes and non-goals

The work must, in order:

1. contain chat-state corruption and duplicate-question risks;
2. make every question durable and recoverable through a `ChatTurn`;
3. replace client-side role guesses with server-issued capabilities;
4. connect governed fast/deep model choices to the RAG path;
5. converge the interface on one warm editorial design system; and
6. close the highest-impact user and administrator workflows.

This branch does not start Docker or the deployed 筼筜 environment, migrate the
deployment server, delete the v1 stream protocol, or remove legacy authorization
fallbacks. It must not expose secrets, PII, provider reasoning, environment
credentials, prompts, or connection details in specifications, logs, tests, or
handoff memory.

## 2. Audited issue register

All issues below are open at this specification baseline. Closure requires the
acceptance evidence defined in section 10.

| ID | Audited issue | Required disposition |
|---|---|---|
| `KP-C01` | Reselecting the active session clears or reloads chat state. | Treat active-session reselection as a no-op. |
| `KP-C02` | Global stream state can appear in the wrong session. | Key stream, composer, partial answer, and list state by session ID. |
| `KP-C03` | Asynchronous message loads race and stale data wins. | Cancel obsolete loads and/or reject responses with a stale sequence. |
| `KP-C04` | A cross-tab selection event aborts this tab's stream. | Keep selection local; synchronize deletion and metadata only. |
| `KP-C05` | Unexpected SSE EOF leaves the UI permanently busy. | Preserve partial content and enter an explicit recoverable/terminal state. |
| `KP-C06` | Retrying the send POST can duplicate the question. | Never automatically retry a question POST; recover the existing Turn. |
| `KP-C07` | Multiple workers can generate concurrently without a session lock. | Use a renewable Redis session lock with guaranteed release. |
| `KP-C08` | History exclusion uses role/content matching and can remove the wrong message. | Exclude only by the persisted question message primary key. |
| `KP-C09` | Cursor pagination exists but the frontend consumes only the first page. | Preserve `next`, deduplicate, and maintain chronological order. |
| `KP-C10` | Creating messages does not touch session `updated_at`. | Touch the session whenever a message is persisted. |
| `KP-C11` | Page unmount/navigation can silently lose an active stream. | Persist/query Turn state and surface an explicit recovery state. |
| `KP-A01` | Chat authorization is not enforced consistently. | Enforce space/member/chat capabilities on list, history, send, share, and export. |
| `KP-A02` | Management consoles are not tiered and scoped admins call global APIs. | Split consoles by scope; scoped admins use scoped APIs only. |
| `KP-A03` | Legacy role arrays, `is_hr_admin`, and `role_level` are mixed into authorization. | Migrate to server capabilities; unmapped legacy users gain no authority. |
| `KP-A04` | `ModelProfile` and `GovernancePolicy` are not connected to RAG execution. | Resolve model, mode, and budgets through governance at execution time. |
| `KP-U01` | History routing, regenerate semantics, and sharing are incomplete. | Route History and implement non-duplicating regenerate/branch/share flows. |
| `KP-U02` | Backend space lifecycle capabilities are not exposed as usable workflows. | Expose discovery, requests, archive/restore/clone/transfer, and scoped review. |
| `KP-D01` | Two token systems and hard-coded design values create visual drift. | Establish one typed token source for CSS, Ant Design, and motion. |
| `KP-D02` | Motion is excessive and reduced-motion is not honored globally. | Restrict motion and support `prefers-reduced-motion`. |

## 3. Locked system invariants

- Stability and data correctness precede authorization restructuring, model
  work, and visual migration.
- Reselecting the active session is a no-op. Switching sessions never aborts
  another session's Turn or leaks its stream.
- A `(user, client_request_id)` pair creates at most one user question.
- Every stream ends in, or can be recovered into, an explicit terminal or
  recoverable Turn state. Partial answer content is retained.
- A question POST is never automatically resubmitted. Reconnection and replay
  recover an existing Turn.
- After the compatibility window, frontend authorization derives only from the
  server capability response. `role_level` is metadata, never authority.
- Scoped administrators never call global endpoints and never grant authority
  above their own scope.
- `fast` is the default answer mode and `deep` is opt-in. Raw provider reasoning
  is never persisted, logged, audited, or sent to the browser.
- The warm editorial brand is preserved. Motion is restrained and the complete
  interface honors `prefers-reduced-motion`.

## 4. ChatTurn v2 contract

### 4.1 Request and identity

The existing send endpoint remains
`POST /api/v1/chat/sessions/{session_id}/send/`. A v2 request adds:

```json
{
  "message": "Question text",
  "client_request_id": "UUID generated once by the client",
  "answer_mode": "fast",
  "protocol_version": 2
}
```

- `client_request_id` is stable across recovery and user-invoked retry of the
  same logical question. A new logical question receives a new UUID.
- `answer_mode` is `fast` or `deep`; omitted mode resolves to `fast`.
- `protocol_version: 2` requests the SSE v2 event contract. During the
  compatibility window, absent or v1 protocol selection retains v1 behavior.
- Authorization is evaluated for the session's space before a Turn or question
  is created.

### 4.2 Durable record

`ChatTurn` is additive and contains at least:

| Field | Contract |
|---|---|
| `id` | UUID primary key; stable recovery identity. |
| `client_request_id` | Client UUID; unique together with `user`. |
| `session`, `space`, `user` | Required scope links; all must agree. |
| `question_message` | The one persisted user question for this logical request. |
| `assistant_message` | The resulting assistant message when one is persisted. |
| `status` | Distinguishes queued/active, completed, retryable failure, terminal failure, and cancelled states. |
| `answer_mode` | Resolved `fast` or `deep` policy. |
| `model_id` | Resolved governed model identifier, not a browser-supplied authority. |
| `attempt_count` | Starts at one; increments only when a retryable Turn is re-attempted. |
| `last_event_sequence` | Highest persisted/emitted SSE v2 sequence for recovery. |
| `error_code` | Stable safe code; never raw provider output or a traceback. |
| timestamps | Creation/update plus execution/terminal timestamps needed for recovery and metrics. |

The database enforces uniqueness on `(user, client_request_id)`. Turn creation,
question creation, and duplicate detection occur atomically.

### 4.3 Idempotency behavior

| Existing Turn state | Repeated request behavior |
|---|---|
| No Turn | Atomically create the Turn and exactly one question, then start attempt 1. |
| Active | Do not create a message or worker; return `turn_in_progress` with the Turn identity. |
| Completed | Return/replay the existing completed result; do not regenerate. |
| Retryable failure | Reuse the Turn and question, increment `attempt_count`, and start one new attempt. |
| Terminal failure or cancelled | Do not silently resubmit; expose the terminal state and require an explicit new user action. |

Regenerate is separate: it creates a new assistant version for the same user
message. Branch creates a new session. Neither operation duplicates the
original user question.

### 4.4 Lock and recovery

- Generation holds a Redis lock scoped to the session with a 180-second lease
  and a 30-second renewal interval.
- The lock is released on success, handled error, cancellation, disconnect,
  worker exception, and every other exit path. Lease expiry is a final safety
  net, not the normal release mechanism.
- SSE v2 events are retained in a Redis replay buffer for 15 minutes.
- The chat API exposes authenticated Turn status and event recovery endpoints.
  Recovery is scoped by the original user, session, space, and capabilities;
  callers provide the last received sequence and receive only later events.
- Unexpected EOF or worker loss leaves a queryable Turn state. The client keeps
  partial content, queries/replays the Turn, and never creates a replacement
  question automatically.

## 5. SSE v2 contract

### 5.1 Wire rules

Every event uses the SSE `id`, `event`, and JSON `data` fields. `id` is a
strictly increasing integer within one Turn and is also the replay cursor.
The server emits `meta` before retrieval starts. A stream has exactly one
terminal `done` or `error` event when the worker can emit a terminal event;
otherwise the status endpoint supplies the terminal/recoverable state.

```text
id: 1
event: meta
data: {"turn_id":"...","session_id":"...","protocol_version":2,"answer_mode":"fast","model_id":"qwen-plus"}

```

### 5.2 Event vocabulary

| Event | Required semantics |
|---|---|
| `meta` | Turn/session identity, protocol, resolved mode/model, and replay metadata; emitted before retrieval. |
| `phase` | Safe application-known phase and status only, such as retrieval or generation; never raw reasoning. |
| `answer_delta` | Ordered assistant text delta for the Turn. |
| `citations` | Permission-safe citation metadata associated with the answer. |
| `quality` | Safe answer-quality result/summary when available. |
| `usage` | Governed usage and timing metrics; no prompts, reasoning, secrets, or credentials. |
| `done` | Completed status, assistant message identity, and final sequence. |
| `error` | Safe code, retryability, Turn status, and final known sequence; no traceback/provider payload. |

The frontend maintains separate connection, idle, and total timeouts. EOF,
parse failure, explicit cancellation, navigation, and unmount always transition
the session-scoped UI to an explicit recoverable or terminal state. Partial
content remains visible and attached only to its owning session.

## 6. Four-level role and capability contract

Authorization has four governance levels. Level 4 contains multiple workspace
roles; this does not create additional hierarchy above the workspace.

| Level | Role | Scope and capabilities | Explicit boundary | Default console |
|---|---|---|---|---|
| 1 | Super admin | Platform-global administration. | Only this level can exercise or grant platform-super authority. | `/platform-admin/*` |
| 2 | Organization admin | Within one organization: settings, business lines, scoped users, templates, metrics, audit, and model binding. | Cannot grant super admin or act outside the organization. | `/governance/*` |
| 3 | Business-line admin | Within one business line: spaces, scoped users, templates, metrics, and audit. | Cannot cross business lines or grant organization/super authority. | `/governance/*` |
| 4 | Space owner | Within one space: members, invitations, access requests, knowledge, quality, audit, settings, and lifecycle. | Cannot grant or call organization/business/platform administration. | `/workspace/:spaceId/manage/*` |
| 4 | Knowledge admin | Document ingestion/index maintenance and knowledge quality within one space. | No member, lifecycle, or higher-scope administration. | `/workspace/:spaceId/manage/*` |
| 4 | Reviewer | Quality workflow and read-only audit within one space. | No knowledge mutation, membership, lifecycle, or higher-scope administration. | `/workspace/:spaceId/manage/*` |
| 4 | Member | Chat, history, share, and export within allowed spaces. `chat.deep` may be added by governed policy. | No management capability. | User chat/history surfaces |
| 4 | Guest | Fast chat only in the allowed guest/demo scope. | No deep mode, history, share, export, source download, or management. | User chat surface |

`GET /api/v1/rbac/me/capabilities/?space_id={id}` is the frontend authority and
returns:

```json
{
  "scopes": {
    "platform": false,
    "organization_ids": [],
    "business_line_ids": [],
    "space_ids": []
  },
  "capabilities": ["chat.ask", "chat.history"],
  "default_console": "/workspace/00000000-0000-0000-0000-000000000000/manage"
}
```

- `capabilities` is a flat, server-resolved list. Routes, navigation, buttons,
  command palette entries, dashboards, and API selection consume this list.
- Scope-qualified server checks remain mandatory; hiding a frontend control is
  not authorization.
- Legacy `hr`/`is_hr_admin` users are mapped only when explicit scope exists.
  Unscoped users appear in an exception report and gain no new authority.
- Old `/admin/*` routes redirect according to `default_console` during the
  compatibility window.

## 7. Fast/deep model policy

| Policy | `fast` | `deep` |
|---|---|---|
| Selection | Default for every eligible user. | Explicit opt-in only. |
| Initial model | `qwen-plus` | `qwen3.7-plus` |
| Thinking | Disabled. | Enabled. |
| Initial thinking budget | Not applicable. | 1024. |
| Eligibility | All users with `chat.ask`, including guests. | Requires governed `chat.deep`; guests are always denied. |
| Configuration | Model ID and related execution values resolve through `ModelProfile` and `GovernancePolicy`. | Model ID and budget resolve through `ModelProfile` and `GovernancePolicy`. |

Provider `reasoning_content` may be consumed transiently by the server adapter
but is never persisted, logged, audited, included in SSE, or rendered in the
browser. User-visible progress is limited to application-known phases and
citation-derived answer basis.

If deep execution fails, the fast path remains available without duplicating
the question. Any fallback or explicit retry remains attached to the same Turn
semantics and is visible through safe phase/error metadata. Model/embedding/HTTP
clients are reused, ingestion-only parser/chunker initialization is removed from
chat, and `meta` is sent before retrieval. Required metrics include TTFE,
retrieval, reasoning duration (numeric only), first-answer-token, total duration,
disconnect, recovery, and idempotency outcomes.

## 8. Design direction

One typed token source drives CSS variables, Ant Design theme values, and motion
constants.

- Surfaces: warm paper neutrals with a terracotta accent and neutral semantic
  status colors.
- Layout: 8px spacing grid, 760px reading width, and 1200px management width.
- Primitives: `AppShell`, `PageHeader`, `Surface`, `EmptyState`, `Status`,
  `ActionBar`, and `ConfirmDialog`.
- Motion: 120ms, 180ms, and 240ms durations using opacity/transform only. Static
  cards do not lift decoratively.
- Accessibility: global `prefers-reduced-motion` behavior removes or minimizes
  non-essential movement without hiding state changes.
- Migration order: chat and the three management workbenches first; then login,
  history, quality, and template pages. Business behavior does not change as a
  side effect of visual migration.

## 9. Rollout phases

| Phase | Delivery slice | Exit condition |
|---|---|---|
| 0 | Specification and durable handoff | This addendum, `memory.md`, pointer, path checks, and diff checks are committed. |
| 1 | Frontend chat stability containment | `KP-C01`–`KP-C06`, `KP-C09`, and `KP-C11` are covered while v1 remains compatible. |
| 2 | ChatTurn, locking, idempotency, SSE v2 | Durable Turn/recovery, `KP-C07`, `KP-C08`, `KP-C10`, and `KP-A01` are verified. |
| 3 | Capability service and management consoles | Four-level matrix and `KP-A02`/`KP-A03` are enforced end to end. |
| 4 | Fast/deep modes and chat performance | Governed model paths and `KP-A04` are verified without raw reasoning exposure. |
| 5 | Unified warm editorial design system | `KP-D01`/`KP-D02` close across prioritized surfaces. |
| 6 | User and administrator product closure | `KP-U01`/`KP-U02` workflows close with capability denial cases. |
| 7 | Compatibility cleanup, full verification, and handoff | Available checks pass; blocked DB coverage is recorded; removal gates are documented. |

Each behavior-changing phase uses test-first development. No later phase may
weaken an earlier invariant to make its own rollout easier.

## 10. Acceptance criteria

### 10.1 Chat stability and data correctness

- Active-session reselection performs no reload and preserves messages,
  pagination, loading state, and the current Turn.
- Stale loads cannot overwrite the selected session; A-to-B switching cannot
  display A's partial answer or disable B's composer.
- Cross-tab selection cannot abort a local Turn. Deletion and metadata updates
  still synchronize.
- EOF, parse failure, navigation/unmount, and cancellation preserve partial
  content and produce a recoverable/terminal state.
- Cursor envelopes retain `next`; older-message loads deduplicate and preserve
  order.
- `(user, client_request_id)` creates no more than one question under duplicate
  and concurrent requests. Session locking renews and releases on all exits.
- History excludes by question primary key and each persisted message touches
  session `updated_at`.

### 10.2 Authorization

- Allow/deny tests cover every role in the four-level matrix and verify scope
  boundaries and upward-grant denial.
- The active frontend has no role-array, `role_level`, or `is_hr_admin`
  authorization branch after `CAPABILITY_NAV` rollout.
- Scoped dashboards and consoles use scoped metrics, user, and audit endpoints;
  server checks deny cross-scope requests.
- Unmapped legacy administrators receive no new capability.

### 10.3 Models, performance, and privacy

- `fast` resolves to governed `qwen-plus` with thinking disabled by default;
  authorized `deep` resolves to governed `qwen3.7-plus` with thinking enabled
  and initial budget 1024.
- Guests cannot request deep mode. Member deep access is controlled by
  `chat.deep`.
- Adapter tests prove reasoning/content separation. Searches, tests, logs, and
  browser payloads contain no raw provider reasoning.
- TTFE and phase metrics are recorded; chat no longer initializes ingestion-only
  parser/chunker dependencies.

### 10.4 Product and design closure

- History is routed; regenerate versions the assistant answer without a second
  user question; branch creates a new session.
- Shares are organization-authenticated, capability-gated, revocable, and
  default to seven-day expiry; guests are denied.
- Citation preview and source access respect permission; space discovery,
  requests, review, archive, restore, clone, transfer, and owner transfer have
  tested entry points and audit/confirmation states.
- The typed token source drives the migrated surfaces, reduced-motion assertions
  pass, and no second active theme palette remains.

### 10.5 Verification and evidence

- Each phase runs its targeted tests and the applicable frontend suite,
  typecheck, build, backend pure/static checks, Django checks, and migration
  consistency checks.
- PostgreSQL-only coverage may be marked blocked only when hostname `db` is
  unavailable; the exact limitation is recorded in `memory.md` and the phase
  report.
- `git diff --check` passes, documentation links resolve, and the deployed
  environment remains unstarted unless separately authorized.

## 11. Compatibility and rollback

### 11.1 Compatibility window

- Add the `ChatTurn` migration without deleting or rewriting existing chat data.
- Keep SSE v1 routes/behavior for one release while the frontend supports both
  protocols. v2 requests select `protocol_version: 2`; absent mode remains fast.
- Keep legacy authorization fallback for one release behind `CAPABILITY_NAV`.
  Do not remove v1 or legacy fallback in this branch.
- `CHAT_STREAM_V2` protects v2 streaming, and `DEEP_ANSWER_MODE` protects deep
  selection. Disabled flags preserve the existing fast/v1 experience.
- Removal after the window requires usage evidence, migration/exception closure,
  rollback rehearsal, and explicit approval.

### 11.2 Enablement order

Enable only after the preceding layer is healthy:

1. `CHAT_TURN_IDEMPOTENCY`
2. `CHAT_STREAM_V2`
3. `CAPABILITY_NAV`
4. `DEEP_ANSWER_MODE`

### 11.3 Rollback order

Disable in reverse order: `DEEP_ANSWER_MODE`, `CAPABILITY_NAV`,
`CHAT_STREAM_V2`, then `CHAT_TURN_IDEMPOTENCY`. Rollback switches traffic back
to fast mode, legacy navigation, and v1 streaming without deleting `ChatTurn`
records, replay evidence, additive columns, or migrations. Data-destructive
rollback is prohibited. Any cleanup migration is a separately approved release.
