# KnowPilot SPEC Implementation Progress

> Updated: 2026-07-17
>
> Branch: `codex/knowpilot-optimization`
>
> Normative optimization specification: [2026-07-17 v2](../../docs/specs/2026-07-16-knowpilot-optimization-spec.md)
>
> Status: optimization implementation and v2 specification locally accepted; 筼筜 deployment acceptance pending

## Executive status

The historical roadmap through Phase 9 remains delivered as recorded in
`SPEC.MD`. The post-V11 optimization scope is no longer a proposed or “not
started” phase: stability, durable chat recovery, capability-scoped consoles,
governed fast/deep execution, design convergence, and missing user/admin
conversation workflows are implemented on this branch.

“Locally accepted” means source, additive migrations, isolated automated tests,
static checks, i18n validation, and production build satisfy the normative spec.
It does not claim live PostgreSQL migration timing, Redis multi-worker behavior,
provider performance/privacy, or authenticated browser/visual acceptance.

## Optimization issue coverage

| Scope | State | Implemented evidence | Deployment evidence still required |
|---|---|---|---|
| `KP-C01`–`KP-C04` selection/state races | Locally accepted | Active reselection no-op; state by session; abort/sequence guards; cross-tab selection isolation | Multi-tab browser journey |
| `KP-C05`–`KP-C07`, `KP-C11` disconnect/duplicate/concurrency/recovery | Locally accepted | Durable Turn, POST-once, explicit recovery, renewable lease, monotonic replay, partial preservation | Live Redis and worker-loss/disconnect exercise |
| `KP-C08`–`KP-C10` identity/pagination/timestamps | Locally accepted | Question-PK exclusion, cursor consumption/dedup/order, session touch | PostgreSQL query and migration observation |
| `KP-A01`–`KP-A03` authorization/admin separation | Locally accepted | Exact capabilities; list/detail/history/export/terminal-recovery/branch/regenerate downgrade denial; active guest Turn recovery; scoped consoles/endpoints; upward denial | Authenticated role and cross-scope UAT |
| `KP-A04` governed model path | Locally accepted | Profile/policy resolution, fast/deep mode, safe phases/metrics, reasoning rejection | Real provider binding and SLO/privacy evidence |
| `KP-U01` conversation closure | Locally accepted | History/search/paging, regenerate/version/branch/share/citation/source | Clipboard/native share and browser source journey |
| `KP-U02` workspace/governance closure | Locally accepted | Discovery/request/review and lifecycle/model-policy workflows | Full browser lifecycle/governance journey |
| `KP-D01`–`KP-D02` design/motion | Locally accepted | Typed warm-editorial tokens, primitives, restrained motion, reduced-motion contracts | Responsive live visual/accessibility pass |

## Functional surface status

| SPEC area | State | Notes |
|---|---|---|
| Architecture and multi-space isolation | Delivered | One deployment, organization/business-line/space scopes, single-space chat retrieval |
| Authentication and account governance | Delivered | Account security, MFA/session/preferences and scoped administration remain in force |
| Scenario templates and knowledge governance | Delivered | Versioned templates, isolated packs, ingestion/index/quality/audit workflows |
| RAG and conversation engine | Delivered plus optimization locally accepted | Durable Turn/SSE v2 compatibility, citations, fast/deep governed policy |
| RBAC and management consoles | Optimization locally accepted | Server capability authority separates platform, governance, and workspace consoles |
| User conversation workflows | Optimization locally accepted | History URL filters, paging, version/regenerate, branch, share, export, source access |
| Space lifecycle and access | Optimization locally accepted | Discovery/request/review/archive/restore/clone/transfer/owner transfer |
| Internationalization/design/accessibility | Optimization locally accepted | 82 locale files, unified token/primitive source, reduced-motion assertions |
| Resolved product decisions | Closed for current release | Authenticated join codes, versioned template overrides, single-space retrieval, project/space rule, bounded cited excerpts |

## Migration and compatibility state

Required additive order:

1. `chat.0013_chatturn`
2. `spaces.0008_organizationmembership_effectiveness`
3. `chat.0014_chatturn_metrics_and_model_lengths`
4. `chat.0015_message_versions_and_session_branches`
5. `chat.0016_conversation_share`

All staged flags default off. Durable Turn identity and duplicate suppression are
mandatory even when `CHAT_TURN_IDEMPOTENCY=false`; that flag is an observation
marker. SSE v1 and compatibility navigation remain for one measured release.
Rollback disables deep mode, capability navigation, SSE v2, and then the marker,
while preserving additive records and schema.

## Verification ledger

Fresh closure evidence from 2026-07-17:

| Gate | Result | Boundary |
|---|---|---|
| Focused idempotency-metric regression | 1 passed | Proves the boolean rollout marker survives the safe metric allowlist; integer impersonation rejected |
| Django complete suite | 365/365 passed | Isolated local settings; not live PostgreSQL/Redis/provider |
| Frontend complete suite | 266/266 passed in 45 files | jsdom/unit/integration; not a live browser |
| TypeScript/i18n/build | Passed; 82 source files; 4,027 modules transformed | Production compilation only; not live visual acceptance |
| Django/migrations/Ruff/diff/docs | Passed | System check, no model drift, changed-file lint, diff and normative-link consistency |

ESLint is not claimed because the installed dependency set does not contain its
executable. The existing large Ant Design/main chunks remain a post-acceptance
bundle-splitting opportunity.

## Single next stage

In an authorized 筼筜 deployment window: back up and rehearse the additive
PostgreSQL migrations with all flags off; deploy compatible code and smoke v1;
then enable the idempotency marker, SSE v2, paired backend/frontend capability
navigation, and paired backend/frontend deep mode in order. At each step capture
rollback evidence, scope denials, live telemetry, and browser/visual results.

The durable handoff and exact remaining checklist are in [`memory.md`](../../memory.md).
