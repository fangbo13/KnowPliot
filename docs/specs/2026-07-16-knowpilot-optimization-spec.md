# KnowPilot Optimization Specification Addendum

> Version: 2026-07-17 v2
>
> Status: Implementation complete and locally accepted; 筼筜 deployment acceptance pending
>
> Primary delivery plan: [KnowPilot Optimization Implementation Plan](../superpowers/plans/2026-07-16-knowpilot-optimization-implementation.md)
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

This branch does not start Docker or the deployed 筼筜 environment, migrate the
deployment server, delete the v1 stream protocol, or remove legacy authorization
fallbacks. It must not expose secrets, PII, provider reasoning, environment
credentials, prompts, or connection details in specifications, logs, tests, or
handoff memory.

## 2. Audited issue register

The disposition below reflects the 2026-07-17 implementation audit. “Locally
closed” requires source-level evidence and the gates in section 10. It does not
substitute for the live dependency and browser evidence required before 筼筜
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
  "content": "Question text",
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
| `status` | One of `accepted`, `retrieving`, `reasoning`, `answering`, `saving`, `completed`, `failed`, or `cancelled`. |
| `answer_mode` | Resolved `fast` or `deep` policy. |
| `model_id` | Resolved governed model identifier, not a browser-supplied authority. |
| `attempt_count` | Starts at one; increments only when a retryable Turn is re-attempted. |
| `last_event_seq` | Highest persisted/emitted SSE v2 sequence for recovery. |
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
- An owner may recover an active Turn with effective `chat.ask`, whether that
  capability comes from direct membership, public-demo guest access, or a
  platform/governance scope. Once the Turn is completed, failed, or cancelled,
  status/replay becomes history access and requires `chat.history`.

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

The initial timeout budget is fixed at 20 seconds to establish the connection,
45 seconds without an event, 180 seconds total, and 5 seconds for each Turn
status/replay recovery request. A timeout aborts only the owning session's local
request and then queries the existing Turn; it never repeats the send POST.

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

### 6.1 Exact capability vocabulary

The following grants are additive inside the listed scope. Platform,
organization, and business-line grants do not remove the endpoint's resource-
scope check.

| Role/scope | Server-issued capabilities |
|---|---|
| Platform admin | `platform.access`, `platform.audit.read`, `platform.metrics.read`, `platform.models.manage`, `platform.organizations.manage`, `platform.roles.manage`, `platform.users.manage` |
| Organization admin | `governance.access`, `governance.audit.read`, `governance.business_lines.manage`, `governance.metrics.read`, `governance.models.bind`, `governance.organization.settings.manage`, `governance.spaces.manage`, `governance.templates.manage`, `governance.users.manage` |
| Business-line admin | `governance.access`, `governance.audit.read`, `governance.metrics.read`, `governance.spaces.manage`, `governance.templates.manage`, `governance.users.manage` |
| Space owner | `chat.ask`, `chat.history`, `chat.share`, `chat.export`, `audit.read`, `knowledge.read`, `knowledge.download`, `knowledge.index`, `knowledge.manage`, `quality.read`, `quality.review`, `workspace.manage`, `workspace.access_requests.manage`, `workspace.invites.manage`, `workspace.lifecycle.manage`, `workspace.members.manage`, `workspace.settings.manage` |
| Knowledge admin | `chat.ask`, `chat.history`, `knowledge.read`, `knowledge.download`, `knowledge.index`, `knowledge.manage`, `quality.read`, `quality.review`, `workspace.manage` |
| Reviewer | `chat.ask`, `chat.history`, `audit.read`, `quality.read`, `quality.review`, `workspace.manage` |
| Member | `chat.ask`, `chat.history`, `chat.share`, `chat.export` |
| Guest | `chat.ask` only |

`chat.deep` is resolved dynamically for a selected non-guest space only when
deep mode is enabled and the effective governance policy makes it available.
Business-line admins intentionally lack organization settings, business-line
management, and model-binding grants. Workspace roles intentionally lack every
`governance.*` and `platform.*` grant.

`chat.history` is the public capability returned to the browser. The space
permission layer names the same check `CHAT_VIEW_HISTORY` with stored code
`chat.view_history`; these are two representations of one policy, not separate
grants. API documentation uses the public capability name and implementation
tests cover the internal mapping.

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
- Local acceptance uses the isolated SQLite test settings. PostgreSQL migration
  timing/locking, Redis multi-worker coordination, provider behavior, and live
  browser journeys remain deployment evidence and may not be inferred from
  local mocks or unit tests.
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
  selection. Disabled flags preserve the fast/v1 experience. Durable Turn
  identity and duplicate suppression remain active regardless of the
  `CHAT_TURN_IDEMPOTENCY` marker.
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
`CHAT_STREAM_V2`, then the `CHAT_TURN_IDEMPOTENCY` observation marker. Rollback
switches traffic back to fast mode, compatibility navigation, and v1 streaming
without weakening duplicate suppression or deleting `ChatTurn` records, replay
evidence, additive columns, or migrations. Data-destructive rollback is
prohibited. Any cleanup migration is a separately approved release.

## 12. API and error contract

All endpoints below are under `/api/v1`, require authentication, and re-check
the current resource scope unless explicitly stated otherwise. A hidden button
or route is never sufficient authorization.

### 12.1 Chat, history, recovery, and conversation operations

| Method and path | Authority | Success contract | Stable failures |
|---|---|---|---|
| `GET|POST /chat/sessions/` | Accessible space plus `chat.history` for list and `chat.ask` for create | 20-session cursor page ordered by pinned, update time, then ID; create binds current/default space | `400` invalid filter; `403` denied; non-disclosing `404` for inaccessible scope |
| `GET|PATCH|DELETE /chat/sessions/{id}/` | Session owner, current space access, and `chat.history` | Read, rename/pin, or soft-delete the owned session | `403` denied; `404` absent or non-owned |
| `GET /chat/sessions/{id}/messages/` | Session owner and `chat.history` | Newest 40-message cursor page; current assistant versions by default; chronological rendering after client normalization | `403` denied; `404` absent/non-owned |
| `POST /chat/sessions/{id}/send/` | Session access plus `chat.ask` | One durable Turn/question; v1 or v2 SSE selected by request and flag | `400` validation; `409` conflict/busy/terminal; `503` coordination or event store unavailable |
| `GET /chat/turns/{turn_id}/` | Original user and current space access; active Turn requires `chat.ask`, terminal Turn requires `chat.history` | Safe durable status and completed answer when available | non-disclosing `404`; `403` current membership/capability denial |
| `GET /chat/turns/{turn_id}/events/?after={seq}` | Same active/terminal rule as Turn status | Replays only events with a later sequence; `Last-Event-ID` is an alternative cursor | `503 event_store_unavailable`; scoped denial as above |
| `POST /chat/messages/{id}/regenerate/` | Owned visible message plus `chat.history` and `chat.ask` | Reuses the persisted question and creates a new assistant version without a second user message | Same Turn/idempotency errors as send |
| `POST /chat/messages/{id}/branch/` | Owned visible message plus `chat.history` and `chat.ask` | Idempotently creates a new session and copies the visible path through the selected message | `400` invalid payload; scoped `403/404` |
| `GET|POST /chat/sessions/{id}/shares/` | Owner; `chat.share` required to create | Lists/creates organization-scoped, read-only, seven-day shares | `403` denied; `404` inaccessible session |
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

### 12.2 Space and administration workflows

| Method and path | Authority | Product contract |
|---|---|---|
| `GET /spaces/discoverable/` | Authenticated user | Lists requestable, current-scope spaces with explicit empty/error states |
| `POST /spaces/{id}/access-requests/` | Authenticated eligible user | Submits one request with a bounded reason and visible pending state |
| `GET|POST /admin/spaces/{id}/access-requests/...` | `workspace.access_requests.manage` or qualifying scoped governance grant | List, approve, or reject; rejection requires reason, reviewer/time, audit event, and safe notification |
| `POST /spaces/{id}/archive|restore|clone|transfer|transfer-owner/` | Matching lifecycle/owner or scoped governance authority | Confirmation-gated lifecycle mutation with audit evidence and refreshed UI state |
| `/spaces/{id}/members/` and `/spaces/{id}/invites/` | Corresponding workspace capability | Scoped member/invite management; no upward grant |
| `/admin/users/` and `/admin/users/{id}/assignments/` | Platform or scoped `governance.users.manage` | Returns/mutates only users inside the caller's effective scope |
| `/admin/model-profiles/` | Platform model authority to mutate; scoped governance may list enabled profiles | Platform registry remains separate from organization bindings |
| `/admin/governance/policies/` | Platform authority or organization `governance.models.bind` | Creates immutable, organization-owned policy revisions; cross-org binding denied |
| `GET /rbac/me/capabilities/?space_id={id}` | Authenticated user | Returns scopes, exact flat capabilities, and deterministic default console |

Space access-code join is authenticated in this release. Pre-authentication
demo-code entry is deferred and, if later approved, must be limited to explicit
non-confidential demo spaces rather than weakening production join rules.

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
5. `chat.0016_conversation_share` — revocable tenant-scoped share records.

Migration `0015` adds `version_group_id` as nullable, assigns a distinct UUID to
each existing message with iterator/bulk-update batches of 1,000, makes it
non-null, and only then adds uniqueness. Historical rows must never share one
schema-default UUID. The final database invariants are one
`(version_group_id, version_number)`, one current message per version group, one
branch per `(user, branch_request_id)`, one Turn per
`(user, client_request_id)`, and one idempotent share per
`(owner, client_request_id)` when the request ID is present.

Migrations are applied with all rollout flags off after backup and rehearsal on
a PostgreSQL copy. Measure duration, table locking, backfill rate, index creation,
and disk growth. Application rollback deploys compatible code and disables flags
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

## 15. Performance, observability, privacy, and design acceptance

### 15.1 Performance and reliability

- Product targets are retrieval p95 at or below 1 second for common space sizes
  and first answer token at or below 3 seconds after retrieval under normal
  provider conditions. These are deployment SLO candidates, not claims from the
  local unit suite; 筼筜 must establish baselines segmented by answer mode/model.
- `meta` is emitted before retrieval. Model, embedding, and HTTP clients are
  reused, and the chat path does not initialize ingestion-only parser/chunker
  dependencies.
- The 20/45/180-second client budgets, 180-second renewable session lease,
  30-second lease renewal, 15-minute replay retention, and 5-second recovery
  request bound are release constants. Changes require contract-test updates.
- The existing large Ant Design/main chunks are a measured post-rollout
  optimization: route-level lazy loading and bundle splitting may proceed only
  after behavior/role journeys remain unchanged.

### 15.2 Safe telemetry and privacy

`ChatTurn.metrics` accepts only `ttfe_ms`, `retrieval_ms`, `reasoning_ms`,
`first_answer_token_ms`, `total_ms`, `disconnect_count`, `recovery_count`, the
bounded `idempotency_disposition`, and boolean
`idempotency_rollout_enabled`. Unknown keys, booleans passed as numbers, and
unbounded labels are rejected. Recovery metrics do not touch `updated_at`, which
is reserved for worker-liveness convergence.

Logs, metrics, audit events, SSE, status responses, specifications, tests, and
handoff memory must not contain raw prompts, provider reasoning, traceback text,
credentials, connection strings, storage paths, or PII. `reasoning_ms` is a
numeric duration only. Citations use plain text stripped of markup and are
bounded to 280 characters.

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

## 16. Original-request traceability

| User request | Specification coverage | Implemented evidence | Remaining release evidence |
|---|---|---|---|
| 1. Repeated clicks disconnect; content disappears | Sections 3–5, 10.1, 12.1, 14.1 | Session-keyed store, reselection no-op, abort/sequence guards, durable Turn, lease/replay, cursor consumption | Live multi-tab disconnect and Redis replay |
| 2. Project admin and super admin not separated | Sections 6, 10.2, 12.2, 14.2 | Exact capability service, platform/governance/workspace consoles, scoped APIs, upward-denial tests | Authenticated role journey in 筼筜 |
| 3. Faster response and streaming thinking model | Sections 5, 7, 10.3, 15.1–15.2 | Early `meta`, client reuse, fast/deep policy, safe phases, timing metrics, no raw reasoning | Provider streaming and p95/SLO baseline |
| 4. Inconsistent visual tone/motion/whitespace | Sections 8, 10.4, 15.3 | Typed tokens, primitives, warm editorial palette, restrained motion, reduced-motion tests | Live responsive visual/accessibility pass |
| 5. Missing user/admin/conversation functions | Sections 10.4, 12, 14 | History/search/paging, regenerate/version/branch/share/citation, discovery/access/lifecycle/governance workflows | Clipboard/native share and full browser UAT |
| 6. Find bugs and provide repair route | Section 2 plus sections 10, 17, and 18 | Audited issue register, contract tests, migrations, current progress report and `memory.md` | Deployment rehearsal and production monitoring |

## 17. Acceptance evidence and release gates

Local acceptance and production acceptance are intentionally separate:

| Gate | Required evidence | Current disposition |
|---|---|---|
| Source/data contract | Model, serializer, state-transition, capability, endpoint, and migration review matches this spec | Locally complete |
| Backend | Focused regressions plus complete Django suite, system check, migration drift check, and changed-file Ruff | Passed: 365/365 plus all static/migration gates |
| Frontend | Complete Vitest suite, TypeScript typecheck, i18n validation, and production build | Passed: 266/266 in 45 files, 82-file i18n, and 4,027-module build |
| Repository/docs | `git diff --check`, normative links resolve, no unresolved placeholder/contradiction in current docs | Passed in the v2 closure review |
| PostgreSQL | Backup/restore rehearsal, migrations through `chat.0016`, duration/lock/data-constraint evidence | Pending authorized 筼筜 window |
| Redis/multi-worker | Lease exclusivity/renewal/release, replay sequence/retention, disconnect and worker-loss recovery | Pending authorized 筼筜 window |
| Provider | Fast/deep binding, safe streaming, timeout/failure behavior, no raw reasoning, performance baselines | Pending authorized 筼筜 window |
| Browser/UAT | User, guest, workspace roles, scoped governance roles, platform role, share/source, responsive/reduced-motion journeys | Pending authorized 筼筜 window |

No service or 筼筜 environment is started by this specification closure. A gate
is not marked production-pass from mocked dependencies. ESLint is not a required
local claim until its executable is present in the installed dependency set.

## 18. Resolved decisions and optimization route

The former product questions are resolved for this release:

1. Production access codes require authentication; pre-auth demo entry is
   deferred to an explicit non-confidential-demo design.
2. Templates are global or scoped assets with versioned overrides; business
   lines do not silently fork untracked copies.
3. Chat retrieval remains single-space. Cross-space retrieval is out of scope
   until an explicit permission and citation-isolation design is approved.
4. High-confidentiality or long-running projects are spaces; small bounded topics
   are categories within a space.
5. Answers prefer summaries with citations and bounded excerpts; the current
   citation excerpt maximum is 280 characters.

The remaining route is deployment work, not another implementation phase:

1. Rehearse backup, restore, and additive PostgreSQL migrations with flags off.
2. Deploy the compatible backend/frontend with all staged flags off; smoke v1.
3. Enable the idempotency observation marker and monitor outcomes while core
   duplicate suppression remains mandatory.
4. Enable SSE v2 and prove Redis/multi-worker/disconnect recovery.
5. Enable backend/frontend capability navigation together and execute every role
   journey, including cross-scope denials.
6. Bind approved provider profiles, then enable backend/frontend deep mode and
   establish fast/deep performance and privacy evidence.
7. Complete responsive visual/reduced-motion UAT, then observe one compatibility
   release before separately approving v1/legacy-fallback removal.

After production acceptance, prioritize route-level lazy loading/bundle splitting,
observability dashboards/alerts for the metrics in section 15, and compatibility
cleanup. These follow-ups may not weaken idempotency, scope isolation, safe-phase
privacy, or additive-data retention.
