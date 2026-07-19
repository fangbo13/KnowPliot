# KnowPilot Optimization Specification Addendum

> Version: 2026-07-19 v3 (internal-beta normative rewrite; provider-entitlement correction)
>
> Status: v2 implementation evidence remains historical; every v3 internal-beta
> requirement is implementation-pending until it passes the gates in sections
> 17 and 27. This document does not claim deployment acceptance.
>
> Historical v2 delivery plan (non-normative for v3): [KnowPilot Optimization Implementation Plan](../superpowers/plans/2026-07-16-knowpilot-optimization-implementation.md). Its `qwen-plus` and coupled deep/thinking steps are superseded by sections 7, 13, and 27; a v3 implementation plan is a later, separately approved code-delivery artifact.
>
> Approved follow-on design: [Ownership Continuity and Account Offboarding](../superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md) — implementation not started
>
> Companion records: [Internal-beta delta](2026-07-18-knowpilot-internal-beta-spec-delta.md)
> and [open-decision log](2026-07-18-knowpilot-internal-beta-decision-log.md)
>
> Scope: stability, data correctness, authorization, model policy, product closure, and visual-system convergence

This addendum is the final normative specification for the KnowPilot
optimization work. If
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

This documentation change does not start Docker or mutate a deployed UAT environment, migrate the
deployment server, delete the v1 stream protocol, or remove legacy navigation/
route compatibility adapters. It must not expose secrets, PII, provider reasoning, environment
credentials, prompts, or connection details in specifications, logs, tests, or
handoff memory.

## 2. Audited issue register

The disposition below reflects the 2026-07-17 implementation audit. “Locally
closed” requires source-level evidence and the gates in section 10. It does not
substitute for the live dependency and browser evidence required before UAT or
production acceptance.

| ID | Audited issue | Required disposition | 2026-07-17 state |
|---|---|---|---|
| `KP-C01` | Reselecting the active session clears or reloads chat state. | Treat active-session reselection as a no-op. | Locally closed |
| `KP-C02` | Global stream state can appear in the wrong session. | Key stream, composer, partial answer, and list state by session ID. | Locally closed |
| `KP-C03` | Asynchronous message loads race and stale data wins. | Cancel obsolete loads and reject responses with a stale sequence. | Locally closed |
| `KP-C04` | A cross-tab selection event aborts this tab's stream. | Keep selection local; synchronize deletion and metadata only. | Locally closed |
| `KP-C05` | Unexpected SSE EOF leaves the UI permanently busy. | Preserve partial content and enter an explicit recoverable/terminal state. | Locally closed |
| `KP-C06` | Retrying the send POST can duplicate the question. | Never automatically retry a question POST; recover the existing Turn. | Locally closed |
| `KP-C07` | Multiple workers can generate concurrently without a session lock. | Use a renewable Redis session lock with guaranteed release. | Locally closed; live Redis pending |
| `KP-C08` | History exclusion uses role/content matching and can remove the wrong message. | Exclude only by the persisted question message primary key. | Locally closed |
| `KP-C09` | Cursor pagination exists but the frontend consumes only the first page. | Preserve `next`, deduplicate, and maintain chronological order. | Locally closed |
| `KP-C10` | Creating messages does not touch session `updated_at`. | Touch the session whenever a message is persisted. | Locally closed |
| `KP-C11` | Page unmount/navigation can silently lose an active stream. | Persist/query Turn state and surface an explicit recovery state. | Locally closed |
| `KP-A01` | Chat authorization is not enforced consistently. | Enforce space/member/chat capabilities on list, history, send, share, and export. | Locally closed |
| `KP-A02` | Management consoles are not tiered and scoped admins call global APIs. | Split consoles by scope; scoped admins use scoped APIs only. | Locally closed |
| `KP-A03` | Legacy role arrays, `is_hr_admin`, and `role_level` are mixed into authorization. | Migrate to server capabilities; unmapped legacy users gain no authority. | Locally closed; compatibility removal pending |
| `KP-A04` | `ModelProfile` and `GovernancePolicy` are not connected to RAG execution. | Resolve model, mode, and budgets through governance at execution time. | Locally closed; live provider pending |
| `KP-U01` | History routing, regenerate semantics, and sharing are incomplete. | Route History and implement non-duplicating regenerate/branch/share flows. | Locally closed |
| `KP-U02` | Backend space lifecycle capabilities are not exposed as usable workflows. | Expose discovery, requests, archive/restore/clone/transfer, and scoped review. | Locally closed |
| `KP-D01` | Two token systems and hard-coded design values create visual drift. | Establish one typed token source for CSS, Ant Design, and motion. | Locally closed; live visual pass pending |
| `KP-D02` | Motion is excessive and reduced-motion is not honored globally. | Restrict motion and support `prefers-reduced-motion`. | Locally closed; live visual pass pending |

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
- `fast` is the default answer mode and `deep` is opt-in. `thinking` is a
  separate, default-off request preference for either mode; changing mode never
  changes the thinking preference.
- The browser may request only `answer_mode` and `thinking_enabled`. Model ID,
  provider, and thinking budget remain server authority. Raw provider reasoning
  is never persisted, logged, audited, or sent to the browser.
- Platform or governance authority does not implicitly grant `chat.*`,
  knowledge-content access, or a synthetic workspace owner role. An
  administrator must hold an explicit effective workspace membership, including
  an ordinary guest membership where applicable, before chatting. Pre-auth demo
  entry remains deferred.
- Workspace creation, ownership transfer, offboarding, and permanent deletion
  use a shared governed-request, impact-version, audit, idempotency, and
  row-locking contract. Permanent deletion is an orchestrated retention action,
  never an uncontrolled foreign-key cascade.
- The warm editorial brand is preserved. Motion is restrained and the complete
  interface honors `prefers-reduced-motion`.

## 4. ChatTurn v2 contract

### 4.1 Request and identity

The existing send endpoint remains
`POST /api/v1/chat/sessions/{session_id}/send/`. A v2 request adds:

```json
{
  "content": "Question text",
  "client_request_id": "UUID generated once by the client",
  "answer_mode": "fast",
  "thinking_enabled": false,
  "protocol_version": 2
}
```

- `client_request_id` is stable across recovery and user-invoked retry of the
  same logical question. A new logical question receives a new UUID.
- `answer_mode` is the requested `fast` or `deep` service tier; omitted mode
  resolves to `fast`.
- `thinking_enabled` is a boolean request preference independent of mode;
  omitted resolves to `false`. Switching between fast and deep must preserve
  the user's explicit thinking choice and must never turn it on implicitly.
- `model_id`, `model_profile_id`, `provider`, `thinking_budget`, and equivalent
  execution fields are forbidden client authority. A v2 request containing any
  of them returns `400 client_policy_authority_forbidden`; the server never
  silently trusts or persists those values.
- `protocol_version: 2` requests the SSE v2 event contract. During the
  compatibility window, absent or v1 protocol selection retains v1 behavior.
- Authorization is evaluated for the session's space before a Turn or question
  is created. `deep` requires `chat.deep`; `thinking_enabled=true` requires the
  independent `chat.thinking` capability. A platform/governance role without an
  effective workspace membership has neither capability nor `chat.ask`.

### 4.2 Durable record

`ChatTurn` is additive and contains at least:

| Field | Contract |
|---|---|
| `id` | UUID primary key; stable recovery identity. |
| `client_request_id` | Client UUID; unique together with `user`. |
| `session`, `space`, `user` | Required scope links; all must agree. |
| `question_message` | The one persisted user question for this logical request. |
| `assistant_message` | The resulting assistant message when one is persisted. |
| `status` | One of `accepted`, `retrieving`, `reasoning`, `answering`, `saving`, `completed`, `failed`, or `cancelled`. |
| `requested_answer_mode` | Client request snapshot, `fast` or `deep`; defaults to `fast` for legacy rows. |
| `answer_mode` | Effective server-resolved `fast` or `deep` policy. |
| `requested_thinking_enabled` | Client preference snapshot; boolean and default false. |
| `thinking_enabled` | Effective server-resolved boolean; never inferred from `answer_mode`. |
| `thinking_snapshot_known` | True for Turns resolved after this contract; false only for migrated historical Turns whose original thinking intent/effect cannot be proved. |
| `thinking_budget` | Server-resolved positive integer when thinking is on; otherwise `NULL`. |
| `model_id` | Resolved governed model identifier, not a browser-supplied authority. |
| `policy_fallback_code` | Bounded safe code when an already-authorized request is downgraded after a policy/flag race; empty on an exact resolution. |
| `attempt_count` | Starts at one; increments only when a retryable Turn is re-attempted. |
| `last_event_seq` | Highest persisted/emitted SSE v2 sequence for recovery. |
| `error_code` | Stable safe code; never raw provider output or a traceback. |
| timestamps | Creation/update plus execution/terminal timestamps needed for recovery and metrics. |

The database enforces uniqueness on `(user, client_request_id)`. Turn creation,
question creation, and duplicate detection occur atomically. The normalized
idempotency fingerprint includes content, session, space,
`requested_answer_mode`, and `requested_thinking_enabled`; a repeated UUID with
different mode or thinking intent returns `409 client_request_conflict`.

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
- A transport disconnect/navigation/unmount detaches only the SSE consumer; it
  does **not** release the execution lease while the provider/worker may still
  run. The lease is released only after the worker has stopped and the Turn is
  atomically terminal, or after a retryable-failure transition proves no worker
  remains. Success, handled error, explicit execution cancellation, and worker
  exception all follow that ordering. Lease expiry is a fenced final safety net:
  a new worker must compare the lease generation and Turn attempt before writing.
- SSE v2 events are retained in a Redis replay buffer for 15 minutes.
- The chat API exposes authenticated Turn status and event recovery endpoints.
  Recovery is scoped by the original user, session, space, and capabilities;
  callers provide the last received sequence and receive only later events.
- Unexpected EOF or worker loss leaves a queryable Turn state. The client keeps
  partial content, queries/replays the Turn, and never creates a replacement
  question automatically.
- A Turn owner may recover an active Turn only while the owner still has
  effective `chat.ask` through an explicit workspace membership (including a
  guest membership). Platform/governance scope alone never satisfies this
  check. Once the Turn is completed, failed, or cancelled, status/replay becomes
  history access and requires `chat.history` under the same membership rule.

### 4.5 State-machine and public-phase mapping

The server rejects any transition not listed below. A `completed` Turn must have
an assistant message. `completed` and `cancelled` are terminal; `failed` can
return to `accepted` only when its `error_code` is in the retryable allowlist and
the user explicitly retries the same logical request.

| From | Allowed next state |
|---|---|
| `accepted` | `retrieving`, `failed`, `cancelled` |
| `retrieving` | `reasoning`, `answering`, `saving`, `failed`, `cancelled` |
| `reasoning` | `answering`, `saving`, `failed`, `cancelled` |
| `answering` | `saving`, `failed`, `cancelled` |
| `saving` | `completed`, `failed`, `cancelled` |
| `failed` | `accepted` for an explicitly retried retryable error only |
| `completed`, `cancelled` | none |

Server phases are reduced before display so implementation or provider
reasoning is never exposed:

| Server phase | Public safe phase | Legacy UI stream phase |
|---|---|---|
| `accepted` | `accepted` | `connecting` |
| `retrieving` or `searching` | `searching` | `searching` |
| `reasoning`, `answering`, or `generating` | `generating` | `streaming` |
| `saving` or `finalizing` | `finalizing` | `completing` |

The session history recovery label is `recovering` for an active Turn,
`recovered` for a completed Turn with more than one attempt, `partial` for a
failed/cancelled Turn with a persisted partial assistant message, `failed` for
one without an assistant message, and `terminal` otherwise. The live composer
uses `idle`, `available`, `recovering`, `recovered`, and `failed` as its recovery
states.

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
data: {"turn_id":"...","session_id":"...","protocol_version":2,"requested_answer_mode":"fast","answer_mode":"fast","requested_thinking_enabled":false,"thinking_enabled":false,"thinking_snapshot_known":true,"thinking_budget":null,"model_id":"qwen3.6-flash","policy_fallback_code":""}

```

### 5.2 Event vocabulary

| Event | Required semantics |
|---|---|
| `meta` | Turn/session identity, protocol, requested and effective mode/thinking, snapshot-known marker, effective model/budget, safe policy fallback code, and replay metadata; emitted before retrieval. |
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

The initial timeout budget is fixed at 20 seconds to establish the connection,
45 seconds without an event, 180 seconds total, and 5 seconds for each Turn
status/replay recovery request. A timeout aborts only the owning session's local
request and then queries the existing Turn; it never repeats the send POST.

## 6. Four-level role and capability contract

Authorization has four governance levels. Level 4 contains multiple workspace
roles; this does not create additional hierarchy above the workspace.

| Level | Role | Scope and capabilities | Explicit boundary | Default console |
|---|---|---|---|---|
| 1 | Platform admin | Platform-global administration. | Only this level can exercise or grant platform-super authority. | `/platform-admin/*` |
| 2 | Organization admin | Within one organization: settings, business lines, scoped users, templates, metrics, audit, and model binding. | Cannot grant platform-admin authority or act outside the organization. | `/governance/*` |
| 3 | Business-line admin | Within one business line: spaces, scoped users, templates, metrics, and audit. | Cannot cross business lines or grant organization/super authority. | `/governance/*` |
| 4 | Space owner | Within one space: members, invitations, access requests, knowledge, quality, audit, settings, and lifecycle. | Cannot grant or call organization/business/platform administration. | `/workspace/:spaceId/manage/*` |
| 4 | Knowledge admin | Document ingestion/index maintenance and knowledge quality within one space. | No member, lifecycle, or higher-scope administration. | `/workspace/:spaceId/manage/*` |
| 4 | Reviewer | Quality workflow and read-only audit within one space. | No knowledge mutation, membership, lifecycle, or higher-scope administration. | `/workspace/:spaceId/manage/*` |
| 4 | Member | Chat, history, share, and export within allowed spaces. `chat.deep` may be added by governed policy. | No management capability. | User chat/history surfaces |
| 4 | Guest | Fast chat only in the allowed guest/demo scope. | No deep mode, history, share, export, source download, or management. | User chat surface |

The canonical role code is `platform_admin`; “Super admin” and “超管” are UI/
stakeholder aliases only. Seeds, capabilities, audits, and tests use the
canonical code so two platform-level roles cannot emerge from naming drift.

An active authenticated internal-beta account also receives the non-governance
entitlement `workspace.creation.request`. This is not a fifth governance level,
does not identify an approval scope, and grants no authority over an existing
workspace.

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
  "default_console": "/chat"
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

`default_console` is deterministic for multi-role users: platform console,
organization governance, business-line governance, workspace management, then
`/chat`, choosing the first tier for which an exact capability exists. At the
workspace tier, use an authorized `User.default_space` when it has a management
capability; otherwise use the most recently managed accessible space, breaking
ties by space UUID. A stale/default space is ignored. This ordering affects
navigation only and never combines or elevates capabilities.

### 6.1 Exact capability vocabulary

The following grants are additive inside the listed scope. Platform,
organization, and business-line grants do not remove the endpoint's resource-
scope check.

| Role/scope | Server-issued capabilities |
|---|---|
| Platform admin | `platform.access`, `platform.audit.read`, `platform.knowledge.read`, `platform.metrics.read`, `platform.models.manage`, `platform.organizations.manage`, `platform.roles.manage`, `platform.taxonomy.manage`, `platform.templates.manage`, `platform.users.manage`, `platform.users.offboard`, `platform.workspace_creation_policies.manage`, `platform.workspace_creation_requests.manage`, `workspace.ownership.read`, `workspace.ownership.transfer.force`, `governance.admin_succession.manage`, `governance.users.suspend` |
| Organization admin | `governance.access`, `governance.admin_succession.manage`, `governance.audit.read`, `governance.business_lines.manage`, `governance.metrics.read`, `governance.models.bind`, `governance.organization.settings.manage`, `governance.spaces.manage`, `governance.taxonomy.manage`, `governance.templates.manage`, `governance.users.manage`, `governance.users.suspend`, `workspace.ownership.read`, `workspace.ownership.transfer.force` |
| Business-line admin | `governance.access`, `governance.audit.read`, `governance.metrics.read`, `governance.spaces.manage`, `governance.taxonomy.manage`, `governance.templates.manage`, `governance.users.manage`, `governance.users.suspend`, `workspace.ownership.read`, `workspace.ownership.transfer.force` |
| Space owner | `chat.ask`, `chat.history`, `chat.share`, `chat.export`, `audit.read`, `knowledge.read`, `knowledge.download`, `knowledge.index`, `knowledge.manage`, `quality.read`, `quality.review`, `workspace.manage`, `workspace.access_requests.manage`, `workspace.delete.permanent`, `workspace.invites.manage`, `workspace.lifecycle.manage`, `workspace.members.manage`, `workspace.settings.manage`, `workspace.ownership.read`, `workspace.ownership.transfer.request` |
| Knowledge admin | `chat.ask`, `chat.history`, `knowledge.read`, `knowledge.download`, `knowledge.index`, `knowledge.manage`, `quality.read`, `quality.review`, `workspace.manage` |
| Reviewer | `chat.ask`, `chat.history`, `audit.read`, `quality.read`, `quality.review`, `workspace.manage` |
| Member | `chat.ask`, `chat.history`, `chat.share`, `chat.export` |
| Guest | `chat.ask` only |

`chat.deep` is resolved dynamically for a selected non-guest space only when
deep mode is enabled and the effective governance policy makes it available.
`chat.thinking` is resolved independently for a selected non-guest space only
when the thinking rollout flag and effective governance policy allow it. A
pending ownership-transfer target receives
`workspace.ownership.transfer.accept` only for the transfer addressed to that
user; that resource-bound grant also permits
`GET /spaces/ownership-transfers/{transfer_id}/` only when
`to_owner=request.user`. It does not grant blanket `workspace.ownership.read`,
membership, or visibility of other transfers.

During internal beta, only platform administrators receive
`platform.workspace_creation_requests.manage`. The future
`governance.workspace_creation_requests.manage` capability is reserved but not
issued until Microsoft identity attributes and organization/business-line
membership are authoritative. Neither `platform.*` nor `governance.*` may be
translated into an `owner` workspace role for capability assembly. Global
metadata endpoints use their explicit platform/governance capabilities;
workspace chat, source content, and history use explicit membership.
Scoped `workspace.ownership.transfer.force` is the ownership-continuity recovery
operation, not a chat/self-join path: the acting administrator may not be the
target owner, all target/scope/reason/version rules still apply, and actor-target
separation is enforced in service and database constraints. A platform user may
chat after a distinct authorized actor validly makes them an owner, because an
explicit owner membership then exists, not because platform authority implied
one.
Business-line admins intentionally lack organization settings, business-line
management, and model-binding grants. Workspace roles intentionally lack every
`governance.*` and `platform.*` grant.

`chat.history` is the public capability returned to the browser. The space
permission layer names the same check `CHAT_VIEW_HISTORY` with stored code
`chat.view_history`; these are two representations of one policy, not separate
grants. API documentation uses the public capability name and implementation
tests cover the internal mapping.

## 7. Fast/deep model and independent-thinking policy

### 7.1 User-visible choices and fixed server mapping

The user chooses a service tier and an independent thinking preference; the
user never chooses a provider model.

| Requested combination | Effective model | Effective thinking intent | Eligibility |
|---|---|---:|---|
| `fast` + off | `qwen3.6-flash` | off | Any effective `chat.ask`, including guest. |
| `fast` + on | `qwen3.6-flash` | on by this explicit request, subject to capability/policy | `chat.ask` + `chat.thinking`; guest denied. |
| `deep` + off | `qwen3.7-plus` | off | `chat.ask` + `chat.deep`; guest denied. |
| `deep` + on | `qwen3.7-plus` | on by this explicit request, subject to capability/policy | `chat.ask` + `chat.deep` + `chat.thinking`; guest denied. |

Every new composer and logical question starts with `fast` and thinking off.
Changing mode preserves the explicit thinking switch value. History and replay
render the effective snapshot stored on each Turn, never the composer's current
selection.

### 7.2 Server resolution and budget semantics

For internal beta the only chat model bindings are fixed:

- `fast` resolves to the enabled system profile whose exact provider model ID
  is `qwen3.6-flash`;
- `deep` resolves to the enabled system profile whose exact provider model ID
  is `qwen3.7-plus`;
- other `ModelProfile` rows may remain in the platform registry but cannot be
  selected by the browser or bound as an internal-beta chat tier.

Resolution requires the applicable immutable `GovernancePolicy` revision and
its enabled canonical `ModelProfile`, then validates that binding against the
fixed server constant. The constant is a fail-closed allowlist, not an ambient
fallback: a missing policy/profile or different model ID returns
`503 model_policy_not_ready` before Turn creation. The legacy
`QWEN_CHAT_MODEL`/`RAG_LLM_MODEL` setting is a compatibility alias, not
model authority: while the alias exists it must equal `qwen3.6-flash`; any other
value makes readiness degraded and returns `503 model_policy_not_ready` before
creating a new Turn; it may not silently change execution. The
idempotent seed/reconciliation operation creates the canonical fast/deep
profiles and a new policy revision; it does not rewrite or delete historical
immutable policy revisions.

`thinking_budget` is meaningful only when `thinking_enabled=true`. It is a
server-resolved integer from the selected mode's governed policy key
(`fast_thinking_budget` or `deep_thinking_budget`), defaults to 1024, and must be
between 1 and 32768 inclusive; booleans are invalid. When thinking is off the
effective budget is `NULL`, is omitted from the provider payload, and is shown
as “not applicable” in the UI. A missing/invalid budget cannot turn thinking on;
it resolves thinking off with a bounded `policy_fallback_code`.

### 7.3 Independent capability and rollout flags

- `DEEP_ANSWER_MODE` means only “the backend may resolve the deep tier.” It no
  longer enables thinking. `VITE_DEEP_ANSWER_MODE` means only “the frontend may
  render the deep control,” and remains non-authoritative.
- `THINKING_MODE` means “the backend may issue `chat.thinking` and resolve
  thinking requests.” `VITE_THINKING_MODE` controls only rendering of the
  thinking switch. Both default false for staged rollout; this availability
  default is separate from the per-question thinking value, which also defaults
  false when the feature is available.
- `chat.deep` and `chat.thinking` are independent dynamic capabilities. A forged
  deep or thinking request without its current capability returns `403
  answer_mode_not_allowed` or `403 thinking_not_allowed` before Turn/question
  creation.
- If capability was valid when the request began but the governed profile,
  policy, or flag changes before execution, the same Turn resolves fail-closed:
  deep may fall back to fast and thinking may fall back to off. `meta`, status,
  and replay expose the effective values and bounded fallback code; the send
  POST is never repeated.

### 7.4 Privacy, failure, and measurement

Provider `reasoning_content` may be consumed transiently by the server adapter
but is never persisted, logged, audited, included in SSE, or rendered in the
browser. User-visible progress is limited to application-known phases and
citation-derived answer basis. The existing state machine remains valid:
thinking-on Turns may use `reasoning`, while thinking-off Turns may transition
directly from retrieval to answering.

A model or thinking failure remains attached to the same Turn and never
duplicates the question. Model/embedding/HTTP clients are reused,
ingestion-only parser/chunker initialization stays outside chat, and `meta` is
sent before retrieval. Metrics include TTFE, retrieval, numeric reasoning
duration, first-answer-token, total duration, disconnect, recovery,
idempotency outcome, effective mode, and effective thinking boolean; they never
contain reasoning text, prompt text, or unbounded provider payloads.

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

| Phase | Delivery slice | Exit condition | Current state |
|---|---|---|---|
| 0 | Specification and durable handoff | This addendum, `memory.md`, pointer, path checks, and diff checks are committed. | Locally accepted by the v2 closure commit |
| 1 | Frontend chat stability containment | `KP-C01`–`KP-C06`, `KP-C09`, and `KP-C11` are covered while v1 remains compatible. | Locally accepted |
| 2 | ChatTurn, locking, idempotency, SSE v2 | Durable Turn/recovery, `KP-C07`, `KP-C08`, `KP-C10`, and `KP-A01` are verified. | Locally accepted; live Redis pending |
| 3 | Capability service and management consoles | Four-level matrix and `KP-A02`/`KP-A03` are enforced end to end. | Locally accepted; browser role journeys pending |
| 4 | Fast/deep modes and chat performance | Governed model paths and `KP-A04` are verified without raw reasoning exposure. | Locally accepted; live provider/SLO pending |
| 5 | Unified warm editorial design system | `KP-D01`/`KP-D02` close across prioritized surfaces. | Locally accepted; live visual pass pending |
| 6 | User and administrator product closure | `KP-U01`/`KP-U02` workflows close with capability denial cases. | Locally accepted |
| 7 | Compatibility cleanup, full verification, and handoff | Local gates pass and removal/deployment gates are documented. | Locally accepted; compatibility removal deferred |

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
- The access-code dialog closes from the close icon, Cancel, Escape, and an
  allowed mask click; every close path clears transient input/error state and
  cannot be immediately reopened by the underlying switcher event.
- Rapid navigation gives each route request an abort signal and monotonically
  increasing sequence. An unmounted route, stale response, or another page's
  cleanup cannot replace or clear the current page state.

### 10.2 Authorization

- Allow/deny tests cover every role in the four-level matrix and verify scope
  boundaries and upward-grant denial.
- The active frontend has no role-array, `role_level`, or `is_hr_admin`
  authorization branch after `CAPABILITY_NAV` rollout.
- Scoped dashboards and consoles use scoped metrics, user, and audit endpoints;
  server checks deny cross-scope requests.
- Unmapped legacy administrators receive no new capability.
- Platform/governance authority does not synthesize an owner membership or
  `chat.*`; chat/history/source-content tests require an explicit effective
  workspace membership and preserve non-disclosing denial without one.
- Internal-beta creation requests require `workspace.creation.request`; review
  requires `platform.workspace_creation_requests.manage`. Future scoped review
  is not enabled before authoritative enterprise identity routing.

### 10.3 Models, performance, and privacy

- `fast` resolves to governed `qwen3.6-flash`; `deep` resolves to governed
  `qwen3.7-plus`. Both resolve with thinking off unless the user explicitly
  enables the independent switch.
- Tests cover fast/off, fast/on, deep/off, and deep/on. `chat.deep` gates only
  the deep tier and `chat.thinking` gates only thinking; guests can use fast/off
  only.
- Thinking-on resolves a server budget in the inclusive range 1–32768 and
  thinking-off persists `NULL`. Client-supplied model or budget fields are
  rejected as authority.
- Seeded/unseeded, disabled-profile, stale-policy, and legacy-environment tests
  prove that neither `qwen-plus` nor unavailable `qwen3.7-Flash` silently becomes the v3 fast
  model. A mismatched legacy environment alias degrades readiness.
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
- Workspace creation has requester and platform-review journeys; approval
  atomically provisions the canonical owner, owner membership, classification,
  audit, and outbox row. Notification delivery occurs after commit and is never
  the authorization fact.
- Permanent workspace deletion is canonical-owner-only and requires archived
  state, fresh impact, an exact `org_slug/space_code` phrase, an idempotency key,
  a retention window, and a durable tombstone. Active shares, open work items,
  child categories, or legal holds block confirmation with stable 409 codes.
- Discovery supports authorized search, business line/work group/office filters,
  frequent and popular cards, stable paging, and explicit member/pending/
  requestable/invited states without exposing private-space activity.
- Access codes create owner-reviewed requests; targeted invitations become
  effective after recipient acceptance without a second owner review. Member
  CRUD cannot create, downgrade, or remove the canonical owner.
- Platform Knowledge shows safe workspace/organization classification and
  filters under `platform.knowledge.read`; document download remains a separate
  workspace-content permission. Scenario Templates explain and preview their
  snapshot/clone semantics.
- The typed token source drives the migrated surfaces, reduced-motion assertions
  pass, and no second active theme palette remains.

### 10.5 Verification and evidence

- Each phase runs its targeted tests and the applicable frontend suite,
  typecheck, build, backend pure/static checks, Django checks, and migration
  consistency checks.
- Local acceptance uses the isolated SQLite test settings. PostgreSQL migration
  timing/locking, Redis multi-worker coordination, provider behavior, and live
  browser journeys remain deployment evidence and may not be inferred from
  local mocks or unit tests.
- SQLite may cover pure state and serializer behavior, but every conditional
  unique constraint, deferrable classification trigger, impact-version race,
  and `select_for_update(of=("self",))` path in sections 13 and 20–22 requires a
  real PostgreSQL `TransactionTestCase`/concurrency gate. A backend image that
  omits repository-root docs or frontend smoke assets is a distinct supported
  test profile, not evidence that those host-level gates passed or regressed.
- `git diff --check` passes, documentation links resolve, and the deployed
  environment remains unstarted unless separately authorized.

## 11. Compatibility and rollback

### 11.1 Compatibility window

- Add the `ChatTurn` migration without deleting or rewriting existing chat data.
- Keep SSE v1 routes/behavior for one release while the frontend supports both
  protocols. v2 requests select `protocol_version: 2`; absent mode remains fast.
- Keep the legacy navigation/route compatibility adapter for one release behind
  `CAPABILITY_NAV`. Do not remove v1 routes or that adapter in this branch. The
  adapter consumes the same server-resolved exact capabilities; it may not read
  role arrays, synthesize owner, or issue an implicit `chat.*`/upward grant.
- Backend scope/capability enforcement is never controlled by `CAPABILITY_NAV`.
  During the compatibility window the backend flag selects only the navigation
  contract returned by the capability response (`navigation_mode=legacy` or
  `capability`) and legacy redirect behavior; `VITE_CAPABILITY_NAV` selects the
  frontend consumer. A flag mismatch shows a bounded navigation-unavailable
  state with a safe `/chat` escape, does not mount/fetch both consoles, and
  cannot add an API grant.
- `CHAT_STREAM_V2` protects v2 streaming, and `DEEP_ANSWER_MODE` protects deep
  selection only. `THINKING_MODE` independently protects thinking resolution;
  their `VITE_*` counterparts control only control visibility. Disabled flags
  preserve fast/off/v1. Durable Turn identity and duplicate suppression remain
  active regardless of the `CHAT_TURN_IDEMPOTENCY` marker.
- Legacy clients that omit thinking resolve it to off. SSE v1 continues to work
  for new known-off Turns. Pre-migration historical Turns carry
  `thinking_snapshot_known=false`; the UI labels them `legacy/unknown` instead
  of interpreting storage sentinels or inventing a snapshot.
- The existing `POST /spaces/` path remains for one compatibility release, but
  once `WORKSPACE_CREATION_APPROVAL` is enabled a human call is a deprecated
  adapter to `POST /spaces/creation-requests/`: it returns the same `202` request
  envelope and never creates a workspace directly. This intentional response
  change closes reviewer-separation bypass without deleting the route. A
  non-human provisioning worker may execute only an already approved request;
  it cannot submit/approve, become owner, or bypass the audit/outbox transaction.
  With the approval feature disabled, human create paths fail closed with
  `503 workspace_creation_unavailable`; disabling a flag never restores unsafe
  single-actor direct creation.
- Existing `InviteCode` redemption at `POST /spaces/join/` remains a direct
  invitation-code path for one compatibility release. New UI/API naming must
  stop calling it an “access code.” New access codes use the owner-reviewed
  request path in section 24. Legacy unbound code issuance is disabled when the
  new invitation flow is enabled, but already-issued valid codes are honored
  until expiry/revocation.
- Removal after the window requires usage evidence, migration/exception closure,
  rollback rehearsal, and explicit approval.

### 11.2 Enablement order

Enable only after the preceding layer is healthy:

1. `CHAT_TURN_IDEMPOTENCY`
2. `CHAT_STREAM_V2`
3. `CAPABILITY_NAV`
4. `DEEP_ANSWER_MODE`
5. `THINKING_MODE`
6. `WORKSPACE_CREATION_APPROVAL`
7. `WORKSPACE_JOIN_V2`
8. `WORKSPACE_PERMANENT_DELETE`

### 11.3 Rollback order

Disable in reverse order: `WORKSPACE_PERMANENT_DELETE`, `WORKSPACE_JOIN_V2`,
`WORKSPACE_CREATION_APPROVAL`, `THINKING_MODE`, `DEEP_ANSWER_MODE`,
`CAPABILITY_NAV`, `CHAT_STREAM_V2`, then the `CHAT_TURN_IDEMPOTENCY` observation
marker. Rollback switches traffic back to legacy direct invitations, pauses new
creation through the retained route adapter, and restores fast/off mode,
compatibility navigation, and v1 streaming without
weakening duplicate suppression or deleting `ChatTurn`, governed-request,
tombstone, replay, audit, or additive migration evidence. A confirmed purge is
not rolled back by a feature flag; only a not-yet-executing scheduled deletion
may be cancelled under section 22. Data-destructive schema rollback is
prohibited. Any cleanup migration is separately approved.

## 12. API and error contract

All endpoints below are under `/api/v1`, require authentication, and re-check
the current resource scope unless explicitly stated otherwise. A hidden button
or route is never sufficient authorization.

All v2 errors use
`{"error":{"code":"stable_code","message":"localized-safe-summary","request_id":"correlation-uuid","current_version":null,"details":{}}}`.
`details` is an endpoint-specific allowlist and never contains hidden-resource
identity, secret input, unsafe free text, or traceback. A replayed successful
mutation returns its original HTTP status/body plus
`Idempotency-Replayed: true`; new success returns `false`. `Retry-After` is
present on 429/eligible 503 responses.

### 12.1 Chat, history, recovery, and conversation operations

| Method and path | Authority | Success contract | Stable failures |
|---|---|---|---|
| `GET, POST /chat/sessions/` | Accessible space plus `chat.history` for list and `chat.ask` for create | 20-session cursor page ordered by pinned, update time, then ID; create binds current/default space | `400` invalid filter; `403` denied; non-disclosing `404` for inaccessible scope |
| `GET, PATCH, DELETE /chat/sessions/{id}/` | Session owner, current space access, and `chat.history` | Read, rename/pin, or soft-delete the owned session | `403` denied; `404` absent or non-owned |
| `GET /chat/sessions/{id}/messages/` | Session owner and `chat.history` | Newest 40-message cursor page; current assistant versions by default; chronological rendering after client normalization | `403` denied; `404` absent/non-owned |
| `POST /chat/sessions/{id}/send/` | Session access plus `chat.ask` | One durable Turn/question; v1 or v2 SSE selected by request and flag | `400` validation; `409` conflict/busy/terminal; `503` coordination or event store unavailable |
| `GET /chat/turns/{turn_id}/` | Original user and current space access; active Turn requires `chat.ask`, terminal Turn requires `chat.history` | Safe durable status and completed answer when available | non-disclosing `404`; `403` current membership/capability denial |
| `GET /chat/turns/{turn_id}/events/?after={seq}` | Same active/terminal rule as Turn status | Replays only events with a later sequence; `Last-Event-ID` is an alternative cursor | `503 event_store_unavailable`; scoped denial as above |
| `POST /chat/messages/{id}/regenerate/` | Owned visible message plus `chat.history` and `chat.ask` | Reuses the persisted question and creates a new assistant version without a second user message | Same Turn/idempotency errors as send |
| `POST /chat/messages/{id}/branch/` | Owned visible message plus `chat.history` and `chat.ask` | Idempotently creates a new session and copies the visible path through the selected message | `400` invalid payload; scoped `403/404` |
| `GET, POST /chat/sessions/{id}/shares/` | Owner; `chat.share` required to create | Lists/creates organization-scoped, read-only, seven-day shares | `403` denied; `404` inaccessible session |
| `DELETE /chat/shares/{share_id}/` | Share owner | Revokes idempotently; owner retains revoke authority after membership loss | non-disclosing `404` when not owner |
| `GET /chat/shares/{token}/view/` | Authenticated current member of same organization/workspace | Sanitized read-only current-version transcript | non-disclosing `404` for revoked, expired, cross-org, or inaccessible share |
| `GET /chat/citations/{id}/source/` | Current space access; download capability for link access | Safe source metadata and bounded excerpt; no raw file/storage path | `403` accessible member without download; non-disclosing `404` otherwise |
| `GET /chat/sessions/{id}/export/` | Owner plus `chat.export` | Permission-scoped conversation export | `403` denied; `404` absent/non-owned |

History query parameters are `q`, `time=all|today|this_week|this_month|older`,
`status=all|partial|recovering|recovered|failed|terminal`, and `cursor`. Unknown
enumeration values return `400`; search covers session title and message content
before pagination.

The send/regenerate idempotency responses are:

| Condition | HTTP/code | Required client action |
|---|---|---|
| Same UUID and same request is active | `409 turn_in_progress` | Query/replay returned `turn_id`; do not POST again automatically |
| Same UUID identifies different content/scope | `409 client_request_conflict` | Generate a new UUID only for a genuinely new logical question |
| Completed Turn lacks its result | `409 turn_result_unavailable` | Surface terminal support state; never invent an answer |
| Failed/cancelled Turn is not retryable | `409 turn_not_retryable` | Require a new explicit user action |
| Session lease already held | `409 session_busy`, retryable | Recover/status first; user may explicitly retry the same Turn |
| Redis/coordination/replay unavailable | `503 coordination_unavailable` or `event_store_unavailable`, retryable | Keep partial content and perform bounded recovery |

Retryable Turn error codes are `answer_save_error`, `client_disconnected`,
`connection_error`, `coordination_unavailable`, `lease_lost`,
`provider_timeout`, `provider_unavailable`, `session_busy`, `stream_error`,
`stream_timeout`, and `worker_lost`. Any non-allowlisted or unsafe exception text
is normalized to `internal_error` and raw provider output is never returned.

Turn status, replay `meta`, terminal `done`, and history detail expose the same
read-only snapshot: `requested_answer_mode`, `answer_mode`,
`requested_thinking_enabled`, `thinking_enabled`, `thinking_snapshot_known`,
`model_id`, `thinking_budget`, and `policy_fallback_code`. When
`thinking_snapshot_known=false`, requested/effective thinking and budget render
as `legacy/unknown` regardless of their storage sentinel; the browser must not
backfill them from current policy or composer state. Regenerate accepts a new `client_request_id`,
`answer_mode`, and `thinking_enabled`, and persists a new Turn snapshot without
duplicating the original user question.

### 12.2 Space and administration workflows

| Method and path | Authority | Product contract |
|---|---|---|
| `GET /spaces/discoverable/` | Authenticated user | Legacy default remains a list; `contract_version=2` provides authorized search/filter/cursor state defined in §12.4 |
| `POST /spaces/{id}/access-requests/` | Authenticated eligible user | Submits one request with a bounded reason and visible pending state |
| `GET, POST /admin/spaces/{id}/access-requests/...` | Current canonical owner plus `workspace.access_requests.manage` | One-release alias for the canonical §12.4 `/spaces/{id}/access-requests/...` service; the historical `/admin/` prefix does not imply platform authority and emits deprecation/sunset headers. |
| `POST /spaces/{id}/archive/` or `restore/` | Current canonical owner plus `workspace.lifecycle.manage` | Confirmation-gated lifecycle mutation with locked owner/version checks, audit evidence, and refreshed UI state; archive is permanent deletion's mandatory first stage |
| `POST /spaces/{id}/clone/` | Existing exact scoped clone capability | Creates a request/provisioning lineage; it never copies ownership, members, content, secrets, or audit by accident |
| Ownership transfer endpoints | Exact capabilities and target grants from the ownership-continuity specification | Canonical request/accept/force behavior; member CRUD and deletion cannot substitute for transfer |
| `/spaces/{id}/members/` and `/spaces/{id}/invites/` | Corresponding workspace capability | Members path remains canonical; `/invites/` is a one-release alias to §12.4 `/invitations/`, with the same service/idempotency/audit and no upward grant |
| `/admin/users/` and `/admin/users/{id}/assignments/` | Platform or scoped `governance.users.manage` | Returns/mutates only users inside the caller's effective scope |
| `/admin/model-profiles/` | Platform model authority to mutate; scoped governance may list enabled profiles | Platform registry remains separate from organization bindings |
| `/admin/governance/policies/` | Platform authority or organization `governance.models.bind` | Creates immutable, organization-owned policy revisions; cross-org binding denied |
| `GET /rbac/me/capabilities/?space_id={id}` | Authenticated user | Returns scopes, exact flat capabilities, deterministic default console, navigation mode, and non-authoritative feature availability |

The capability response adds:

```json
{
  "navigation_mode": "legacy|capability",
  "feature_availability": {
    "deep": true,
    "thinking": false,
    "workspace_creation_approval": true,
    "workspace_join_v2": true,
    "workspace_permanent_delete": false
  }
}
```

These booleans describe rollout availability only. API authorization still uses
the exact capability and resource scope. `default_console` is consumed after a
safe same-origin `next` target; otherwise login/refresh/root navigation uses it
and falls back to `/chat` only when the returned route is absent, unsafe, or no
longer authorized.

### 12.3 Governed workspace creation and deletion APIs

All writes below require a UUID `Idempotency-Key`; all detail routes use a
non-disclosing 404 outside the caller's scope.

| Method and path | Authority | Success contract | Stable failures |
|---|---|---|---|
| `POST /spaces/creation-requests/` | Active account plus `workspace.creation.request` | Creates one typed `workspace_create` governed request; returns `202 pending` | `400` invalid classification; `409 request_already_pending` or `idempotency_key_reused` |
| `GET /spaces/creation-requests/mine/` | Requester | Cursor list of own request status/result/rejection summary | `400` invalid cursor |
| `POST /spaces/creation-requests/{id}/cancel/` | Original requester while pending | `200 cancelled`; idempotently cancels without creating a space and releases its locator reservation | `409 request_not_pending` or `stale_request_version` |
| `GET /admin/governed-requests/?action=workspace_create&status=&cursor=` | `platform.workspace_creation_requests.manage` in beta | Platform review queue, scope-filtered before query filters | scoped `403/404`; `400` invalid filter |
| `GET /admin/governed-requests/{id}/impact/` | Same review capability | Fresh, safe creation/uniqueness/classification impact and `impact_version` | `409 request_not_pending` |
| `POST /admin/governed-requests/{id}/approve/` | Same review capability | Under one transaction creates the space, canonical owner/mirror, classification, audit/outbox, and completed request; returns `201` with space | `409 impact_changed`, `stale_request_version`, `request_already_resolved`, `space_locator_conflict`, or `self_approval_forbidden` |
| `POST /admin/governed-requests/{id}/reject/` | Same review capability | Returns `200 rejected`; required bounded reason, reviewer/time, atomic audit/outbox | `409 stale_request_version` or `request_already_resolved`; `422 unsafe_reason` |
| `GET /spaces/{id}/deletion-impact/` | Current canonical owner plus `workspace.delete.permanent` | Returns lifecycle/retention state, counts, structured blockers, confirmation phrase, and `impact_version` | non-disclosing `404`; `409 workspace_not_archived` only on a mutation, not this read |
| `POST /spaces/{id}/deletion-requests/` | Same canonical-owner check | Returns `202 pending`; creates one typed deletion request against fresh impact/lifecycle/ownership versions | `409 workspace_not_archived`, `deletion_already_pending`, `impact_changed`, or active blocker code |
| `POST /spaces/{id}/deletion-requests/{request_id}/confirm/` | Current canonical owner and unchanged owner/version captured by this request | Exact phrase + acknowledgement + request/lifecycle/ownership versions schedule retention-protected purge; returns `202` with canonical status `scheduled` | `409 stale_request_version`, `impact_changed`, `confirmation_mismatch`, `ownership_changed`, `retention_hold`, or active blocker code; a new owner must start again |
| `POST /spaces/{id}/deletion-requests/{request_id}/cancel/` | Current canonical owner before execution | Returns `200 cancelled`; does not automatically restore the space | `409 purge_already_started` or `stale_request_version` |
| `GET /spaces/deletion-requests/{request_id}/` | Current canonical owner while live; after purge, the immutable confirming-owner UUID matching the authenticated account | Safe request/purge status, blocker kind, retention date, per-store manifest phase/counts, and retryable failure code; resolves through request/tombstone snapshots after space removal | non-disclosing `404`; `409 request_invalidated` only on mutation |

Creation request body:

```json
{
  "name": "Assurance methodology",
  "code": "assurance-methodology",
  "purpose": "Bounded business purpose, max 1000 chars",
  "visibility": "private",
  "business_line_id": "uuid",
  "work_group_id": "uuid",
  "office_location_ids": ["uuid"],
  "template_version_id": "uuid-or-null"
}
```

The client never submits an approval scope or owner. Internal-beta routing sets
the platform review scope and approval makes the requester the canonical owner.
Every command below also carries its own `Idempotency-Key` header. Creation
cancel is `{"expected_request_version":3}`. Creation approval is:

```json
{
  "expected_request_version": 3,
  "impact_version": "64-lower-case-hex",
  "acknowledge_requester_becomes_owner": true
}
```

Creation rejection is
`{"expected_request_version":3,"reason_code":"controlled-code","reason_text":"optional, max 500"}`.
Delete-request creation is:

```json
{
  "impact_version": "64-lower-case-hex",
  "expected_lifecycle_version": 7,
  "expected_ownership_version": 3
}
```

Permanent-delete confirmation is:

```json
{
  "expected_request_version": 2,
  "impact_version": "64-lower-case-hex",
  "expected_lifecycle_version": 7,
  "expected_ownership_version": 3,
  "confirmation_phrase": "org_slug/space_code",
  "acknowledge_permanent": true
}
```

Deletion cancellation is `{"expected_request_version":3}`. A replay returns the
original status; a stale CAS returns `current_version`, and `impact_changed`
returns `current_version`, `impact_revision`, `impact_version`,
`impact_expires_at`, and the refreshed safe impact in error `details`. No 409
automatically retries or preserves an old acknowledgement.

Success bodies use the canonical persistence enum, never UI labels. Submission
returns
`{"request_id":"uuid","status":"pending","request_version":1,"expires_at":"RFC3339","status_url":"same-origin-path"}`;
creation approval returns
`{"request_id":"uuid","status":"completed","request_version":2,"space":{"id":"uuid","provisioning_status":"provisioning|ready|failed"}}`;
deletion confirmation returns
`{"request_id":"uuid","status":"scheduled","request_version":3,"purge_not_before":"RFC3339","status_url":"same-origin-path"}`.
Cancel/reject/status responses likewise return only the section 20.2 enum plus
the current version and their allowlisted result fields. “approved” and
“purge_scheduled” may be localized UI/event labels, but are not request status
values.

The phrase is compared to the server-returned normalized locator and is never
logged or copied into audit metadata. Unknown request fields are rejected.

### 12.4 Discovery, taxonomy, invitation, notification, and platform knowledge APIs

Every v2 mutation in this subsection requires `Idempotency-Key`; state
transitions also require the current resource version. Same-key/same-digest
replay returns the original result and a changed digest returns
`409 idempotency_key_reused`.

| Method and path | Authority | Contract |
|---|---|---|
| `GET /spaces/discoverable/?contract_version=2&q=&business_line_id=&work_group_id=&office_location_id=&access_state=&sort=&cursor=` | Authenticated account | Applies visibility/scope first, then validated filters. `sort` is `name`, `recent`, or `popular`; returns a stable cursor envelope and safe classification/access state. |
| `GET /spaces/discovery/highlights/` | Authenticated account | Returns at most five `frequent` user-specific accessible cards and five privacy-bucketed `popular` visible cards; never returns raw cross-user counts. |
| `GET /spaces/taxonomy/{kind}/?context=&q=&scope_id=&cursor=` | Authenticated account; `kind` is `business-lines`, `work-groups`, or `office-locations` | Returns only active selectable values visible to the account; `context=creation` also requires an active workspace-creation policy. IDs are revalidated on request/approval. |
| `GET, POST /admin/taxonomy/{kind}/` and `PATCH /admin/taxonomy/{kind}/{id}/` | Exact mapping in §23.1 | Cursor CRUD/deactivate for controlled values; moving a value across its parent scope is rejected. |
| `GET, POST /admin/workspace-creation-policies/` and `POST /admin/workspace-creation-policies/{id}/activate/` or `retire/` | `platform.workspace_creation_policies.manage` | Cursor list/create immutable revision and versioned activation/retirement; no mutation of an active revision. |
| `GET /templates/?scope=&q=&cursor=` and `GET /templates/{id}/revisions/{revision_id}/preview/` | Authenticated account within template scope | Safe current-version list and exact immutable revision preview with included/excluded component schema. |
| `POST /templates/`, `POST /templates/{id}/revisions/`, and `POST /templates/{id}/revisions/{revision_id}/activate/` | Global `platform.templates.manage` or scoped `governance.templates.manage` | Create template/draft revision and atomically activate an immutable revision; published rows are never patched and document assets are never copied. |
| `POST /spaces/access-code-requests/` | Authenticated account | Validates a new access code and creates/reuses a pending `SpaceAccessRequest`; never creates membership. Body includes code and bounded reason. |
| `GET /spaces/access-requests/mine/` and `POST /spaces/access-requests/{id}/cancel/` | Original requester | Cursor status list and idempotent pending cancellation. |
| `GET, POST /spaces/{id}/access-codes/` and `POST /spaces/{id}/access-codes/{code_id}/revoke/` | Current owner plus `workspace.invites.manage` | Lists safe prefixes/status or returns a new raw code once; revocation blocks new redemption without deciding pending requests. |
| `GET, POST /spaces/{id}/invitations/` and `POST /spaces/{id}/invitations/{invitation_id}/revoke/` | Current owner plus `workspace.invites.manage` | Cursor list/create/revoke targeted non-owner offers; secrets are returned once and never listed. |
| `GET /spaces/{id}/access-requests/` | Current owner plus `workspace.access_requests.manage` | Cursor review list with bounded reason and safe requester/status/version; no code secret. |
| `POST /spaces/{id}/access-requests/{request_id}/approve/` or `reject/` | Same current-owner check | Versioned terminal action; approve chooses a role no higher than the code ceiling, reject requires a reason code. |
| `POST /space-invitations/redeem/` | Authenticated targeted recipient | JSON body carries the single-use token and `action=accept` or `decline`; accept creates/reactivates the allowed membership and decline creates none. Both are idempotent; the token never appears in the URL. |
| `GET /notifications/` | Recipient | Actionable items add safe `action_kind`, `resource_type`, `resource_id`, `allowed_actions`, `action_state`, and an allowlisted same-origin `deep_link`. |
| `POST /notifications/{id}/actions/{action}/` | Recipient; `action` must be currently allowlisted for the matching resource | Delegates to the same invitation/access-request service; notification and resource state commit together. No client redirect is accepted. |
| `GET /spaces/{id}/members/?cursor=` | Current owner plus `workspace.members.manage` | Cursor list of non-secret member/effectiveness/change evidence; canonical owner is labelled immutable here. |
| `PATCH /spaces/{id}/members/{membership_id}/` | Same | Expected version + role/status/expiry + reason; owner role/mirror is rejected. |
| `DELETE /spaces/{id}/members/{membership_id}/` | Same | Idempotently removes a non-owner and revokes effective access while retaining evidence. |
| `GET /admin/documents/?q=&organization_id=&business_line_id=&work_group_id=&space_id=&status=&cursor=` | `platform.knowledge.read` | Global metadata list with nested safe organization/business-line/work-group/space identity; no file URL, storage path, or implicit download grant. |

The v2 bodies are shape-strict. Omitted optional fields are null/defaulted by
the server; unknown fields are rejected. Canonical mutation bodies are:

```json
{"code":"one-time-plaintext-input","reason":"Why access is needed (max 500)"}
```

```json
{"target_user_id":"uuid-or-null","target_email":"verified-target-or-null","role":"member","expires_in_days":7}
```

Exactly one invitation target is non-null. Access approval uses
`{"expected_request_version":2,"role":"member"}`; rejection uses
`{"expected_request_version":2,"reason_code":"controlled-code","reason_text":"optional, max 500"}`.
Invitation redemption uses
`{"token":"one-time-plaintext-input","action":"accept"}`. Member patch uses
`{"expected_membership_version":4,"role":"reviewer","status":"active","expires_at":null,"reason_code":"role_change","reason_text":"optional, max 500"}`;
unchanged mutable fields are omitted. Member DELETE requires
`If-Match: "membership-v4"` and
`{"reason_code":"access_removed","reason_text":"optional, max 500"}`. Secret
values are request-body only, redacted before request logging, and never echoed
after their one allowed issuance/entry response.

The remaining commands use these exact shapes:

- taxonomy create:
  `{"parent_id":"uuid","normalized_code":"ag-12345","display_name":"Assurance Group 12345"}`;
  taxonomy patch:
  `{"expected_version":2,"display_name":"new name","active":false}`. Parent
  reassignment is not a patchable field;
- creation-policy revision create:
  `{"business_line_id":"uuid","audience":"registered_beta","review_route":"platform","effective_from":"RFC3339-or-null","effective_until":"RFC3339-or-null","reviewer_separation_required":true}`;
  activation/retirement:
  `{"expected_policy_version":2}`;
- template create:
  `{"scope_type":"organization","scope_id":"uuid","key":"stable-key","display_name":"name"}`;
  revision create:
  `{"expected_template_version":2,"components":{"category_tree":[],"scenario_definitions":[],"quality_rubric":{},"workspace_defaults":{},"model_policy_refs":[]}}`;
  activation:
  `{"expected_template_version":3,"expected_revision_hash":"64-lower-case-hex"}`;
- access-code issue:
  `{"role_ceiling":"member|guest","expires_at":"RFC3339","max_uses":20,"max_pending":20}`;
  code revoke:
  `{"expected_code_version":2,"reason_code":"rotated"}`;
  direct discovery request:
  `{"reason":"Why access is needed (max 500)"}`;
  requester cancel:
  `{"expected_request_version":2}`;
- invitation revoke:
  `{"expected_invitation_version":2,"reason_code":"access_no_longer_needed"}`;
  access-request approve/reject use the exact versioned bodies above; invitation
  redemption uses the exact token/action body above;
- member PATCH/DELETE and notification action use only the shapes specified in
  this subsection. No mutation accepts a client-selected scope, owner, redirect,
  model/profile, budget, policy revision substitution, or result UUID.

For notification actions, `accept|decline` of a targeted invitation uses
`{"expected_resource_version":2}`; access-request `approve` uses
`{"expected_resource_version":2,"role":"member"}`; `reject` additionally
requires controlled `reason_code` and optional max-500 text. The notification
service maps this payload to the same canonical resource command and passes the
same idempotency record; it does not implement a second state machine. Header
`Idempotency-Key` is the sole client operation key—there is no duplicate body
`client_request_id` for these workflows.

Invalid, expired, revoked, wrong-recipient, and out-of-scope access/invitation
secrets share non-disclosing `404 access_code_not_available` or
`invitation_not_available`. State/version races are 409; invalid shapes/roles are
400; unsafe free text is 422; throttling is 429 with `Retry-After`.

`access_state` is one of `member`, `invited`, `pending`, or `requestable`.
Discovery never returns a private space merely because it is popular. Search is
bounded to 100 Unicode characters and covers safe name/code/description and
controlled taxonomy labels; authorization is never inferred from a search hit.

Access-code entry remains authenticated. Pre-authentication demo-code entry is
deferred and, if later approved, must be limited to explicit non-confidential
demo spaces. Targeted invitations may grant `knowledge_admin`, `reviewer`,
`member`, or `guest` only when the inviter can grant that role; `owner` is never
an invitation/member-CRUD role. Reusable/unbound invitation codes are limited to
`member` or `guest` during compatibility. Owner assignment always uses the
ownership-transfer service.

### 12.5 Readiness and test-principal operations

`GET /api/v1/health/ready/` is authentication-exempt and returns HTTP 200 or
503 with only `status=ready|not_ready`, build/configuration revision, and a map
of bounded check codes (`database`, `migrations`, `canonical_models`,
`creation_reviewers`, `creation_policy`, `shared_rate_limit`, `purge_registry`).
Values are `ok|disabled|not_ready`; there are no model IDs, environment values,
counts, hosts, paths, or errors. This endpoint is an orchestrator signal, not an
authorization oracle.

`GET /api/v1/admin/system/readiness/` requires `platform.access` and returns the
same result plus safe expected/effective fast/deep model IDs, profile/policy IDs
and revisions, `legacy_alias_matches`, paired rollout states, cache backend kind
(`shared|process_local`), worker-count bucket, and
`expired_test_principal_count`. It never returns keys, endpoints, connection
strings, or account identities.

`GET /api/v1/admin/test-principals/?state=expired_active&cursor=` requires
`platform.users.offboard` and lists only accounts explicitly marked
`account_purpose=test`, with ID, safe admin identity, expiry, owning run, active/
owner/admin blocker booleans, and individual ownership impact URL. There is no
bulk-delete or pattern-match endpoint. For each approved exact ID, operators use
the ownership specification's
`GET /admin/users/{user_id}/offboarding-impact/` and
`POST /admin/users/{user_id}/offboard/` with its impact/version/successor map.
Internal beta intentionally has no QA-cleanup frontend; this is an audited
operator workflow. Legacy accounts without test metadata appear only through an
approved exact allowlist in the no-write inventory and are never auto-classified.

## 13. Persistence and migration contract

The required additive deployment sequence is:

1. `chat.0013_chatturn` — durable Turn identity, status, indexes, and unique
   `(user, client_request_id)` constraint;
2. `spaces.0008_organizationmembership_effectiveness` — scoped organization and
   business-line administration effectiveness;
3. `chat.0014_chatturn_metrics_and_model_lengths` — safe metrics and governed
   model identifier capacity;
4. `chat.0015_message_versions_and_session_branches` — regeneration lineage,
   current-version constraints, branch idempotency, and question identity;
5. `chat.0016_conversation_share` — revocable tenant-scoped share records;
6. ownership-continuity prerequisite: `spaces.0009_ownership_continuity_stage_a`,
   `users.0004_user_offboarding_metadata`, then the audited/remediated
   `spaces.0010_ownership_continuity_stage_c`; no later workspace lifecycle
   migration may bypass its canonical owner or offboarding service;
7. `spaces.0011_ownership_invariant_hardening` — the conditional one-active-
   owner-membership constraint, owner-state check, and deferred canonical-owner
   mirror trigger required by section 20; this is required even if an earlier
   ownership branch omitted it;
8. `users.0005_test_principal_metadata` — nullable `account_purpose`, expiry,
   and owning test-run identity for newly created test principals; no historical
   account is guessed or deleted;
9. `chat.0017_independent_thinking_snapshot` — requested/effective mode and
   thinking snapshots, budget/fallback fields, defaults, and checks;
10. `scenario_templates.versioned_clone_contract` — hardens existing
    `ScenarioTemplateRevision`, current/application revision pins, hashes,
    published-row immutability trigger, and legacy application state;
11. `spaces.0012_internal_beta_taxonomy` — `WorkGroup`, `OfficeLocation`,
    workspace classification fields/through table, usage daily/summary tables,
    legacy-unclassified state, indexes, and PostgreSQL consistency triggers;
12. `spaces.0013_governed_workspace_requests` — common governed-request envelope,
    typed create/delete details, locator reservation, operation idempotency,
    immutable `WorkspaceCreationPolicy` revisions, lifecycle/dependency versions,
    deferred detail-shape triggers, and live-request constraints;
13. `spaces.0014_workspace_join_v2` — hashed `SpaceAccessCode`, targeted
    `SpaceInvitation`, access-request source-shape trigger, pending access/
    invitation uniqueness, member-version/owner guards, and compatibility
    provenance;
14. `notifications.0003_actionable_notification_contract` — typed resource/
    action state needed for safe invitation and request deep links;
15. `spaces.0015_workspace_deletion_stage_a` — tombstone, purge job/checkpoint,
    retention/manifest fields, but no delete guard yet;
16. `knowledge.workspace_retention_contract` — category hierarchy plus the
    exact eligible/retained FK and snapshot changes in §22.4;
17. `chat.0018_workspace_retention_contract` — exact conversation/business-
    evidence FK, snapshot, and scrub fields in §22.4;
18. `scenario_templates.workspace_retention_contract` — application snapshots/
    cleanup after tombstone exists;
19. `audit.workspace_retention_contract` — immutable workspace/tombstone/actor
    snapshots and fixed non-cascading AuditLog/security-event FKs; and
20. `spaces.0016_workspace_deletion_stage_c` — transfer snapshot/nullable FK,
    final registry validation, locator/tombstone constraints, and purge guard
    trigger after every dependent app migration is present.

The labels after step 5 are normative ordering for this baseline. If a branch
already consumed a number, the implementation plan may renumber the file but
must preserve this dependency graph and record the mapping in the migration
audit; it may not reorder the invariants.

Migration `chat.0015` adds `version_group_id` as nullable, assigns a distinct UUID to
each existing message with iterator/bulk-update batches of 1,000, makes it
non-null, and only then adds uniqueness. Historical rows must never share one
schema-default UUID. The final database invariants are one
`(version_group_id, version_number)`, one current message per version group, one
branch per `(user, branch_request_id)`, one Turn per
`(user, client_request_id)`, and one idempotent share per
`(owner, client_request_id)` when the request ID is present.

Migration `chat.0017` backfills existing Turns with
`requested_answer_mode=answer_mode`, false boolean storage sentinels, a null
thinking budget, `thinking_snapshot_known=false`, and
`policy_fallback_code=legacy_thinking_unknown`. The false sentinels are not
historical truth and APIs must apply the known marker. It does not rewrite
historical `model_id` evidence. New Turns, including post-migration v1 clients
that omit thinking, write `thinking_snapshot_known=true` and known off.
PostgreSQL checks require unknown snapshots to use false/null sentinels; known
effective thinking off implies a null budget, and known effective thinking on
implies an integer budget from 1 through 32768.

Taxonomy migration `0012` never guesses a team from a space name or free-form
tag. Existing rows become `classification_state=legacy_unclassified`; new
ordinary create approvals require `complete`, while explicitly
organization-wide/demo spaces may be `exempt`. `WorkGroup` is unique by
`(business_line, normalized_code)`, `OfficeLocation` by
`(organization, normalized_code)`, and the workspace-location through table by
`(space, office_location)`. Because ordinary Django checks cannot enforce
cross-table organization/business-line agreement, one shared PostgreSQL
constraint function, called by `DEFERRABLE INITIALLY DEFERRED` triggers,
enforces four rules: business line and workspace organizations match; WorkGroup
and workspace business lines match; every selected office and workspace
organization match; and `classification_state=complete` requires non-null
business line/work group plus at least one office location.
`legacy_unclassified|exempt` may omit the new
fields but may not contain a cross-scope reference. Constraint triggers invoke
the function after relevant insert/update/delete on `KnowledgeSpace` (organization,
business line, work group, state), `BusinessLine` (organization), `WorkGroup`
(business line), `OfficeLocation` (organization), and the workspace-location
through table. Parent moves are also service-rejected; raw SQL cannot bypass the
commit-time check. SQLite service tests do not substitute for this trigger.

The governed-request envelope enforces unique
`(requester_uuid, action_type, idempotency_key)` and
one live deletion request per workspace with conditional PostgreSQL unique
constraints. `WorkspaceLocatorReservation`—not a cross-table unique claim—owns
the organization/normalized-code namespace for reserved, live, and tombstoned
states. Deferred detail triggers require creation reviewer/time on
completed/rejected, completed space identity on successful creation, deletion
confirmer/schedule on `scheduled`, and tombstone/job identity on
`executing|failed|completed`. `KnowledgeSpace`
receives `lifecycle_version` and `dependency_version`. Lifecycle increments on
archive, restore, transfer, deletion scheduling/cancellation, and any
classification change relevant to impact; dependency increments whenever a
registered share/task/category/hold/lease blocker is created or changes.

The locator migration creates the table without activating creation traffic,
NFC/case-normalizes every existing `(organization, space.code)`, and inserts one
`live` reservation per space in deterministic UUID batches. A normalized
collision stops the migration/readiness with an exact-ID exception report; it
never auto-renames a space. Only after a zero-exception audit is the unique
constraint validated. Every later create/rename/purge locks and transitions that
same namespace row.

`WorkspaceTombstone.original_space_id`, request UUID, and locator-reservation FK
are individually unique. The shared reservation row transitions `live ->
tombstoned` and is never released, so the normalized locator cannot be reused by
a new space. Audit, completed compliance/quality evidence, and any record still under
a retention/legal hold use a tombstone/nullable reference rather than cascading
with `KnowledgeSpace`. The purge service owns deletion order; schema `CASCADE`
is not accepted as the orchestration mechanism.

Before `WORKSPACE_PERMANENT_DELETE` can enable, migration
`spaces.0016_workspace_deletion_stage_c` backfills
immutable `space_uuid`, organization UUID, and safe locator snapshots on every
`OwnershipTransfer`, then changes only its `space` FK from `PROTECT` to nullable
`SET_NULL`. This is an explicit deletion-specific override of ownership-
continuity §7.2: completed transfer evidence must outlive the space, while any
non-terminal transfer remains a deletion blocker. Actor/old-owner/new-owner FKs
retain their ownership-spec retention behavior. The purge guard and service
prevent premature detachment; a direct delete still fails.

Migrations are applied with all rollout flags off after backup and rehearsal on
a PostgreSQL copy. Measure duration, table locking, backfill rate, index creation,
trigger validation, conditional-constraint creation, tombstone growth, and disk
growth. Every queryset that locks a row while also selecting nullable relations
uses `select_for_update(of=("self",))` or separate self-only queries; PostgreSQL
must prove that no nullable outer join is locked. Application rollback deploys
compatible code and disables flags
in reverse order while retaining additive rows/columns. Reversing migrations or
deleting Turn/version/share data requires a separately approved retention plan.

## 14. Product-state and interaction specification

### 14.1 Chat and history

- Reselecting the active session does nothing. Switching sessions preserves the
  prior session's Turn, partial answer, composer, message window, cursor, and
  error/recovery state in its session-keyed slot.
- Each list/detail request owns an abort signal and request sequence. A response
  may update state only if both still match the selected session/query.
- History exposes loading, error with retry, no-history empty, no-search-results
  empty, result, loading-more, end-of-list, and stale-request-discarded behavior.
  Filters and the active cursor are URL-addressable.
- The latest message window loads first. “Load earlier” consumes exactly one
  cursor page, deduplicates by message ID, and renders chronologically without
  scroll jumps.
- Send disables only the owning session composer while active. Partial text is
  never cleared by EOF, timeout, parse failure, unmount, navigation, or another
  tab's selection event.
- A user-visible recovery action queries Turn status/events. `recovered` attaches
  the durable answer; `failed` keeps partial content and safe error guidance.
- Regenerate shows answer-version navigation and never inserts a second user
  question. Branch switches only after the new session is confirmed. Share shows
  expiry/revocation state and never exposes a token from another organization.
- The composer shows only fast/deep and the independent thinking switch. Before
  `meta` it labels them “requested”; after `meta` the Turn processing/detail
  panel shows read-only effective mode, model ID, thinking on/off, and budget or
  “not applicable.” Fallback changes are visible and historical Turns use their
  persisted snapshots. `thinking_snapshot_known=false` renders
  `legacy/unknown` for both requested/effective thinking and budget; the false
  storage sentinel is never shown as a factual off decision.

### 14.2 User and administrator journeys

- Users can discover accessible/requestable spaces, give an access reason, see
  pending/approved/rejected state, and understand the next action without needing
  an administrator to explain an opaque error.
- Space owners review access reasons, approve or reject with required rationale,
  manage members/invites, and perform archive/restore/clone/transfer operations
  through explicit confirmations and result feedback.
- Knowledge admins see knowledge/index/quality tools but not membership or
  lifecycle actions. Reviewers see quality/review and read-only audit but not
  knowledge mutation. Members and guests see no management navigation.
- Platform, organization, and business-line administrators land in different
  capability-derived consoles. Every list, empty state, action, and API request
  is scoped; a scoped admin never falls back to a global endpoint.
- Governance model binding separates the platform model registry from immutable
  organization policy revisions. The UI displays effective model/mode/budget but
  does not accept browser-supplied model authority.
- Successful login, refresh, and root entry use a safe same-origin `next` path
  first, then capability-derived `default_console`. Platform, governance,
  workspace-manager, and ordinary user journeys land on `/platform-admin`,
  `/governance`, `/workspace/:id/manage`, and `/chat` respectively when
  capability navigation is enabled; legacy mode keeps its documented fallback.

### 14.3 Workspace creation request and review

Every active internal-beta account sees “申请创建 Workspace” only when
`workspace.creation.request` is present **and** capability bootstrap reports
`workspace_creation_approval=true`. The form uses server-provided business
line, work group, office location, visibility, and optional template choices;
organization and approver are not editable browser authority. It explains that
the requester becomes owner only after approval.

`draft` and `submitting` are local UI states only. Persisted creation-request
states are exactly `pending`, `completed`, `rejected`, `cancelled`, and
`expired`; the separately persisted workspace provisioning state is
`provisioning|ready|failed`. A repeated click sends one idempotent request.
`completed` links to the created workspace and renders provisioning state;
`rejected` shows the bounded reviewer reason; pending requests can be cancelled
but not edited in place. A material change creates a new request after
cancellation/rejection/expiry. The UI may label `completed` as “approved,” but
must send, store, filter, and test the canonical API enum `completed`.

The internal-beta platform queue shows request age, requester safe identity,
purpose, proposed locator, classification, template snapshot, uniqueness/
ownership impact, and approve/reject actions. Approval requires a fresh impact
version and a summary confirming that the requester becomes canonical owner.
Rejection requires a reason. 409 refreshes the request/impact without discarding
an unsent reviewer reason. Notifications are sent only after commit.

Future enterprise routing follows the active creation-policy revision and
server-derived authoritative identity: the nearest tier with an eligible active
reviewer set is business-line, then organization, then platform fallback.
Browser claims, free-form manager email, and display-only profile fields never
choose the approver. No such scoped routing is enabled in internal beta.

### 14.4 Discovery cards and controlled classification

The discovery page has a search field, controlled filters, a five-card
“常用” section, a five-card privacy-safe “热门” section, and a cursor-paged
result grid. Cards display workspace name/code, organization, business line,
work group, office locations, short description, and one access state. They do
not display raw member/question counts.

`frequent` is current-user data ordered by rolling 30-day interaction count,
last interaction, then stable workspace ID. `popular` uses the k-anonymous
30-day distinct-active-user buckets and stable ordering in §23.3; it never uses
or exposes raw Turn/member counts. Both apply current authorization/visibility
before ranking and remove an ineligible card immediately.

`WorkGroup` is the API/model name and “组别/团队” is its bilingual UI label; an
example is `Assurance Group 12345`. It belongs to exactly one existing
`BusinessLine`. `OfficeLocation` belongs to one organization and is orthogonal:
a workspace may select multiple offices. Neither is a new authorization scope
in internal beta. Free-form tags may improve search but cannot drive approval,
scope, SSO mapping, or permission checks.

Loading skeleton, empty catalog, no search results, no filter results, retryable
error, member, invited, pending, and requestable states are distinct. URL query
parameters preserve search/filter state. The create-request form uses the same
taxonomy labels/IDs, so a card and its resulting workspace cannot disagree.

### 14.5 Access codes, targeted invitations, notifications, and members

The product uses two unambiguous terms:

| Term | Meaning | Membership timing |
|---|---|---|
| Access code / 访问码 | Shareable discovery credential with no role authority. Redemption creates/reuses a pending access request. | Only after owner approval. |
| Invitation / 邀请 | Owner-issued, recipient-bound, expiring invitation with a permitted non-owner role. | On authenticated recipient acceptance/redemption; no second owner approval. |

These v2 entry/review controls render only when capability bootstrap reports
`workspace_join_v2=true` in addition to the exact resource capability. With the
flag off, new UI shows a bounded unavailable state and never calls legacy join;
the legacy route remains only for already deployed compatibility clients.

An access-code requester sees pending/approved/rejected/expired status. Owners
receive an actionable notification and deep link to
`/workspace/{spaceId}/manage/access?request_id=...`; approve/reject locks and
revalidates the pending request, rejection requires a bounded reason, and only
one concurrent resolution succeeds. The requester then receives either “Open
workspace” or “View decision.”

An invited recipient sees Accept and Decline in the notification feed and on a
dedicated landing page. Expired/revoked/already-resolved actions show an
idempotent terminal state, not a generic load error. Notification links are
same-origin route templates selected by the server; arbitrary stored URLs are
never navigated.

The owner member table supports list; targeted invite; create/reactivate only
after accepted invitation or approved access; non-owner role/status/expiry
change; suspend/reactivate; and remove, with explicit error/retry states for
`knowledge_admin`, `reviewer`, `member`, and `guest`. `owner` is displayed
read-only and changed only by the ownership-transfer flow. Every mutation checks
`workspace.members.manage`, an idempotency key/version, target eligibility, and
upward-grant denial. Removing a pending transfer target atomically invalidates
that transfer first; the canonical owner or a row participating in an executing
switch is blocked rather than partially changed.

### 14.6 Archived workspace permanent-deletion journey

The lifecycle page keeps the existing archive/restore behavior. “永久删除” is
shown only when capability bootstrap reports `workspace_permanent_delete=true`,
the selected space is archived, and the current canonical owner has
`workspace.delete.permanent`. Platform/governance authority alone never shows
or passes this action; flag off hides mutation controls while preserving status
for an already scheduled request.

The deletion journey is:

1. archive the workspace and explain that it becomes read-only;
2. load a fresh impact showing content counts, retained evidence, active
   blockers, earliest purge time, and exact confirmation phrase;
3. resolve every blocker and refresh impact;
4. type the exact `org_slug/space_code`, check the permanent-deletion
   acknowledgement, and confirm once;
5. show `purge_scheduled`, cancellation deadline, purge progress, then a durable
   deleted state from the retained request/tombstone locator. A `failed` store
   phase shows safe support/retry status but no second confirm or restore; only
   the dispatcher resumes the same purge job/checkpoints.

The destructive button remains disabled for phrase mismatch, stale impact,
active blocker, or submission. Default focus is not destructive. A 409 preserves
the typed phrase only until the refreshed phrase is compared, then requires a
new acknowledgement. Cancellation before purge execution leaves the workspace
archived; restore is a separate explicit action.

### 14.7 Platform Knowledge and Scenario Templates

`/platform-admin/knowledge` lists metadata across spaces under
`platform.knowledge.read` with Organization, Business Line, Work Group, Space,
document title/category/type/status/date columns and matching filters. The Space
cell links to safe workspace metadata. Preview/download actions appear only when
the administrator also has an explicit effective workspace membership whose
role supplies the relevant content capability; the global list itself grants
neither. A pre-existing legacy orphan document uses explicit “Unassigned” state.
Purged documents have no retained document row and never appear as a tombstoned
Knowledge result; the tombstone is visible only in authorized deletion/audit
evidence views.

The Scenario Templates entry and empty state state plainly: “模板是创建
Workspace 的克隆起点/初始配置快照；它不是共享 Workspace，后续模板修改不会
静默改变已创建的 Workspace。” Cards/detail show purpose, scenario type, scope,
version, prompt/retrieval defaults, quick questions, classifications brought
forward, and fields editable after creation. “使用模板创建 Workspace” opens the
same creation request for ordinary users and the same provisioning service for
authorized direct administrators. Preview distinguishes configuration snapshot
from document/content copying, which is explicitly excluded.

### 14.8 Route-owned loading and closable dialogs

Every modal uses a single owner state and a single `close()` transition. Close
icon, Cancel, Escape, and permitted mask click behave identically: they abort
the modal-owned request when that request is still safely abortable, clear local
validation/server errors and secret input, release busy state, and leave
surrounding dropdown/route state unchanged. Close remains effective while
submitting. If the server action cannot be cancelled, the UI detaches safely,
does not claim the action was cancelled, and later reflects its committed result
through ordinary status/notification refresh; it never reopens or updates an
unmounted modal.

Every route load owns an `AbortController` and request sequence. On navigation,
the route aborts its own pending HTTP work and unsubscribes its own listeners;
responses update state only when route identity and sequence are still current.
Chat SSE cleanup continues to follow §§4–5 and may not clear another route's
ordinary list state. Errors distinguish abort (silent), 401 (reauth), 403/404
(scope-safe), 429 (retry guidance using `Retry-After`), 5xx, and network failure.

## 15. Performance, observability, privacy, and design acceptance

### 15.1 Performance and reliability

- Product targets are retrieval p95 at or below 1 second for common space sizes
  and first answer token at or below 3 seconds after retrieval under normal
  provider conditions. These are deployment SLO candidates, not claims from the
  local unit suite; UAT must establish baselines segmented by answer mode/model.
- `meta` is emitted before retrieval. Model, embedding, and HTTP clients are
  reused, and the chat path does not initialize ingestion-only parser/chunker
  dependencies.
- The 20/45/180-second client budgets, 180-second renewable session lease,
  30-second lease renewal, 15-minute replay retention, and 5-second recovery
  request bound are release constants. Changes require contract-test updates.
- The measured Ant Design/main chunks are a v3 performance work item, not a
  proven cause of the navigation failure in §26. Platform, governance,
  workspace-management, discovery, template, and quality routes load through
  route-level lazy boundaries with stable loading/error states. Using the
  production Vite manifest, the aggregate JavaScript fetched before the
  authenticated `/chat` route becomes interactive—entry plus recursive static
  imports and modulepreloads, counting a shared file once—must be at most
  250 KiB gzip. A dynamic chunk preloaded before that point counts in the
  aggregate; every other individual lazy chunk must be at most 400 KiB gzip.
  CSS/assets are reported separately. A checked-in machine-readable baseline makes a
  regression fail the build. Splitting may not change route capability gates,
  default-console behavior, or request cleanup.
- Ordinary route GETs use abort/sequence ownership rather than automatic retry.
  A `429` honors a bounded `Retry-After` and offers an explicit user retry; login
  and send throttles are not assumed to be the cause of unrelated list failures
  without matching network evidence.

### 15.2 Safe telemetry and privacy

`ChatTurn.metrics` accepts only `ttfe_ms`, `retrieval_ms`, `reasoning_ms`,
`first_answer_token_ms`, `total_ms`, `disconnect_count`, `recovery_count`, the
bounded `idempotency_disposition`, bounded `effective_answer_mode`, bounded
`policy_fallback_code`, and booleans `thinking_enabled` and
`idempotency_rollout_enabled`. Unknown keys, booleans passed as numbers, and
unbounded labels are rejected. Recovery metrics do not touch `updated_at`, which
is reserved for worker-liveness convergence.

Workspace-governance metrics include request counts/age by safe status,
approval/rejection/conflict totals, discovery query latency/result buckets,
access/invitation resolution totals, deletion blockers by controlled code,
scheduled/cancelled/completed purges, and stale-impact conflicts. Labels never
contain names, search text, purpose/rejection notes, confirmation phrases,
codes/tokens, or user identifiers.

Logs, metrics, audit events, SSE, status responses, specifications, tests, and
handoff memory must not contain raw prompts, provider reasoning, traceback text,
credentials, connection strings, storage paths, or PII. `reasoning_ms` is a
numeric duration only. Citations use plain text stripped of markup and are
bounded to 280 characters.

Access/invitation plaintext, confirmation phrases, free-form request purpose,
rejection notes, deletion impact snapshots, and notification bodies are not
metric labels. Audit stores controlled action/result/reason codes and resource
IDs; sensitive free text is bounded, access-controlled, and excluded from list
views. A tombstone contains only the minimum locator/scope, actor reference,
policy snapshot, timestamps, and aggregate counts/digests needed for retention
and non-reuse.

### 15.3 Visual language and motion

- The single typed source is `frontend/src/design/tokens.ts`; it drives CSS
  variables and Ant Design theme values. Light accent is `#B85B35`, dark accent
  is `#E27B55`, with warm paper neutrals and semantic success/warning/error.
- Typography is 15px/1.6 body text with a restrained editorial display face.
  Spacing follows 4/8/16/24/32/48px on an 8px base; reading width is 760px and
  management width is 1200px. Control/surface/large radii are 8/12/16px.
- Standard motion is 120/180/240ms with
  `cubic-bezier(0.2, 0, 0, 1)`, limited to opacity/transform or essential state
  feedback. Static cards do not lift and repeated/decorative animation is absent.
- `prefers-reduced-motion: reduce` globally minimizes non-essential animation
  while preserving focus, progress, success, error, and confirmation state.
- Desktop, tablet, and narrow layouts retain reading rhythm, whitespace, action
  discoverability, keyboard focus, and contrast. Live visual acceptance must
  inspect chat, history, login, and all three administration workbenches.

### 15.4 Configuration, test identities, and environment truth

- Readiness reports the safe expected/effective fast and deep model IDs,
  mismatched legacy model alias, enabled policy/profile presence, and paired
  backend/frontend rollout state without returning environment values, keys, or
  endpoints.
- Historical QA superusers observed in a local acceptance database are a data
  hygiene issue, not a schema migration. Cleanup begins with a no-write inventory
  keyed by explicit test-account metadata or an approved exact allowlist, then
  uses the ownership/offboarding impact service. It never pattern-deletes users,
  bypasses last-platform-admin protection, or cascades business/audit data.
- New automated test principals carry `account_purpose=test`, an expiry, and an
  owning test run. Non-test deployments expose a health count for expired active
  test principals; identities are not listed in the health response.
- Verification reports use `passed`, `failed`, `not_run`, or
  `environment_blocked`. Repository-root documentation/frontend smoke gates run
  from a profile that contains those assets; a backend-only container must not
  misreport their absence as a product regression or their omission as a pass.
- The product name is **KnowPilot**. The canonical remote for this baseline is
  `github.com/fangbo13/Onborading-AI.git`; `KnowPliot` and machine-specific paths
  are historical aliases only. New documentation uses repository-relative links
  and never assumes `D:\KnowPliot` or `D:\Github\Onborading-AI` at runtime.

## 16. Original-request traceability

The implementation evidence in this table is the 2026-07-17 v2 historical
baseline only. It is not evidence that the 2026-07-18 v3 changes are implemented.
V3 traceability and gates are in section 27.

| User request | Specification coverage | Implemented evidence | Remaining release evidence |
|---|---|---|---|
| 1. Repeated clicks disconnect; content disappears | Sections 3–5, 10.1, 12.1, 14.1 | Session-keyed store, reselection no-op, abort/sequence guards, durable Turn, lease/replay, cursor consumption | Live multi-tab disconnect and Redis replay |
| 2. Project admin and super admin not separated | Sections 6, 10.2, 12.2, 14.2 | Exact capability service, platform/governance/workspace consoles, scoped APIs, upward-denial tests | Authenticated role journey in UAT |
| 3. Faster response and streaming thinking model | Sections 5, 7, 10.3, 15.1–15.2 | Historical v2: early `meta`, client reuse, coupled deep/thinking policy, safe phases, timing metrics, no raw reasoning | V3 independent-thinking implementation, four combinations, provider streaming, and p95/SLO baseline |
| 4. Inconsistent visual tone/motion/whitespace | Sections 8, 10.4, 15.3 | Typed tokens, primitives, warm editorial palette, restrained motion, reduced-motion tests | Live responsive visual/accessibility pass |
| 5. Missing user/admin/conversation functions | Sections 10.4, 12, 14 | History/search/paging, regenerate/version/branch/share/citation, discovery/access/lifecycle/governance workflows | Clipboard/native share and full browser UAT |
| 6. Find bugs and provide repair route | Section 2 plus sections 10, 17, and 18 | Audited issue register, contract tests, migrations, current progress report and `memory.md` | Deployment rehearsal and production monitoring |

## 17. Acceptance evidence and release gates

Local acceptance and production acceptance are intentionally separate:

| Gate | Required evidence | Current disposition |
|---|---|---|
| Source/data contract | Model, serializer, state-transition, capability, endpoint, and migration review matches this spec | V2 historical pass; v3 implementation review pending |
| Backend | Focused v3 regressions plus complete Django suite, system check, migration drift check, and changed-file Ruff | V2 historical 365/365; no v3 implementation claim |
| Frontend | Complete Vitest suite, TypeScript, i18n, production build, bundle budget, and route-state tests | V2 historical 266/266; no v3 implementation claim |
| Repository/docs | `git diff --check`, normative links resolve, canonical naming, no placeholder/contradiction, delta and decision log agree | V3 document gate pending final review |
| PostgreSQL | Backup/restore rehearsal; full §13 sequence; constraint triggers, conditional uniqueness, self-only row locks, concurrent approval/deletion/ownership evidence | Pending v3 implementation and authorized PostgreSQL run |
| Redis/multi-worker | Lease exclusivity/renewal/release, replay sequence/retention, disconnect and worker-loss recovery | Pending authorized test window |
| Provider | Exact qwen3.6-flash/qwen3.7-plus binding, four mode/thinking combinations, safe streaming/fallback, no raw reasoning, performance baselines | Pending v3 implementation and provider run |
| Browser/UAT | All roles plus create review, discovery/taxonomy, access/invitation notifications, member CRUD, dialog/navigation regression, platform Knowledge/templates, delete retention, responsive/reduced-motion | Pending v3 implementation; §26 records only the requested bug investigation |
| Data hygiene/config | Model readiness, supported test profiles, QA-principal dry run/offboarding, no last-admin or retention bypass | Pending; local observation is not cleanup evidence |

No gate is marked implementation- or production-pass from this Markdown-only
rewrite or from mocked dependencies. The requested existing local Docker/browser
bug investigation is diagnostic evidence only and may not mutate data/config or
be generalized into deployment acceptance. ESLint is not claimed until its
executable is present in the installed dependency set.

## 18. Resolved decisions and optimization route

The former product questions are resolved for this release:

1. Access codes require authentication and create owner-reviewed access
   requests; targeted invitations become effective after recipient acceptance.
   Existing direct `InviteCode` redemption is an invitation compatibility path,
   not the new access-code meaning. Pre-auth demo entry remains deferred.
2. Templates are global or scoped assets with versioned overrides; business
   lines do not silently fork untracked copies.
3. Chat retrieval remains single-space. Cross-space retrieval is out of scope
   until an explicit permission and citation-isolation design is approved.
4. High-confidentiality or long-running projects are spaces; small bounded topics
   are categories within a space.
5. Answers prefer summaries with citations and bounded excerpts; the current
   citation excerpt maximum is 280 characters.
6. Internal-beta workspace creation is reviewed by platform administrators; it
   is not trust-based. Future scope routing waits for authoritative enterprise
   identity.
7. `WorkGroup` and `OfficeLocation` are controlled classification, not tags or
   authorization scopes. A WorkGroup belongs to one BusinessLine; locations are
   organization-scoped and many-to-many with workspaces.
8. Platform authority does not implicitly grant workspace chat. A platform
   administrator chats only after an explicit effective membership is created
   and audited.
9. `fast=qwen3.6-flash`, `deep=qwen3.7-plus`; thinking is an independent,
   default-off preference for either mode. Model and budget remain server
   authority.
10. Permanent workspace deletion is current-owner-only, archive-first,
    impact/version/typed-confirmation protected, retention delayed, and
    tombstoned. Governance authority alone cannot bypass it.

The v3 route includes implementation, verification, and deployment; none of
those stages is completed by this specification rewrite:

1. Rehearse backup, restore, and additive PostgreSQL migrations with flags off.
2. Deploy the compatible backend/frontend with all staged flags off; smoke v1.
3. Enable the idempotency observation marker and monitor outcomes while core
   duplicate suppression remains mandatory.
4. Enable SSE v2 and prove Redis/multi-worker/disconnect recovery.
5. Enable backend/frontend capability navigation together and execute every role
   journey, including cross-scope denials.
6. Reconcile exact canonical model profiles, enable deep, verify deep/off, then
   enable thinking and verify fast/on and deep/on without raw reasoning.
7. Enable creation approval and join-v2, execute platform/requester/owner/
   recipient journeys, and observe creation-route-adapter/legacy-invitation
   traffic.
8. Rehearse governed impact, tombstone retention, and PostgreSQL constraints,
   then enable permanent deletion only after a recoverable scheduled-purge drill.
9. Complete responsive visual/reduced-motion/bundle UAT, then observe one
   compatibility release before separately approving v1/legacy removal.

After production acceptance, prioritize the observability dashboards and alerts
defined in section 15 and compatibility cleanup. These follow-ups may not weaken
idempotency, scope isolation, safe-phase privacy, or additive-data retention.

## 19. V3 scope, precedence, and issue identifiers

This v3 text is normative for the internal-beta changes defined below. Where a
v2 sentence couples deep mode to thinking, treats an access code as a direct
membership grant, synthesizes a workspace owner from platform authority, or
allows an uncontrolled workspace cascade, this v3 text supersedes it. Unaffected
v2 contracts, especially ChatTurn/SSE, section 6's four authority levels, and
section 11's compatibility window, remain in force.

The ownership-continuity specification remains the prerequisite authority for
canonical ownership, transfer, and offboarding. Sections 20--22 reuse its
transaction, impact, audit, idempotency, and notification primitives. They do
not use `SpaceAccessRequest` as a generic workflow table. Five v3 hardening
amendments explicitly supersede the ownership document where its own precedence
clause would otherwise conflict: section 6's scoped capability grants plus
force actor-target separation supersede ownership §§6.2/8.2; section 20.3's one
global lock order supersedes ownership §§8.3/12; section 20.2's deferred owner-
mirror enforcement supplements ownership §7.1; and section 13's deletion-only
snapshot + nullable `OwnershipTransfer.space` supersedes its §7.2 `PROTECT`.
Section 20.4 refines ownership §§3/8.3 notification wording: the outbox row is
atomic with business state, while only external delivery occurs after commit.
All other ownership behavior remains normative. Any implementation found outside the requested
`fix/v1.74.1-acceptance-bugs` / `82231f5` baseline is non-baseline evidence, not
proof that this specification is shipped.

The issue IDs used by tests and release evidence are:

| ID | Backlog item | Normative landing |
|---|---|---|
| IB-01 | 一.1 create-workspace approval | Sections 20--21 |
| IB-02 | 一.2 invitation/access/member workflow | Sections 12.4, 14.5, and 24 |
| IB-03 | 一.3 platform Knowledge workspace ownership | Sections 12.4, 14.7, and 25.1 |
| IB-04 | 一.4 Scenario Templates explanation | Sections 14.7 and 25.2 |
| IB-05 | 一.5 discovery search/cards/classification | Sections 14.4 and 23 |
| IB-06 | 一.6 modal cannot close/navigation load failure | Sections 14.8 and 26 |
| IB-07 | 一.7 fixed models and independent thinking | Sections 4--7 and 25.3/J |
| IB-A | 二.A model configuration mismatch | Sections 7, 15.4, and 25.3/A |
| IB-B | 二.B unused capability-navigation flag | Sections 11, 12.2, and 25.3/B |
| IB-C | 二.C login destination | Sections 12.2, 14.2, and 25.3/C |
| IB-D | 二.D platform chat path | Sections 6, 25.3/D, and 25.4 |
| IB-E | 二.E historical QA superusers | Sections 15.4 and 25.3/E |
| IB-F | 二.F large frontend chunks | Sections 15.1 and 25.3/F |
| IB-G | 二.G misleading container tests | Sections 15.4, 17, and 25.3/G |
| IB-H | 二.H repository/product naming | Sections 15.4 and 25.3/H |
| IB-I | 二.I ownership-continuity prerequisite | Sections 13, 19--22, and 25.3/I |
| IB-J | 二.J effective model/mode/budget display | Sections 5, 14.1, and 25.3/J |
| IB-DEL | Locked delete-workspace requirement | Sections 20 and 22 |

All v3 implementation rows are `pending` until code, PostgreSQL, browser, and
release evidence exists. A specification assertion is never implementation
evidence.

## 20. Shared governed-action infrastructure

### 20.1 Persistence model

Workspace creation and permanent deletion use the same service-level primitives
as ownership transfer and offboarding: actor snapshotting, deterministic scope
resolution, impact calculation, idempotency, reviewer separation, row locking,
atomic audit/outbox emission, and post-commit delivery. Shared behavior is implemented as
common services and mixins, not by overloading the ownership or access-request
tables.

`GovernedActionRequest` is the common envelope:

| Field | Contract |
|---|---|
| `id` | UUID primary key; public request ID |
| `action_type` | `workspace_create` or `workspace_permanent_delete`; extensible enum |
| `requester` / `requester_uuid` | Nullable `SET_NULL` FK plus immutable actor UUID snapshot; user hard deletion remains separately governed |
| `scope_type`, `scope_uuid` | Server-derived review scope; never accepted as client authority |
| `organization`, `business_line`, `target_space` | Organization/business-line are scoped `PROTECT` FKs; target space is nullable `SET_NULL` with immutable UUID snapshot and may detach only through the authorized purge transaction |
| `target_space_uuid` | Immutable target snapshot; null for creation until approval |
| `locator_reservation` | Nullable at the shared-table schema level but action-shape-required: non-null from create or deletion submission through terminal history; a deletion always points at the target space's backfilled live reservation, which becomes tombstoned during purge |
| `status` | State machine in section 20.2 |
| `idempotency_key`, `request_digest` | Submission key/digest only; later operations use `WriteIdempotencyRecord` |
| `request_version` | Positive `bigint`, incremented on every state/route/impact transition and used for CAS |
| `impact_revision` | Positive `bigint` incremented whenever a new impact snapshot is issued |
| `impact_version` | Fixed 32-byte SHA-256 digest, encoded as 64 lower-case hex in APIs; not a counter |
| `impact_expires_at` | Server timestamp after which approval/confirmation must refresh impact |
| `impact_snapshot` | Sanitized JSON object with blocker IDs, versions, policy version, and expiry; no user content or raw token |
| `reviewer` / `reviewer_uuid` | Nullable `SET_NULL` actor and immutable snapshot; used for creation decision or deletion confirmer evidence |
| `reviewed_at`, `reason_code`, `reason_text` | Review evidence; optional text is NFC-normalized and at most 500 Unicode characters, encrypted-at-rest where configured |
| `expires_at`, `scheduled_for`, `started_at`, `completed_at` | Lifecycle timestamps |
| `result_uuid`, `failure_code` | Immutable result/evidence locator and stable machine failure |
| timestamps | Created/updated timestamps controlled by the server |

Typed one-to-one details prevent an unvalidated JSON command bus:

- `WorkspaceCreateRequestDetail` stores normalized name/code, purpose,
  requested visibility, organization/business-line/work-group/location IDs,
  template key/version, and nullable created-space UUID.
- `WorkspaceDeletionRequestDetail` stores immutable space locator, expected
  lifecycle/ownership versions, archived-at, purge-not-before, typed
  confirmation digest (never plaintext), and nullable tombstone UUID.
- `WorkspaceLocatorReservation` is the single namespace table for both live and
  deleted locators: organization UUID + normalized code is unique; state is
  `request_reserved|live|tombstoned|released`; it references at most one live
  space, active creation request, or tombstone as its state requires; historical
  requests may keep a read-only FK to the same row after release/reuse. Creation
  submission reserves/reuses this row under lock, rejection/cancellation/expiry releases
  it, approval changes it to live, and authorized purge changes the same row to
  tombstoned. No cross-table uniqueness assumption is used.
- `WriteIdempotencyRecord` stores actor UUID, operation code, UUID key, request
  digest, target/request UUID, `in_progress|completed|failed` disposition, safe
  result reference, original HTTP status/schema version, expiry, and timestamps.
  `(actor_uuid, operation_code, key)` is unique. It records each submit,
  approve, reject, cancel, confirm, retry, join, member, and notification action;
  the envelope key remains only the creation/deletion submission key.
- `WorkspacePurgeJob` is one-to-one with a deletion request and stores
  `queued|running|failed|completed`, attempt, fenced lease generation/expiry,
  manifest digest, started/completed timestamps, and stable failure code.
  `WorkspacePurgeCheckpoint` stores `(job, store_code, batch_key)` unique,
  expected/ack digest, item/byte counts, last cursor, status, and attempts.
  Stores are `database`, `blob`, `search`, `vector`, and `replay`, extended only
  through a migration and registry contract.
- `GovernedActionOutbox` stores request, event type, recipient, payload version,
  originating request/transition version, delivery state, and retry metadata.
  `(request, event_type, recipient, transition_version)` is unique so delivery
  retries deduplicate without suppressing a later reroute/status event.
- `WorkspaceTombstone` stores the deleted UUID, organization UUID,
  unique locator-reservation FK, `org_slug/space_code` digest and normalized
  reserved components,
  archived/purged timestamps, request UUID, final manifest digest, and retention
  flags. It contains no document/chat content.

`SpaceAccessRequest`, `OwnershipTransfer`, and `GovernedActionRequest` remain
separate typed aggregates. They share functions for idempotency, audit, locking,
impact serialization, and outbox dispatch only.

One-to-one alone does not enforce shape. `DEFERRABLE INITIALLY DEFERRED`
constraint triggers on envelope and both detail tables require exactly one
matching detail at commit, reject the other detail type, and validate the
action/status/target/result matrix across parent and child. Same-table `CHECK`s
handle only local enum/null/range rules. Locator uniqueness is enforced only by
`WorkspaceLocatorReservation`, never by a cross-table assumption.

### 20.2 Constraints and state machines

Creation has one live state, `pending`. Approval performs the database result in
one transaction and transitions directly `pending -> completed`; reject,
requester cancel, and expiry transition `pending -> rejected|cancelled|expired`.
Those four destinations are terminal. A database approval error rolls back and
leaves the request pending. An expected, safely classified command failure is
recorded through the outer idempotency transaction described in §20.4; a fatal
transaction/connection abort may leave no operation row and is safe to retry.
The separately stored workspace provisioning state is `provisioning|ready|failed` and retries
the same created space, not the request or locator.

Deletion transitions `pending -> scheduled -> executing -> completed`.
`pending|scheduled -> cancelled|expired|invalidated` is allowed only before
execution. A store failure transitions `executing -> failed`; the purge
dispatcher alone may transition the same lineage `failed -> executing`, then to
`completed`. Delete terminal states are `completed`, `cancelled`, `expired`, and
`invalidated`; live/blocking states for the one-live-request partial constraint
are `pending`, `scheduled`, `executing`, and `failed`. Deletion has no rejected
state or external reviewer: the owner confirmation is recorded in reviewer/
reviewed-at fields as consent, not as an authority override.

PostgreSQL enforces, rather than merely documents:

- unique `(requester_uuid, action_type, idempotency_key)` and non-empty submit
  digest, plus the operation-level idempotency uniqueness above;
- action/status-specific field `CHECK`s (for example create has no target before
  completion; deletion always has non-null target-space UUID and archive
  timestamp, while its nullable FK may become null only in executing/failed/
  completed authorized purge states);
- at most one live permanent-deletion request per space via a partial
  unique constraint;
- one active owner membership per space via
  `UniqueConstraint(fields=("space",), condition=Q(status="active",
  role="owner"), name="spaces_one_active_owner_membership")`;
- owner membership implies `status='active'` and `expires_at IS NULL`;
- every ownership transfer requires `requested_by_id <> to_owner_id`; a forced
  administrator cannot appoint themselves as the shortcut to membership/chat;
- deferred constraint triggers on `KnowledgeSpace` owner insert/update,
  `SpaceMembership` user/space/role/status/expiry insert/update/delete, and User
  eligibility update verify at commit that
  `KnowledgeSpace.owner_id` equals the active owner membership's `user_id`, and
  that this user remains eligible. Implementations that cannot install this
  PostgreSQL trigger are not release-ready; a service-only assertion is
  insufficient for this release. The function validates only an affected space
  row that still exists at commit, so an authorized guarded purge can delete the
  membership and space in one transaction without a false orphan violation;
- deferred taxonomy/scope triggers defined in section 23; and
- a purge guard trigger defined in section 22.6.

Every transition uses a compare-and-set predicate on status and
`request_version`. Zero updated rows means `409 stale_request_version`, not a
silent success. Reviewer separation is mandatory for creation: the requester
cannot approve their own request. Permanent deletion has no reviewer override;
the owner both requests and confirms as specified in section 22.

### 20.3 One global lock order

Services first resolve immutable IDs without locks, then enter one transaction
and lock the subset they need in this exact order:

1. `User`;
2. `WriteIdempotencyRecord`, then `AuthSession` rows when offboarding;
3. `Organization`, then `BusinessLine`;
4. `WorkspaceLocatorReservation`;
5. `WorkGroup`, `OfficeLocation`, `WorkspaceCreationPolicy`,
   `ScenarioTemplate`, and immutable `ScenarioTemplateRevision` configuration
   rows, in that order;
6. `KnowledgeSpace`;
7. `OrganizationMembership`, `UserRole`/administrator assignments, and
   `AdminRegistrationCode`;
8. `SpaceMembership`;
9. `OwnershipTransfer`;
10. `SpaceAccessCode`, legacy `InviteCode`, `SpaceEmailInvite`,
    `SpaceInvitation`, and `SpaceAccessRequest`;
11. `GovernedActionRequest` and its typed detail;
12. `ChatSession`, then `ChatTurn`;
13. registered deletion dependencies in fixed order: category,
    `ConversationShare`, task/job, retention hold;
14. `WorkspaceTombstone`, `WorkspacePurgeJob`, then purge checkpoints;
15. `Notification`, then governed/action outbox rows.

Multiple IDs of one type are sorted by UUID/primary key. Skipping an unused type
does not alter relative order. This order also governs ownership transfer and
offboarding; their older local sequences are superseded by section 19.

Each lock query is an explicit
`.select_for_update(of=("self",)).order_by("pk")`. It does not lock through a
nullable join. `skip_locked` is allowed only for an outbox dispatcher that will
not later lock an earlier domain row, never for a user transition or purge
claim. A purge dispatcher reads candidate IDs without row locks, then starts a
new transaction and acquires the entire applicable order before CAS-claiming one
job; competing dispatchers lose the CAS or wait without reversing the order.
Under the locks the service re-evaluates actor
status, exact capability, scope, canonical owner, lifecycle version, request
version, and the complete impact snapshot before it writes.

Chat send/recovery locks `User -> KnowledgeSpace -> SpaceMembership ->
ChatSession -> ChatTurn`, rechecks membership/capability after its row lock, and
rechecks the space lifecycle before reserving a turn. This serializes sends with
membership revocation and archive/purge; an archived or purge-scheduled space returns
`409 workspace_not_writable` and cannot acquire a new provider lease.

Membership suspend/remove and user deactivation acquire the same prefix, then
lock that user's active `ChatSession`/`ChatTurn` rows. They increment the
execution fence, revoke SSE/replay authorization, and transition cancellable
Turns before the membership becomes ineffective. A provider call that cannot be
physically stopped may finish remotely, but its stale fence cannot stream or
persist content. Tests race revoke/deactivate against reserve, first token,
saving, disconnect, and recovery; no post-revocation content is delivered.

Every service that creates or changes a deletion blocker acquires the space at
its global-order position before blocker rows and increments its monotonic
`dependency_version`. Impact includes that version and then locks/reads the
registered dependency rows. A plugin or new
task type cannot participate in a workspace until it registers its blocker,
retention, lock-order, snapshot, and purge behavior; otherwise permanent-delete
readiness fails closed with `storage_manifest_unavailable`.

### 20.4 Idempotency, impact, audit, and notification

Each mutation requires a UUID `Idempotency-Key`. Its operation digest includes
normalized command fields, resolved scope, actor UUID, operation code, target,
and expected versions. The operation inserts/locks its
`WriteIdempotencyRecord` in the outer business transaction, then runs the domain
transition in a database savepoint. On success, domain state, audit/outbox, and
the completed original response commit together. A safely classified validation/
provider-independent command failure rolls back only the savepoint, then stores
the failed safe response and audit in the outer transaction. A database or
connection failure that aborts the outer transaction leaves neither domain
change nor durable idempotency claim; retry may acquire the key. Same key/operation/
digest returns the original HTTP status and safe result reference; a currently
running identical operation returns `409 operation_in_progress`; the same key/
operation with another digest returns `409 idempotency_key_reused`. Records are
retained at least 90 days and never expire while the target workflow is live.
Legacy `idempotency_conflict` is a one-window response alias whose payload also
contains canonical code `idempotency_key_reused`; new endpoints emit only the
canonical code.

An impact version is a 32-byte digest, not a count or monotonic integer. It hashes the ordered blocker/resource IDs,
their relevant status/version/update timestamp, applicable retention/policy
version, `dependency_version`, `impact_revision`, and storage manifest version.
Approval or confirmation with an expired
or mismatched impact version returns `409 impact_changed` plus a safe refreshed
summary. It never exposes document titles, message text, invite secrets, or
access-code material.

Internal-beta impact TTL is 10 minutes for creation and 5 minutes for deletion;
the response always carries `impact_expires_at`. A policy revision may shorten
future TTLs but cannot extend an already issued snapshot. Tests freeze the clock
at just before/at expiry and treat expiry as changed impact.

Every service-observed outcome that can commit, including denied, stale,
replayed, cancelled, and safely classified failed operations, writes an
append-only audit event with actor snapshot, target,
request/action IDs, old/new states, exact capability, scope, correlation ID,
idempotency outcome, and safe impact summary. Successful state, audit, and
outbox rows are inserted atomically in the business transaction.
`transaction.on_commit` may only wake the dispatcher; it is never the sole
creation point for an outbox row. Dispatch failure cannot roll back the action
and retries the same transition-version outbox record. An outer transaction or
process crash is represented by database/operational telemetry and recovery,
not by an audit row the failed transaction could not durably write.

## 21. Governed workspace creation

### 21.1 Internal-beta authority and routing

Internal beta uses platform-administrator review, not a trust-on-first-create
model. Any active, non-deactivated registered account may receive
`workspace.creation.request`, but that capability creates a request only. It
never grants organization, business-line, workspace, or chat authority.

The requester selects only visible controlled classification. `business_line_id`
is required and the server derives its organization; `work_group_id` must be an
active child of that business line and every location must belong to the derived
organization. Internal beta routes every valid request to the platform queue.
Neither a submitted scope ID nor the requester's current workspace role can
alter that route.

Because beta accounts have no authoritative organization membership, selectable
business lines come from an explicit immutable `WorkspaceCreationPolicy`
revision, not from a fabricated user scope. Rows are unique by
`(business_line, revision)` and store `draft|active|retired`,
`audience=registered_beta|authoritative_members`,
`review_route=platform|nearest_scope`, effective dates, and reviewer-separation
requirement. A partial unique constraint permits at most one active revision per
business line; activation locks and retires the prior active row. Each request
pins the exact policy UUID/revision. Internal beta permits only active
`registered_beta + platform` revisions. Seeing a requestable taxonomy value does
not expose private workspaces or grant that scope. The policy revision enters
the request digest and impact and is rechecked at approval.

The migration intentionally activates no business line. A platform admin uses
the policy API/UI to create and activate an explicit allowlist revision; release
readiness requires at least one active beta policy and at least two eligible
platform reviewers before `WORKSPACE_CREATION_APPROVAL` can enable. This
fail-closed bootstrap avoids silently exposing every existing business line.

When Microsoft identity and authoritative organization/manager relationships
exist, routing becomes server-derived nearest-scope routing in this order:
eligible business-line approver, eligible organization approver, then platform
fallback. The first tier with an active reviewer set owns the request; upward
fallback does not grant the requester upward authority. This future router is
flagged and cannot activate from self-asserted profile fields. A route change
increments `request_version`, writes audit, and notifies the new reviewer set.

### 21.2 Submission and review behavior

Submission normalizes Unicode name, lower-case slug code, purpose, visibility,
and sorted taxonomy IDs before calculating the digest. The server rejects
unknown fields and validates name/code uniqueness case-insensitively within the
derived organization. A uniqueness conflict found at submission is `409
space_locator_conflict`; the same race found at approval returns the same code
without resolving the request.

One requester may have at most one pending request for the same normalized
organization/code tuple. Rate limits are action-specific and shared consistently
across workers; the global read throttle is not used as a creation workflow
guard. The response contains request ID, status, submitted safe fields,
`request_version`, `expires_at`, and status URL, but no reviewer identities.

Only a reviewer with the exact routed capability may inspect impact or resolve
the request. Platform review is
`platform.workspace_creation_requests.manage`; the future organization and
business-line capabilities are separately named and scoped. A reviewer cannot
approve their own request. A platform administrator who needs a workspace must
be approved by a different eligible platform administrator; absence of a second
reviewer is `409 reviewer_separation_unavailable`, not permission to self-approve.

Rejection requires an allowlisted reason code plus optional bounded text. The
requester may cancel only `pending`; expiration is a scheduled compare-and-set.
Approve/reject/cancel/expire races lock the request row and produce one terminal
outcome. Repeated delivery with the same idempotency key returns that outcome.

### 21.3 Atomic approval result

Approval locks according to section 20.3, recomputes taxonomy, scope,
eligibility, locator uniqueness, template availability/version, and impact, then
atomically:

1. creates one `KnowledgeSpace` in active lifecycle state;
2. sets the requester as `KnowledgeSpace.owner`;
3. creates exactly one active, non-expiring owner membership mirror;
4. attaches controlled classification and a pinned template version;
5. records request completion and result UUID;
6. emits the audit event; and
7. inserts requester/reviewer outbox rows atomically; delivery occurs after
   commit.

Any failure rolls back all seven database effects. Template materialization and
search/index provisioning run from idempotent post-commit jobs; until ready the
space is visible to its owner with explicit `provisioning` status and chat/
ingest writes return `409 workspace_provisioning`. A failed job is retryable and
does not create another space.

### 21.4 Creation acceptance matrix

Required tests cover active/inactive requester, hidden/cross-scope taxonomy,
case-insensitive locator collision, requester/reviewer separation, cancellation
versus approval, two reviewers approving concurrently, template version change,
outbox retry, and identical/conflicting idempotency replay. PostgreSQL tests must
prove one space/owner mirror under concurrency and prove the deferred owner
trigger. API tests prove a creation request cannot be used as `chat.ask` or as
membership in any existing space. Future-routing tests use authoritative fixture
claims and prove business-line -> organization -> platform fallback without
upward authorization. Policy tests cover zero-policy readiness, immutable
revision, at-most-one active revision, activation race, reviewer-count gate,
request pinning, and policy retirement/change causing refreshed impact rather
than silent reroute.

## 22. Archive and permanent workspace deletion

### 22.1 Authority and two distinct stages

Deletion is current-canonical-owner-only. Platform, governance, organization,
business-line, knowledge-admin, and Django-admin authority does not substitute
for ownership. Both archive and every permanent-delete mutation re-read the
canonical owner and exact owner capability under lock. An emergency legal or
operator procedure is deliberately outside the product API and requires a
separately approved break-glass specification.

Stage 1 is `POST /spaces/{id}/archive/` by the current owner. It increments
`lifecycle_version`, makes the space read-only, rejects new chat/ingest/invite/
access/share creation or extension, removes it from general discovery, releases provider work
that has not started, and retains owner access to impact, export, dependency
cleanup, restore, and audit views. Archive is reversible while no purge has
started. Restore is owner-only, increments lifecycle version, and returns
`409 deletion_request_active` until any pending/scheduled deletion request has
been explicitly cancelled.

Stage 2 begins only from archived state. Impact is read first, the owner creates
one deletion request, then confirms the fresh version by typing the exact
server-returned normalized `org_slug/space_code` and checking an explicit
permanence acknowledgement. Pasting is permitted for accessibility; comparison
is exact after Unicode NFC normalization and does not trim or case-fold beyond
the canonical locator. The plaintext phrase is held in component memory only
and is never persisted, logged, placed in analytics, or sent in an URL.

An ownership transfer, externally changed lifecycle version, or new blocker
invalidates a pending or scheduled request before execution. Locator mutation is
forbidden while archived or while a deletion request is live; restore first
requires cancellation. The new owner must obtain a fresh impact and create a
new request; a deletion request is never inherited as consent. The current owner
may cancel before `executing`. Cancel does not restore the workspace
automatically.

### 22.2 Impact precheck and stable blockers

The impact response returns safe counts, blocker objects (`kind`, opaque ID,
status, remediation route), retention dates, expected lifecycle/ownership
versions, the canonical confirmation phrase, and `impact_version`. It never
returns document/message text or secret material.

The request and confirmation endpoints return `409` while any of these blockers
exists:

| Stable code | Blocking dependency | Clear condition |
|---|---|---|
| `active_shares` | Active conversation/document share or public link | Revoke/expire every share and let revocation commit |
| `open_tasks` | Queued/running ingestion, review, gap, evaluation, export, or other space task | Finish or cancel into a terminal state |
| `child_categories` | Any active space-scoped child category/classification node | Explicitly delete/rehome through its own workflow |
| `ownership_transition_pending` | Non-terminal ownership transfer or offboarding succession | Resolve or cancel the ownership workflow |
| `active_chat_execution` | Reserved/streaming ChatTurn, provider lease, replay lease, or non-terminal recovery | Reach terminal state and expire the replay/lease safety window |
| `retention_hold` | Legal, audit, investigation, backup, or business-record hold | Authorized hold workflow releases it; owner cannot override |
| `storage_manifest_unavailable` | Content/blob/index inventory cannot be produced consistently | Inventory service recovers and a fresh impact is issued |

The minimum active-chat safety window is 15 minutes after the last terminal/
lease event. Dependency counts alone do not satisfy confirmation; IDs and
versions participate in `impact_version`. A new blocker after confirmation moves
the scheduled request to `invalidated` before deletion and notifies the owner.

### 22.3 Retention and scheduling

For internal beta, purge cannot begin before both `archived_at + 30 days` and
`confirmed_at + 7 days`; applicable legal/business/audit/backup retention may
extend that date. The effective `purge_not_before` is the latest of all dates and
is returned to the owner. These periods are server policy, not request fields;
changing them is a versioned policy migration and cannot shorten an already
scheduled request.

A scheduled workspace remains read-only and is labelled with purge date and
cancel action. The dispatcher follows section 20.3's unlocked-candidate/full-
order-CAS claim, changes one request to `executing`, creates the tombstone and
purge job/checkpoints, and records the frozen storage manifest digest under the
same lock/revalidation contract. Clock-only eligibility never
bypasses a fresh blocker/hold/owner/lifecycle check.

### 22.4 Data disposition

"Permanent" means removal of eligible live workspace content, not erasure of
audit or retained business evidence:

| Data class | At archive/schedule | After retention and authorized purge |
|---|---|---|
| Documents, versions, chunks, embeddings/index entries, source blobs | Read-only; inventoried and retained | Explicit, idempotent logical cascade and storage deletion |
| Chat sessions/messages/turns/citations/replay payloads | No new writes; active execution must drain | Explicit logical cascade after replay/retention expiry |
| Memberships, invitations, access codes/requests, shares, workspace policies | New grants/create/extend are frozen; blocker-reducing revoke, reject, cancel, expire, task cancel, category rehome/delete, and authorized hold release remain available | Revoked/expired then explicitly deleted or detached by the fixed schema matrix below |
| Space-scoped categories and open tasks | Must be resolved before confirmation | No implicit surprise cascade; only terminal, non-record artifacts are eligible |
| Completed reviews, approvals, exports, task outcomes, ownership transfers, governed requests | Preserved as business evidence with actor/space UUID snapshots | FK detaches with `SET_NULL`/snapshot; never cascades from workspace deletion |
| Audit log, security events, retention/legal holds | Append-only and preserved | Retained by governing policy; never cascades |
| Workspace tombstone | Created/reserved before content purge | Minimal locator/UUID/manifest evidence retained indefinitely to prevent reuse |

The following model/FK matrix is the migration and test oracle; “snapshot” means
immutable `space_uuid`, organization UUID, locator digest, relevant source-row
UUIDs, and nullable tombstone FK, never copied content:

| Model/relation | Final FK and purge behavior | Migration owner |
|---|---|---|
| `knowledge.DocumentChunk`, `knowledge.Document` (including versions), blobs/search/vector entries | Eligible content; existing space/document `CASCADE` may remain only as a backstop. Purge checkpoints explicitly delete chunks/index/blob, then document rows. No document metadata survives workspace purge. | `knowledge.workspace_retention_contract` |
| `knowledge.IngestionJob` and scoped `BatchImportResultRecord` | Queued/running is `open_tasks`. Terminal outcome uses nullable `SET_NULL` document/space plus snapshot; clear task ID, raw error/result details, and per-file names, retaining controlled status/count/timestamps only. New batch records require space; ambiguous legacy rows are `legacy_scope_unknown` migration exceptions, not silently attached. | same knowledge migration |
| Space-scoped `DocumentCategory` hierarchy | Migration adds nullable space and parent. Active children block; after explicit child resolution, remaining space-root categories are eligible explicit deletes with space `CASCADE` backstop. Global categories are untouched. | same knowledge migration |
| `chat.Citation`, `Message`, `ChatTurn`, `ChatSession`, replay payload | Eligible conversation content; explicit child-first batches, then existing `CASCADE` backstop. Redis replay keys must acknowledge the same manifest. | `chat.workspace_retention_contract` |
| `chat.ConversationShare` | Active rows block; revoke/expire is allowed while archived. Revoked rows are eligible explicit deletes before session. | same chat migration |
| `chat.Feedback` | Non-terminal review is `open_tasks`. Terminal row is retained with nullable `SET_NULL` space/message plus snapshot; purge clears comment, suggested source, review context, and free-text resolution, retaining controlled rating/reason/status/resolution code/timestamps. | same chat migration |
| `chat.FeedbackReviewEvent` | Fixed nullable `SET_NULL` space/feedback plus snapshot; retain event/from/to/actor UUID/time, clear free-text notes. Never cascades from feedback/message/space. | same chat migration |
| `chat.KnowledgeGapTicket` | Open/in-progress blocks. Terminal row uses nullable `SET_NULL` space/feedback plus snapshot; retain normalized question hash, status/priority/resolution code/actor/time and clear question/source/free-text resolution. | same chat migration |
| `chat.ComplianceExportJob` | Queued/processing blocks. Terminal row uses nullable `SET_NULL` space plus snapshot; delete result file/blob and path, retain dataset/status/row-count/error-code/timestamps. | same chat migration |
| `chat.ModelInvocation` | Nullable `SET_NULL` content/space links plus UUID snapshot; retain only already-safe aggregate telemetry until its normal telemetry retention, then delete. | same chat migration |
| `spaces.SpaceMembership`, legacy/new invitation/access-code/access-request rows, usage daily/summary, workspace-local policy runtime rows | Credentials/access/personalization are explicitly revoked then deleted. Immutable `GovernancePolicy` revisions instead use nullable `SET_NULL` space + snapshot and remain evidence. | `spaces.0015_workspace_deletion_stage_a` + `spaces.0016_workspace_deletion_stage_c` |
| `spaces.OwnershipTransfer` | Nullable `SET_NULL` space plus snapshot as specified in §13; all actor FKs retain ownership-policy behavior. | same spaces migration |
| `scenario_templates.ScenarioTemplateApplication` | Space is nullable `SET_NULL`; existing `template` becomes nullable `SET_NULL` with immutable template UUID/key snapshot, while new `template_revision` is `PROTECT`. Retain application outcome/revision hash and space/tombstone/revision snapshots; clear mutable `template_snapshot`/task IDs. Published source revisions remain independent and immutable. | `scenario_templates.workspace_retention_contract` |
| `audit.AuditLog`, security events | Fixed nullable `SET_NULL` workspace/actor links where present plus immutable target/scope/actor UUID and tombstone/request reference; never cascade. Append-only governing retention. | `audit.workspace_retention_contract` |
| Retention/legal holds | Fixed nullable `SET_NULL` live-space FK plus immutable space/organization/locator snapshot and tombstone reference. Active holds block and remain governed evidence after purge. | `spaces.0015_workspace_deletion_stage_a` + `spaces.0016_workspace_deletion_stage_c` |
| `GovernedActionRequest`, details, purge job/checkpoints, locator reservation, tombstone | Nullable `SET_NULL` live-space FK with immutable snapshots; retained. Delivered outbox and expired operation-idempotency rows follow their own retention only after the target is terminal. | `spaces.0015_workspace_deletion_stage_a` + `spaces.0016_workspace_deletion_stage_c` |
| `notifications.Notification` | No live authorization fact. On purge, action becomes terminal `resource_deleted`, deep link/actions are cleared, and only safe resource UUID/type remains until normal notification retention. | `notifications.0003_actionable_notification_contract` |

Any installed space-bearing model absent from this registry makes
`purge_registry=not_ready` and `storage_manifest_unavailable`; feature enablement
and confirmation fail closed. Adding a model requires a migration-owned row in
this matrix/registry and its blocker, snapshot, purge, and retention tests.
Every `legacy_scope_unknown` or `legacy_revision_unknown` row that could refer to
the target must be resolved into an exact target or proved unrelated by an
audited migration exception before delete readiness can become true; purge
never guesses from a name, path, title, tag, or template label.

No retained row contains a dangling FK. Each relation has one fixed database FK
action in the schema matrix above; dynamic “PROTECT until purge, then SET_NULL”
is not claimed. Workflow guards and blockers protect active rows, while the
purge transaction explicitly detaches fixed-`SET_NULL` evidence before deleting
eligible content. Eligible content is deleted by a manifest-driven service in
deterministic batches; an eligible `CASCADE` is only a referential backstop after
the explicit batch is empty, never the orchestration mechanism.

Blob, search-index, vector-index, replay, and database deletion form an
idempotent purge saga. Each store/batch records the checkpoint fields from
section 20.1. The request
becomes `completed` only when every eligible store acknowledges the same
manifest and the tombstone is durable. Failure stays `executing` or `failed`
with the space inaccessible and the same job resumable; it never reports success
or starts a second lineage.

### 22.5 Restore, backup, and observability

Before `executing`, owner cancellation preserves data and allows a separate
restore. Once execution starts, the product reports `purge_in_progress`; no
restore is promised. Backup retention is not presented as an end-user undo.
Operators must prove backup expiry/restore policy in the PostgreSQL release gate
and must not selectively resurrect a purged locator into the live namespace.

Metrics include request/confirm/cancel/invalidate counts, blocker kinds, schedule
lag, per-store manifest progress, retry/failure codes, and end-to-end purge age.
They exclude confirmation text, codes, titles, chat, document, and actor PII.
Alerts fire for a job stuck in one phase, manifest mismatch, tombstone conflict,
or any live row referencing a purged UUID without an allowed snapshot.

### 22.6 PostgreSQL enforcement and acceptance

A PostgreSQL `BEFORE DELETE` trigger on `KnowledgeSpace` rejects deletion unless
there is exactly one matching governed request whose persisted status is
`executing`, its target UUID/lifecycle/ownership/impact/manifest values match,
its retention date has passed, its tombstone/locator reservation exists, all
non-database store checkpoints acknowledge the frozen manifest, and the database
checkpoint is `running` with the same fenced lease. The service must separately
hold the rows under §20.3; a trigger does not pretend to inspect lock ownership.
Direct ORM deletion, Django Admin deletion,
raw maintenance scripts, and a plain FK cascade therefore fail closed. The purge
service deletes eligible dependants explicitly, detaches retained evidence, and
deletes the space row last. No application setting may disable this trigger.

Tests run on real PostgreSQL and cover: non-owner at every authority level;
unarchived request; every blocker independently; changed impact/owner/lifecycle;
wrong phrase and Unicode/case variants; duplicate confirms; confirm/cancel and
send/purge races; retention boundary; trigger denial of ORM/Admin/raw delete;
storage failure/retry; audit/outbox failure; retained FK integrity; tombstone
locator non-reuse; and simultaneous ownership/offboarding/deletion. A successful
test asserts eligible content absence, retained business/audit evidence, manifest
agreement, one tombstone, and one completed request.

## 23. Discovery and controlled workspace taxonomy

### 23.1 Taxonomy model and meaning

The authoritative hierarchy is:

`Organization -> BusinessLine -> WorkGroup`, with `OfficeLocation` owned by the
organization and attached many-to-many to workspaces.

- `Organization` is the tenant/data boundary and future enterprise-identity
  anchor.
- `BusinessLine` remains the existing authorization/reporting scope.
- `WorkGroup` is a controlled classification child of exactly one business line.
  A label such as **Assurance Group 12345** is a WorkGroup display name; its
  immutable UUID and normalized code are the stable identity.
- `OfficeLocation` is controlled organization classification. A workspace may
  have zero or more only when exempt/legacy, otherwise one or more.
- WorkGroup and location do not themselves grant capability or membership. The
  authorization boundary remains organization/business-line/workspace.
- Free-form tags remain optional search/display metadata. They cannot replace a
  controlled field and are forbidden inputs to routing, capability resolution,
  retention, or compliance reports.

`WorkGroup` has UUID, business line, normalized code, display name, optional
description, active flag, sort order, and timestamps. `OfficeLocation` has the
same shape under organization plus optional locale/time-zone metadata.
`KnowledgeSpace` gains nullable `work_group`, M2M office locations, and
`classification_state = complete|legacy_unclassified|exempt`. New ordinary
approvals require `complete`; legacy rows are not guessed from names/tags.

Controlled mutation uses an exact kind/scope map: business lines require
`platform.organizations.manage` or organization-scoped
`governance.business_lines.manage`; WorkGroups require
`platform.taxonomy.manage` or organization/business-line-scoped
`governance.taxonomy.manage`; office locations require
`platform.taxonomy.manage` or organization-scoped
`governance.taxonomy.manage` and are denied to a business-line-only admin.
Every endpoint rechecks the parent scope; no generic taxonomy grant crosses it.
Deactivation preserves historical references, removes the value from new
selectors, and blocks new approvals; it never silently rewrites spaces. Moving
a WorkGroup to another business line or a location to another organization is
not supported. Create a replacement and migrate spaces through an audited,
impact-checked operation.

### 23.2 Discovery authorization and search

Discovery applies visibility and effective account/space scope in the database
query before search, facets, ranking, counts, or pagination. A private hidden
space cannot affect result count, facet count, popular rank, cursor, or latency
bucket merely because its text matches. Search never grants access.

`q` is NFC-normalized, trimmed, 1--100 Unicode characters, and matched against
safe name, code, bounded description, business-line, WorkGroup, office-location,
and non-authoritative tag labels. PostgreSQL uses a language-neutral normalized
search vector plus `pg_trgm` indexes for controlled prefix/fuzzy matching. An
index migration is concurrent where PostgreSQL permits and is rehearsed on a
copy. SQLite substring behavior is not acceptance evidence.

Filters are ANDed across dimensions and ORed within repeated location values.
Every requested ID is checked for visibility and cross-table consistency;
syntactically invalid IDs return 400, while well-formed unknown or out-of-scope
filter IDs return a normal empty cursor page with no facets, never a cross-scope
name or existence distinction. Cursor ordering is
stable and includes `(sort_score, normalized_name, space_uuid)`; a policy or
filter change invalidates the cursor with `400 invalid_cursor`.

Each card shows safe name/code, purpose summary, business line, WorkGroup,
locations, access state, and one allowed action. It never shows member count,
owner contact, documents, activity detail, or a private-space existence hint to
an unauthorized account.

When transient rows overlap, one deterministic access state is returned in this
priority: `member`, then valid targeted `invited`, then pending access request,
then `requestable`. Terminal/expired rows never outrank a live state and lazy/
scheduled cleanup must converge to the same result.

### 23.3 Frequent and popular cards

`WorkspaceUsageDaily(user, space, date)` is the source of truth, unique by that
triple, and stores privacy-minimal interaction count plus last interaction for
that UTC day. It is updated only for an authorized open, chat terminal event, or
document action and retained 35 days. `WorkspaceUsageSummary` is unique by
`(user, space)` and is idempotently recomputed from the last 30 daily buckets;
it stores `interaction_count_30d`, `last_interacted_at`, and `computed_through`.
A user's `frequent` cards are their currently accessible spaces ordered
by `(interaction_count_30d DESC, last_interacted_at DESC, space_uuid ASC)`, at
most five. No other user's activity participates.

`popular` considers only explicitly discoverable spaces after the caller's
authorization filter. It counts distinct active users over 30 days, publishes
only buckets `5-9`, `10-24`, `25-49`, `50+`, suppresses values below five, and
orders by `(bucket DESC, normalized_name ASC, space_uuid ASC)`. The UI labels it
as organization-wide activity, not a recommendation or permission. Internal
beta may legitimately show no popular cards.

Usage rows contain no search terms, question text, document titles, or model
output. Daily buckets older than 35 days are deleted; summary rows are
recomputed after bucket expiry and deleted when no bucket/access remains.
Deactivated users stop contributing. Discovery metrics record query
duration, safe result-count bucket, cache outcome, and filter kinds only.

### 23.4 Discovery acceptance

Tests cover exact/prefix/Unicode search, every facet and combination, inactive
taxonomy, legacy/exempt spaces, cross-organization forged IDs, private result/
facet/rank non-disclosure, stable cursor pagination, stale cursor, frequent
personalization, k-anonymous popular suppression, deactivated users, empty/error
states, and create-form dependent selectors. PostgreSQL tests prove trigram/
search indexes and deferred organization-business-line-WorkGroup-location
triggers. Browser tests prove keyboard-accessible cards/filters, URL-backed
search state, back/forward restoration, and no duplicate request per logical
resource.

## 24. Access codes, targeted invitations, notifications, and members

### 24.1 Two different entry contracts

An **access code** is a space locator/request credential. Redeeming it never
creates membership. It validates the code and account, then creates or returns
one pending owner-reviewed `SpaceAccessRequest`. A **targeted invitation** is an
owner-authorized membership offer to one user or verified email and one allowed
role. Recipient acceptance directly creates/reactivates that membership; it
does not require a second owner approval.

A caller may also submit `POST /spaces/{id}/access-requests/` without a code
when authorization-filtered Discovery already exposes that exact workspace as
`requestable`. This is not a third grant semantic: it creates the same pending,
owner-reviewed request and never membership. The request records
`source_kind=access_code|discovery`; an access-code source requires the locked
code/policy snapshot, while a discovery source requires the discoverability
policy revision and has no code FK. Both share the `(space, user, pending)`
constraint, approval state machine, role ceiling, audit, and notification path.

`SpaceAccessCode` stores a random-secret hash and display prefix, space, creator,
active/expiry state, request-role ceiling (`member` or `guest` in beta), use/
pending limits, policy version, and timestamps. Raw codes are returned once at
creation, never stored, listed, logged, notified, or included in URLs. Rotation
invalidates future redemption but does not decide already pending requests.

`SpaceInvitation` stores space, inviter, immutable target user UUID or a
normalized-email HMAC plus encrypted delivery address, a canonical `target_key`
(`user:{uuid}` or `email:{hmac}`), proposed non-owner role, token hash/prefix,
policy/ownership version, `pending|accepted|declined|expired|revoked|invalidated`,
expiry (maximum seven days in beta), recipient/reviewer timestamps, and
resulting membership UUID. The encrypted address is available only to the
delivery/verified-email binding service, is never a list/audit/log field, and is
cleared after terminal notification retention; the HMAC/snapshot remains for
deduplication evidence. Tokens are random, single-use, returned once, and
accepted only by the authenticated target (or an account with the same verified
email).

The existing reusable `InviteCode` direct-membership path is called **legacy
invitation code** during section 11's single compatibility release. It remains
limited to `member|guest`, is measured separately, and is never rendered or
documented as the new access-code flow. New UI and new API clients cannot create
it. Removal still requires separate approval after zero observed use.

PostgreSQL makes `SpaceAccessCode.secret_hash` and
`SpaceInvitation.token_hash` unique. It enforces one pending access request per
`(space, user)` and one pending invitation per `(space, target_key)` with partial
unique constraints. A shape check requires exactly one invitation target form.
When a verified email becomes a user target, a locked canonicalization step
merges or invalidates an existing email/user duplicate before acceptance.
Token/code use counters are incremented
under a self-only row lock and cannot exceed the configured ceiling.

Both credentials contain at least 128 bits from the operating-system CSPRNG.
Lookup stores a key-versioned HMAC-SHA-256 under a separately managed server
pepper plus a non-secret display prefix; comparison is constant-time. Pepper
rotation accepts active key versions during a bounded migration and never logs
raw input. A database-only leak is therefore not a usable credential list.

### 24.2 Access-request workflow

Code redemption is rate-limited with a shared multi-worker store and constant-
shape invalid/expired/out-of-scope errors. A valid redemption creates at most
one pending request per `(space, user)` under a partial unique constraint. It
does not switch active space. The requester sees `pending` in Discovery and may
cancel; the current owner receives an actionable notification.

`SpaceAccessRequest` has `pending|approved|rejected|cancelled|expired|invalidated`,
an independent `expires_at` fixed to submission + 14 days in beta, monotonic
version, conditional source/code/discovery-policy snapshot, bounded reason,
decision evidence, and resulting membership UUID. A deferred shape trigger
requires exactly the fields for its `source_kind`. Code rotation/revocation/
expiry blocks new redemption but does
not retroactively decide a pending request; only request expiry or a locked owner
decision does. Expiry is handled lazily on read/action and by an hourly CAS job,
with one terminal notification.

Owner approve/reject locks the required subset in section 20.3 order (including
`SpaceMembership` before access-request rows), then rechecks owner, request,
code policy version, role ceiling, space lifecycle, user status, and existing
membership. Approval creates or
reactivates exactly one non-owner membership; rejection creates none and requires
a reason code. Concurrent approve/reject yields one outcome. Repeated action is
idempotent and returns the existing terminal state. The notification/audit/
outbox rows commit atomically with that terminal state; external delivery is
post-commit and never precedes membership durability.

### 24.3 Invitation and notification workflow

Creating an invitation checks `workspace.invites.manage` plus the inviter's
ability to grant the requested role. `owner` is rejected; ownership uses the
ownership-transfer service. At acceptance the service rechecks inviter/owner
grant authority, target identity, space lifecycle, role ceiling, account state,
token hash/expiry, and invitation version under section 20's lock order. An
ownership or policy change that removes authority invalidates the invitation.

If an active membership already exists, acceptance never creates a duplicate or
downgrades a stronger role. It returns `200 already_member` when no authorized
change is needed, while atomically setting the invitation to `accepted`,
consuming its token, and recording the existing membership UUID; an explicit
role change uses member update after acceptance.
Decline creates no membership. Accept/decline races produce one terminal result
and the losing call returns `409 invitation_already_resolved` with safe state.

Any transaction that first establishes effective membership through invitation
acceptance, access approval, or ownership transfer locks the user's other
pending join aggregates for that space in the section 20.3 order. It marks them
`invalidated` in the same transaction, except that the invitation currently
being accepted becomes `accepted`. If access approval wins first, later
invitation acceptance follows the `already_member` rule and consumes that
invitation without changing role. Thus Discovery cannot remain `pending` or
`invited` after membership exists, and no race creates a duplicate membership.

Invitation-recipient notifications deep-link to the invitation card on
`/spaces/discover`; allowed actions are `accept` and `decline`. Access-request
notifications deep-link the current owner to the workspace access-request panel;
allowed actions are `approve` and `reject`. Server-generated deep links are
selected from an allowlist by resource type/ID, are same-origin, and never carry
tokens/codes. The API does not accept a client-provided redirect URL.

Notification and resource action commit in the same transaction: the
notification moves `unread|read -> actioned` only if the invitation/request
transition succeeds. A stale notification renders the terminal resource state
with no action buttons. Mark-read alone never accepts or rejects anything.
Email/push delivery is an outbox side effect and is not membership evidence.

### 24.4 Interaction states

Discovery displays exactly one of `member`, `invited`, `pending`, or
`requestable`. Invitation acceptance shows progress, disables duplicate submit,
and on success refreshes capability/membership before offering “Open space.”
Access-code submission shows “Request sent” and never says “Joined.” Closing the
dialog while the request is in flight closes it immediately; a late response may
update notification/discovery state but cannot reopen the modal, switch active
space, or update an unmounted component. A committed request is not falsely
described as cancelled by closing the UI.

400 validation, 401, 403, 404/non-disclosure, 409 stale state, 429 with retry
time, network failure, and timeout have distinct recoverable states. No failure
is converted into an empty list or membership success. The code field is cleared
on close/error/success and excluded from analytics and error reporting.

### 24.5 Member lifecycle

The owner member table supports cursor list, invite, create/reactivate through
approved access, update role, suspend/reactivate, and remove. Each row shows user,
non-owner role, effective status/expiry, source, and safe last-change evidence.
Every write requires `workspace.members.manage`, the current canonical owner,
`Idempotency-Key`, expected membership version, and audit reason.

Member CRUD permits `knowledge_admin`, `reviewer`, `member`, and `guest` only.
It cannot create, update, suspend, expire, or remove the canonical owner mirror;
those attempts return `409 ownership_workflow_required`. It cannot grant a role
the actor lacks authority to grant, operate on a deactivated account, cross
space scope, or shorten a retention hold. Removing a member revokes active
sessions/shares according to policy without deleting their historical business/
audit evidence.

If the target of a pending voluntary ownership transfer is removed, one locked
transaction first changes that transfer to `invalidated`, emits its audit/outbox,
then removes the non-owner membership. Removing the current or former owner row
required by an in-progress ownership/offboarding switch remains blocked with
`409 ownership_workflow_required`; generic CRUD never partially edits the owner
switch.

Required PostgreSQL/API/browser tests cover secret hashing/redaction, target
binding, code rotation, pending uniqueness, expiry, role ceilings, existing
membership, every accept/decline/approve/reject race, notification atomicity and
stale rendering, outbox retry, close-during-submit, owner-protection, forged
space/user IDs, and capability refresh after membership change.

## 25. Administration, templates, configuration, and A--J closure

### 25.1 Platform Knowledge metadata and content boundary

The platform Knowledge page is a cross-space metadata inventory, not a global
content-reader role. Each row and export contains document safe title/status/
version timestamps plus organization, business line, WorkGroup, and workspace
name/code/UUID. The page supports the scoped filters in section 12.4, cursor
pagination, and an explicit “Workspace” column that links to safe workspace
metadata. A legacy orphan row shows `Unassigned`; a purged document does not
survive or appear. Retained tombstone locator state belongs to governed deletion/
audit endpoints, not the document inventory.

`platform.knowledge.read` authorizes only this metadata view. Preview, file URL,
download, extracted text, chunks, citations, and chat history still require the
appropriate effective workspace membership and `knowledge.read`/
`knowledge.download` capability. A platform administrator may not turn a
metadata hit into content access or chat through a synthetic owner role. Search,
counts, and filters are scope-safe and audited; CSV/export applies the same
field allowlist and capability.

Tests include documents in multiple spaces with duplicate titles, archived
spaces, legacy orphans, and a purged workspace returning zero document rows;
filters, cursor stability, forged space IDs, metadata-only platform access,
explicit member content access, and absence of storage paths/signed URLs from
every metadata response.

### 25.2 Scenario Templates as versioned clone starting points

Every Templates page and workspace-creation selector explains:

> A scenario template is a versioned starting point for a new workspace. It
> copies structure and default policy; it does not share live workspace data.

A template version may copy category structure, prompt/scenario definitions,
quality rubric, safe workspace defaults, and permitted model-policy references.
It never copies documents, chunks/indexes, chats, members, invitations/access
codes, ownership, audit history, secrets, API credentials, shares, tasks, or
retention holds. Creation pins the chosen immutable template version; later
template edits do not mutate the workspace. Applying/rebasing a template to an
existing workspace is out of scope.

The existing `ScenarioTemplateRevision` is the version authority. The hardening
migration adds `snapshot_hash`, `published_at`, a nullable
`ScenarioTemplate.current_revision` (`PROTECT`), and
`ScenarioTemplateApplication.template_revision` (`PROTECT`). It backfills one
normalized revision for a template that has none, pins every historical
application to the recorded/reconstructed revision or marks it
`legacy_revision_unknown`, and installs a PostgreSQL trigger that rejects UPDATE
or DELETE of a published revision. New edits create another `(template,
version)` row and atomically move the current pointer; create requests pin the
revision UUID, not “latest.”

Existing `ScenarioTemplateAsset`/`TemplateAssetApplication` rows are historical
compatibility evidence only. V3 creation does not create asset applications or
copy their source documents; readiness reports any code path still attempting
that behavior before template-backed creation can enable.

The UI shows scope, version, last update, included component summary, excluded
data warning, preview, and “Use as starting point.” An unavailable or changed
version blocks approval with a fresh impact; it never silently substitutes
latest. Empty state links to documentation and distinguishes “no templates in
scope” from load failure. Capability and audit remain those of existing scoped
template management.

### 25.3 Explicit closure of backlog A--J

| Item | Normative behavior | Required evidence |
|---|---|---|
| A -- model config mismatch | Canonical fast is exactly `qwen3.6-flash`, deep exactly `qwen3.7-plus`; seed, profile, policy, settings alias, readiness, Turn meta, and provider request must agree. A mismatched compatibility alias returns `503 model_policy_not_ready` for a new Turn rather than silently choosing it. | Readiness tests for missing/disabled/mismatched/valid profiles and provider-spy tests for all four mode/thinking combinations. |
| B -- unused `CAPABILITY_NAV` | Backend `CAPABILITY_NAV` controls the `navigation_mode` returned by capability bootstrap and server route availability only. It never enables/disables authorization. Frontend capability navigation renders only when build support and server mode agree; mismatch shows a bounded unavailable state and does not mount/fetch both consoles. | Flag on/off/mismatch route, menu, API-count, direct-URL, and authorization matrix. |
| C -- login destination | After MFA/authentication, redirect priority is validated same-origin `next`, current capability response `default_console`, then `/chat`. Unauthorized/stale targets are recomputed server-side; no open redirect or role-name switch. | Owner/platform/governance/member, multi-role priority, safe/unsafe `next`, default/recent/stale workspace, and flag-pair browser tests. |
| D -- platform chat | Platform authority alone has no `chat.*`. A platform administrator uses the same user identity and must be explicitly invited or owner-approved into the workspace, including a policy-valid guest membership where applicable; platform capability cannot self-add or synthesize owner. Chat/source/history checks use only that effective membership. | Capability/API/browser tests before invitation, pending, accepted member/guest membership, suspension, removal, and cross-space access. |
| E -- historical QA superusers | No pattern deletion. Inventory exact IDs through platform-only `/admin/test-principals/` using explicit `account_purpose=test` metadata or an approved exact allowlist, run the existing ownership/offboarding impact endpoint, protect the last platform admin and retained evidence, then execute exact-ID audited offboarding. Existing 12 is an observation, not a deletion authorization or expected production count. | No-write/operator-only inventory, dry-run impact, approved exact target list, no bulk/pattern endpoint or frontend, last-admin/owner blockers, audit, and post-cleanup health count. |
| F -- large frontend chunks | All console routes, Knowledge, Templates, Discovery, and heavy editor/chart surfaces are route-lazy. The authenticated initial static-import/modulepreload aggregate is <=250 KiB gzip and each later lazy chunk is <=400 KiB gzip. A manifest budget is a CI gate, and shared design tokens/components do not require importing an entire console. | Clean production build manifest with aggregate calculation, per-route network trace, cache/revisit trace, and no eager request for unopened consoles. |
| G -- misleading container tests | Test profiles are named and scoped: backend-unit, repository-quality, PostgreSQL-integration, browser-UAT, and provider-integration. Missing out-of-profile assets or dependencies is `not_run`/`environment_blocked`, never product failure or pass. Model expectations are explicit fixtures, not ambient `.env`; public `/health/ready/` and platform `/admin/system/readiness/` expose only the safe truth defined in §12.5. | Machine-readable report with command/profile/environment fingerprint and four-state result for every gate, plus public/platform readiness authorization and redaction tests. |
| H -- repository/product naming | Product is `KnowPilot`; canonical repository is `fangbo13/Onborading-AI`. `KnowPliot` and machine paths are aliases only. Runtime, scripts, and docs use repository-relative paths and never derive product identity from folder name. | Link/path scan and clean-clone run outside both historical absolute paths. |
| I -- ownership prerequisite | Ownership-continuity migrations, conditional owner uniqueness, deferred owner mirror trigger, transfer/offboarding concurrency, and PostgreSQL evidence must pass before creation approval or permanent deletion can enable. A local branch implementation is not target-baseline or release evidence. | Dependency-graph check plus ownership, offboarding, creation, deletion three-way concurrency suite on PostgreSQL. |
| J -- effective model display | Composer offers only Fast/Deep and independent Thinking. Turn status/details show requested mode, effective mode, read-only effective model ID, effective thinking, budget when applicable, `thinking_snapshot_known`, and bounded fallback reason from server `meta`/status. Unknown historical snapshots render `legacy/unknown`; none is editable or echoed back as model authority. | Meta/history/replay/reconnect/fallback/legacy-unknown UI tests; DOM/request assertion that no model/profile/budget selector or client field exists. |

### 25.4 Effective platform membership path

For clarity, “explicitly joined” in item D normally means an accepted targeted
invitation or an owner-approved access request under section 24. It may also be
the owner membership produced by a valid ownership-continuity transfer performed
by a distinct authorized actor; force-transfer actor and target cannot be the
same person. Platform administrators receive no special self-join endpoint.
Their platform metadata/audit duties remain available through explicit
`platform.*` APIs, while chat/source content uses only the resulting explicit
workspace role. Suspension/offboarding removes that membership exactly as for
any other user.

### 25.5 Navigation rollout pairing

Capability bootstrap returns `navigation_mode=legacy|capability`,
`configuration_revision`, and the existing exact capabilities/default console.
The frontend sends its supported contract version, not an authority flag. A
paired rollout first deploys code supporting both modes, then changes backend
mode and compatible frontend build together. Direct legacy URLs redirect once
without mounting/fetching legacy data when capability mode is active. Rollback
restores legacy navigation but leaves exact backend authorization in force.

### 25.6 Environment and evidence hygiene

Health/readiness expose safe booleans/revisions, never secrets or raw environment
values. Test reports identify Git SHA, migration leafs, database engine,
cache/rate-limit backend, worker count, enabled flags, and frontend build ID.
Only a matching report may support an acceptance claim. A backend-only SQLite
run cannot support PostgreSQL locking/constraint claims; a source test cannot
support built-Chromium motion or bundle claims.

## 26. IB-06 reproduction evidence, root cause, and repair contract

### 26.1 Evidence boundary

The 2026-07-18 investigation was read-only: no login, database write, config
change, image rebuild, or container start/stop was authorized. The existing
browser was at `/login`; login would create an `AuthSession`, and browser control
was also blocked by the session safety policy. Existing 24-hour proxy logs had
no `POST /api/v1/spaces/join/`. Therefore the access-code modal was not falsely
reported as a live click reproduction. Its cause is established by a complete
source/dependency/built-asset chain; the navigation failure is directly observed
in existing Docker logs.

The two symptoms have different direct causes. Rate limiting can prolong an old
join flow's busy state, but it does not explain the modal motion deadlock.

### 26.2 Access-code modal: deterministic source-level cause

Reproduction path represented by the reported UI is: authenticated header
`SpaceSwitcher` -> “Join with access code” -> modal -> X, Cancel, Esc, or mask.
`SpaceSwitcher.tsx` supplies `transitionName="fade"`, while neither source nor
the current built assets contains the required `fade-enter`, `fade-leave`, or
`fade-appear` motion CSS. Ant Design 5.29.3 passes that name through rc-dialog to
rc-motion. rc-motion starts leave and waits for transition/animation end;
rc-dialog supplies no motion deadline. With no matching CSS event, `afterClose`
does not run, `animatedVisible` remains true, and the Portal/focus/scroll lock
remains even though React state set `open=false`. The custom transition was
introduced by commit `96f1dbf`; the original cancel state setter was unchanged.
Fourteen same-pattern modals are in the regression scope, not just this dialog.

A second, submit-time lockout exists: Ant Design's modal handler ignores every
cancel path while `confirmLoading=true`, and current `busy` spans join POST,
space reload, active-space switch, and session reload. Thus X, Cancel, Esc, and
mask also intentionally fail during a potentially long or 429-interrupted chain.

Normative repair behavior is implementation-neutral: every modal uses either
the library's complete default motion or a shipped enter/leave/reduced-motion
definition with a finite deadline. X, Cancel, Esc, and allowed mask close remain
effective during submit. Late results cannot reopen, auto-switch space, retain a
Portal/focus trap/body scroll lock, or write an unmounted view. The new access-
code flow creates a request and never executes the old join/switch chain.

Built-Chromium tests, not jsdom alone, must prove all four close controls idle and
pending, 400/429/network/timeout recovery, no-transition-end deadline, reduced
motion, 20 open/close cycles with zero leaked portals/locks, one POST per submit,
and bounded follow-up requests.

### 26.3 Frequent navigation: observed Docker reproduction and cause

Existing proxy logs show this exact same-class failure at
`http://127.0.0.1:3003`, Chrome 128, 2026-07-18 10:02:20Z--10:03:12Z
(18:02:20--18:03:12 Asia/Shanghai), using an authenticated administrator able to
open legacy `/admin/*` (the logs do not identify an email):

`dashboard -> codes -> announcements -> users -> business-lines -> same-page
refresh -> templates -> business-lines`.

In 37.55 seconds the client first completed 39 API GETs. At
10:02:57.989 `/api/v1/admin/organizations/` returned the first 429 in this
captured switching segment; two milliseconds later business-lines returned 200.
Mixed 200/429 responses continued, and three of the first four quality-page
requests were 429. Each page group was observed again about 200 ms later. The
logs prove duplicate request groups but do not uniquely prove StrictMode or any
other mount cause, so the SPEC does not invent one.

Runtime evidence was `UserRateThrottle=30/minute`, per-process `LocMemCache`,
`CAPABILITY_NAV=false`, and Gunicorn 2 workers x 8 threads. Page mounts fan out
2--5 GETs; old route requests are generally not cancelled, the API client has no
429/`Retry-After` contract or request coalescing, and several pages map errors to
empty arrays. The low global read quota is exhausted by ordinary navigation;
per-process counters then cause nondeterministic interleaved 200/429 across
workers. The observed sequence contained no chat SSE and no notification click,
so neither is assigned as its cause.

### 26.4 Navigation/rate-limit behavior contract

Authenticated idempotent navigation reads use a shared multi-worker limiter,
not `LocMemCache`: sustained 240 requests/minute/user with a 60/10-second burst
for internal beta. Login, chat mutation, access-code attempts, and governed
mutations retain separate security/action limits. All workers make the same
decision for the same identity/history. A 429 includes standards-compliant
`Retry-After` and stable `rate_limited`; the UI shows a retry state and never an
empty success. SSE connections use their own connection quota and are not
charged again for every streamed event.

Each logical resource is requested at most once per route mount. Identical
in-flight GETs are coalesced; route unload aborts cancellable requests, and every
state writer uses an abort/sequence guard so late page A cannot overwrite page
B. Capability navigation on/off mounts and fetches only its selected console.
Notification polling has one cleaned-up interval. SSE controllers/timers are
session-keyed and released on terminal/stop/delete/reset as already required by
section 4.

The regression replays the observed route sequence at normal and rapid cadence,
with one active SSE and with notification polling, on two or more workers. It
asserts zero unintended 429, one request per logical resource/mount, no stale
overwrite, and correct distinct UI for abort, 401, 403, 404, 429, 5xx, timeout,
and network failure. A forced 429 test asserts `Retry-After` behavior. A
deterministic shared-cache test proves that the same parallel history cannot
produce random mixed decisions across workers.

## 27. Internal-beta requirement-to-evidence matrix

This table is the release checklist for the backlog. “Required evidence” means
new evidence on the target implementation; every row is currently pending.

| ID | Model/migration contract | API/capability contract | Frontend and required evidence |
|---|---|---|---|
| IB-01 | Revisioned creation policy + governed envelope/typed detail + single locator namespace + per-operation idempotency + atomic outbox; taxonomy and canonical-owner constraints after ownership migrations | Section 12.3 create/mine/cancel/review/impact/approve/reject; `workspace.creation.request` and beta platform review capability | Bootstrap-unavailable/request/status/reviewer journeys; self-review denial; PostgreSQL locator, double-approve, ownership, idempotency, scope, policy-revision, and outbox tests |
| IB-02 | Hashed `SpaceAccessCode`, targeted `SpaceInvitation.target_key`, independent access/invitation states and pending uniqueness, membership version/audit | Section 12.4 access/invitation/notification/member APIs; owner invite/access/member capabilities; each action has its own idempotency key/version | Discovery accept/decline and owner approve/reject deep links; code/request expiry separation, email binding, secrets, race, replay, role, stale notification, owner-protection, and close-pending tests |
| IB-03 | Existing `Document.space` projection while live; purged documents do not survive, and only deletion/audit tombstone evidence remains | Platform metadata endpoint with `platform.knowledge.read`; workspace membership still gates content/download | Workspace/org/BL/group columns and filters; duplicate title, archived and deleted-resource behavior, forged filter, metadata/content-boundary tests |
| IB-04 | Published immutable `ScenarioTemplateRevision` hash/current pointer and create-detail revision pin; application revision is retained | Exact revision preview/management APIs plus creation impact version; no implicit “latest” substitution | Clone-start explanation, include/exclude preview, empty/error states; prove no document/member/secret/history copy, no asset path, and no later mutation |
| IB-05 | WorkGroup, OfficeLocation, space classification state/M2M, user/space/date daily buckets and recomputed 30-day summary, PG indexes/triggers | Discovery v2 search/filter/highlight and taxonomy reads/management; authorization filter before search/rank | URL-backed search/facets/cards; PG Unicode/index/all-trigger-event tests and private/facet/popularity non-disclosure |
| IB-06 | No data migration; shared rate-limit store is runtime implementation, not a schema shortcut | Access request replaces direct join; 429 includes stable code and `Retry-After` | Built-Chromium modal close/leak suite and observed-route multi-worker navigation/cancel/coalescing/error-state suite in section 26 |
| IB-07 | Turn requested/effective mode/thinking/budget/fallback/known-marker migration and checks; canonical profiles/policy | Send/regenerate accept mode + thinking only; `chat.deep` and `chat.thinking` independent; browser model/budget rejected | Four combinations, defaults, legacy unknown, fallback/race, provider payload, SSE/history/replay, no reasoning persistence, and no model selector |
| IB-A | Canonical exact model IDs and compatible alias readiness | Readiness fails new execution with `503 model_policy_not_ready` on mismatch | Missing/disabled/mismatch/valid readiness plus provider-spy identity tests |
| IB-B | No persistence change | Capability bootstrap owns `navigation_mode`; backend authorization never flag-gated | Flag off/on/mismatch direct-URL/menu/request-count matrix with no dual console mount |
| IB-C | No persistence change | Login uses safe `next`, then server `default_console`, then `/chat` | Platform/org/BL/owner/member/MFA, unsafe redirect, stale space, and paired-flag journeys |
| IB-D | Ordinary effective `SpaceMembership`; no synthetic role | Platform APIs remain metadata/admin; chat/history/source require membership | Before/pending/accepted/suspended/removed and second-space denials for platform user |
| IB-E | Test-purpose/expiry/run metadata for new principals; retained actor snapshots | Exact-ID inventory from `/admin/test-principals/`, ownership impact, then existing audited offboarding endpoints; never pattern/bulk delete or bypass last admin | Operator-only/no-frontend access, exact approved target evidence, blocker/audit/retention verification, expired-test health count |
| IB-F | Production build manifest artifact | No API change; route data is not fetched before route mount | Clean build budgets: authenticated entry/static-import/modulepreload aggregate <=250 KiB gzip with shared chunks counted once, each lazy chunk <=400 KiB gzip; per-route trace and lazy console/editor/chart proof |
| IB-G | Named execution profiles and machine-readable evidence fingerprint | Public safe `/health/ready/` plus platform-only `/admin/system/readiness/`; readiness supplies safe environment truth | Four-state per-gate report; backend-only/SQLite/provider-unavailable cases cannot misclaim pass/fail |
| IB-H | No schema change | No runtime path/product-name inference | Canonical remote/product scan and clean-clone test outside historical paths |
| IB-I | Ownership migrations, one-owner partial unique constraint, deferred owner trigger, shared lock/impact/outbox primitives | Ownership/transfer/offboarding contract remains prerequisite to create/delete | PostgreSQL dependency order and ownership/offboarding/create/delete concurrency before feature enablement |
| IB-J | Effective Turn fields and `thinking_snapshot_known` are durable and replayable | `meta`, status, history, replay expose requested/effective read-only snapshot plus known marker | Requested/effective mode, model ID, thinking, conditional budget, fallback and legacy-unknown UI across live/reconnect/history; request contains no model/budget |
| IB-DEL | Deletion request/detail, lifecycle/dependency versions, tombstone/locator, fixed retained-FK matrix, purge job/fenced lease/store checkpoints, purge guard trigger | Owner-only archive/impact/request/confirm/cancel/status; exact bodies/versions, 409 blockers, typed locator | GitHub-style confirmation, retention/cancel/after-purge status UI; PG race/trigger/registry/FK-retention/store-failure/checkpoint/non-cascade evidence suite |

Release sign-off requires a named owner and evidence link for every row, plus the
gates in section 17. A waived row requires a separately approved delta that
states user impact, rollback, expiry, and why no invariant is weakened; “not
implemented,” SQLite-only evidence, or a Markdown assertion cannot be waived as
equivalent acceptance.
