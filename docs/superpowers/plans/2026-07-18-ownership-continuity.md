# Ownership Continuity and Account Offboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every active or archived space retain one effective canonical owner while providing atomic, auditable ownership transfer and account offboarding.

**Architecture:** `KnowledgeSpace.owner` becomes the authority and its owner `SpaceMembership` becomes a compatible mirror. Focused domain services own row locking, state transitions, idempotency and audit emission; APIs and old mutation paths delegate to those services. Offboarding first derives a deterministic impact snapshot, then rechecks and commits all succession and revocation changes in one transaction.

**Tech Stack:** Django/DRF, PostgreSQL constraints and row locking, React/TypeScript, Vitest, Django `TestCase`/`TransactionTestCase`.

## Global Constraints

- Do not use `created_by` or `SpaceMembership.role=owner` as the ownership authority.
- Use `transaction.atomic`, stable lock order, and `select_for_update(of=("self",))` whenever locking a queryset with nullable joins.
- A voluntary transfer is pending for 72 hours and changes no permissions before acceptance.
- Only server-resolved capabilities grant force transfer or global offboarding; frontend controls are never authority.
- Same idempotency key plus actor and normalized request is replay-safe; a changed request returns `409 idempotency_conflict`.
- Offboarding must recompute `impact_version`; an unresolved owner or final admin returns `409` without partial writes.
- Never write secrets, raw codes, tokens, provider data, or unbounded personnel notes into audits, tests, or docs.
- User hard deletion is disabled in Phase 1; reactivation does not restore memberships, roles, sessions, shares, or credentials.

---

### Task 1: Persistence, predicates, and migration audit

**Files:**
- Modify: `backend/apps/spaces/models.py`, `backend/apps/users/models.py`
- Create: `backend/apps/spaces/migrations/0009_ownership_continuity_stage_a.py`, `backend/apps/spaces/management/commands/audit_ownership_continuity.py`, `backend/apps/spaces/ownership.py`, `backend/apps/spaces/test_ownership_continuity_models.py`

**Produces:** `effective_user`, `effective_membership`, `canonical_owner`, `effective_platform_admin`, `effective_org_admin`, `effective_business_admin`; nullable owner/metadata and an `OwnershipTransfer` record with Stage-A safe constraints.

- [ ] Write failing tests that a newly-created space has an owner FK and exactly one effective owner mirror, and that inactive, expired, or revoked users do not count as effective owners/admins.
- [ ] Run `backend\\venv\\Scripts\\python.exe backend\\manage.py test apps.spaces.test_ownership_continuity_models --settings=config.settings.local_test` and observe the missing-owner failures.
- [ ] Add nullable `owner`, `ownership_version`, `OwnershipTransfer`, user deactivation metadata, model constraints safe for Stage A, and creation-path dual writes.
- [ ] Add the audit command: only backfill a space with exactly one effective legacy owner; report zero/multiple owners and missing effective admins as safe JSON/CSV without sensitive values.
- [ ] Re-run the focused model/command tests and `makemigrations --check`.

### Task 2: Ownership transfer domain service

**Files:**
- Create: `backend/apps/spaces/ownership_services.py`, `backend/apps/spaces/test_ownership_transfer_service.py`
- Modify: `backend/apps/audit/models.py`, `backend/apps/spaces/models.py`

**Produces:** `OwnershipTransferService.request`, `.accept`, `.decline`, `.cancel`, `.force`, and `.expire_pending`.

- [ ] Write failing tests for pending-no-change, acceptance atomic switch/version increment, decline/cancel/expiry/invalidation no-change, invalid targets, replay, and two competing accepts.
- [ ] Run the focused tests and observe failures because the service does not exist.
- [ ] Implement the service with user → space → membership → transfer locking, expected-version checks, a unique request key, on-commit notification dispatch, and safe audit action payloads.
- [ ] Add PostgreSQL `TransactionTestCase` coverage for concurrent acceptance and ensure every locking query avoids nullable-side `FOR UPDATE` joins.
- [ ] Run focused service tests using `config.settings.test` in PostgreSQL and local focused tests.

### Task 3: Capability-scoped ownership APIs and legacy delegation

**Files:**
- Modify: `backend/apps/rbac/capabilities.py`, `backend/apps/spaces/urls.py`, `backend/apps/spaces/views.py`, `backend/apps/spaces/serializers.py`
- Create: `backend/apps/spaces/ownership_views.py`, `backend/apps/spaces/test_ownership_api.py`

**Produces:** ownership detail, candidates, voluntary/force/create/accept/decline/cancel endpoints and a compatible legacy `transfer-owner` adapter.

- [ ] Write API failures for invisible cross-scope spaces, candidate eligibility, target-only acceptance, scoped force authority, and legacy endpoint delegation.
- [ ] Run the new API tests and observe the expected 404/403/endpoint failures.
- [ ] Resolve the seven exact new capabilities through the existing capability service and delegate endpoint mutations to `OwnershipTransferService`.
- [ ] Make the legacy endpoint return `202` for voluntary requests, `200` for permitted force transfers, and deprecation/successor headers.
- [ ] Run focused API tests and the capability regression suite.

### Task 4: Offboarding impact and atomic orchestration

**Files:**
- Create: `backend/apps/rbac/offboarding.py`, `backend/apps/rbac/test_offboarding.py`
- Modify: `backend/apps/rbac/views.py`, `backend/apps/rbac/urls.py`, `backend/apps/users/security.py`, `backend/apps/chat/models.py`

**Produces:** deterministic `OffboardingImpactService.inspect` and atomic `OffboardingService.offboard` used by both new and old deactivate APIs.

- [ ] Write failing tests for owner blockers, stale impacts, final platform/org/business admin protection, complete mapped offboarding, credential/share/session revocation, task requeue, failure rollback, and reactivation non-restoration.
- [ ] Run the focused tests and observe the missing service/API failures.
- [ ] Lock subject then scopes/spaces in UUID order; recompute impact, complete valid succession/forced transfer, revoke scoped grants/sessions/shares/unused credentials, requeue work, set safe deactivation metadata, and audit after commit.
- [ ] Route old deactivate through the service and return `409 offboarding_required` plus the impact URL whenever mappings are missing.
- [ ] Run focused PostgreSQL and local tests, including a fault-injection rollback assertion.

### Task 5: Bypass protection and retained data

**Files:**
- Modify: `backend/apps/spaces/views.py`, `backend/apps/spaces/admin_views.py`, `backend/apps/rbac/views.py`, `backend/apps/users/admin.py`, relevant user foreign keys/migrations
- Create: `backend/apps/spaces/test_ownership_bypass_protection.py`, `backend/apps/users/test_user_retention.py`

- [ ] Write failures covering canonical-owner member downgrade/removal, final scope-admin removal/revoke, Django-admin User delete denial, and protected chat/audit/compliance references.
- [ ] Run the tests to prove the former direct routes bypass the service invariant.
- [ ] Delegate membership and assignment mutations to shared predicates/services; block User delete permission and move retention-critical user references away from cascade behavior where required.
- [ ] Add Stage-C migration only after the audit reports no unremediated owner anomalies: owner non-null/PROTECT and one active owner-mirror conditional constraint.
- [ ] Run model/migration checks and focused protection tests on PostgreSQL.

### Task 6: Frontend lifecycle and offboarding workflows; documentation and release evidence

**Files:**
- Modify: `frontend/src/pages/console/WorkspaceLifecyclePage.tsx`, platform user management components, `frontend/src/api/spaces.ts`, `frontend/src/api/admin.ts`, locale files
- Create: ownership/offboarding API and component tests
- Modify: `docs/superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md`, `docs/specs/2026-07-16-knowpilot-optimization-spec.md`, `audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md`, `memory.md`

- [ ] Write failing UI/API tests for searchable eligible candidates, absent UUID input, distinct voluntary/force/offboard confirmations, disabled unresolved impact, replay-safe submit, preserved selections on impact conflict, and capability-hidden global offboarding.
- [ ] Run the focused Vitest tests and observe the missing workflow failures.
- [ ] Implement ownership card, candidate search/paging, transfer responses, force reason/confirmation, impact drawer and successor mapping using server capabilities and idempotency keys.
- [ ] Update translations/accessibility/reduced-motion/mobile states, then run focused tests, full frontend tests, typecheck, i18n validation, and production build.
- [ ] Record actual local/PG evidence and clearly mark deployment/UAT gates pending; run Django check, migration drift, Ruff on changed Python files, Markdown-link/placeholder scan, and `git diff --check`.
