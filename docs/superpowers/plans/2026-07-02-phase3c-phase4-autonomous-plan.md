# Phase 3C to Phase 4B Autonomous Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` and `superpowers:test-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete retrieval safety, scoped audit governance, and the Phase 4 operations/metrics MVP with a versioned audit after every major phase.

**Architecture:** Retrieval is fail-closed on space and active-document state. Audit records carry explicit organization, business-line, and space scope. Admin health and metrics use real bounded checks and scoped database aggregates, while document deletion becomes an auditable archive lifecycle.

**Tech Stack:** Django 5/DRF, Celery, Redis, PostgreSQL/pgvector with SQLite fallback, React 18, TypeScript, Ant Design, Vitest.

---

## Execution gates

- [ ] Preserve all pre-existing working-tree changes and stage only named phase files.
- [ ] Run a real backend baseline from the `backend` working directory and the frontend test/i18n/typecheck/build gates.
- [ ] Use red-green-refactor for every behavior change.
- [x] Generate the matching report under `audit_reports/v7.4` or `audit_reports/v7.5` before marking a phase complete.
- [ ] Create one local commit per passing phase; do not push.
- [ ] Stop at the current phase if its focused or regression gate fails.

## Phase 3C — Retrieval safety (V7.4)

- [ ] Add failing tests for missing/invalid space, cross-space isolation, active-only retrieval, rejected filter keys, UUID validation, SQLite/PostgreSQL parity, and SQL parameterization.
- [ ] Add a typed `RetrievalFilters` allowlist supporting only document and category IDs.
- [ ] Require `space_id` in the retriever and RAG pipeline and update every caller.
- [ ] Hard-code active-document enforcement in both database implementations.
- [ ] Run focused and full backend regression gates.
- [ ] Write `audit_reports/v7.4/Phase3C_Retrieval_Safety_Test_Audit_Report_V7.4.md`, update the SPEC progress, and commit `feat(rag): enforce safe space-scoped retrieval`.

## Phase 4A — Scoped audit governance (V7.5)

- [ ] Add failing tests for organization/business-line isolation, platform visibility, denied access, filters, pagination, immutable API behavior, and serialized role/scope/result fields.
- [ ] Add nullable immutable scope identifiers and a success/denied/failure result to audit records without guessing historical scope.
- [ ] Replace the legacy global HR audit gate with platform/org/business admin scope rules.
- [ ] Propagate scope/result through sensitive space, invite, document, role, admin-code, and template events.
- [ ] Add server-side filters and update the admin audit UI with visible errors.
- [ ] Run migration, focused, backend regression, frontend, i18n, typecheck, and build gates.
- [x] Write `audit_reports/v7.5/Phase4A_Audit_Governance_Test_Audit_Report_V7.5.md`, update progress, and commit `feat(audit): add scoped governance audit`.

## Phase 4B — Operations, metrics, and lifecycle MVP (V7.5)

- [ ] Add failing tests for real health states, dependency degradation, admin scope, metric calculations, archive behavior, hard-delete restrictions, and idempotent stale transitions.
- [ ] Add authenticated `/api/v1/admin/health/` and `/api/v1/admin/metrics/` endpoints.
- [ ] Use bounded database, Redis, Celery, and vector checks; report LLM configuration honestly without a paid probe.
- [ ] Return scoped usage, response, evidence, citation, ingestion, stale/expiry, and permission-denial metrics.
- [ ] Add stale/archived states, archive-by-default deletion, protected super-admin hard deletion, and an idempotent stale-document command.
- [ ] Replace inferred frontend health with the real endpoints and expose lifecycle states/actions.
- [ ] Run all backend/frontend/migration/system/build gates.
- [x] Write `audit_reports/v7.5/Phase4B_Operations_Metrics_Test_Audit_Report_V7.5.md`, update SPEC/progress/roadmap, and commit `feat(admin): add health metrics and document lifecycle`.

## Deferred roadmap

- Phase 4C/V7.5: failed Celery job visibility and retry, token/error metrics, and quality drill-down.
- Phase 5A/V8.0: user-owned feedback, flagged-answer review queue, reviewer status and resolution.
- Phase 5B/V8.1: knowledge-gap tickets and usage-driven knowledge analytics.
- Production hardening/V9.0: PostgreSQL/pgvector/Redis/Celery integration, load, recovery, retention, and release audit.
