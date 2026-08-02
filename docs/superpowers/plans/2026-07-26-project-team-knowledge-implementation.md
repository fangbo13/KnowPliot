# Project Team Knowledge Template and Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the project-team knowledge architecture defined in `docs/specs/project_team_knowledge_template_index_spec.md` on top of the existing workspace, document-versioning, template, and RAG platform.

**Architecture:** Add a focused `project_knowledge` Django domain that owns project periods, responsibility units, stable knowledge blocks and immutable versions, index releases, roll-forward state, and retrieval context. Keep existing `knowledge.Document` as the source-file layer and existing spaces as the authorization boundary; expose project-native APIs and a project workbench in React.

**Tech Stack:** Django 5 / DRF, PostgreSQL or SQLite test fallback, Celery-compatible index events, React 18, TypeScript, Ant Design, Vitest.

## Global Constraints

- Every project object is scoped by workspace, project, period/fiscal year, entity, and knowledge status.
- Approved versions are immutable; saving creates a new version.
- Draft and approved retrieval modes are separated and cannot bypass hard filters.
- Responsibility and approval are object-level; the last substantive editor cannot approve their own change unless an explicit exception exists.
- Watermark and attribution data are metadata and audit records, never embedding text.
- Roll-forward inherits approved blocks and marks them `unreviewed` until confirm, update, fork, replace, or mark not applicable.
- Index changes are incremental and stable block IDs survive content edits.
- Audit is the first complete vertical slice; Tax, Deals, and Consulting share the same manifest contract.

---

### Task 1: Project knowledge domain foundation

**Files:**
- Create: `backend/apps/project_knowledge/models.py`
- Create: `backend/apps/project_knowledge/migrations/0001_initial.py`
- Modify: `backend/config/settings/base.py`
- Test: `backend/apps/project_knowledge/test_models.py`

**Interfaces:**
- Produces `Project`, `ProjectPeriod`, `ProjectEntity`, `ResponsibilityUnit`, `KnowledgeBlock`, `KnowledgeVersion`, `IndexRelease`, and `IndexDocument`.
- Stable IDs and database constraints enforce project/FY/entity isolation and one current version pointer per block.

- [ ] Write model tests for required dimensions, uniqueness, immutable approved versions, and stable block keys.
- [ ] Run the focused model tests and confirm they fail because the domain does not exist.
- [ ] Add the models, constraints, app registration, and migration.
- [ ] Run focused tests and migration checks.

### Task 2: Business-line manifests and audit project initialization

**Files:**
- Create: `backend/apps/project_knowledge/manifests.py`
- Create: `backend/apps/project_knowledge/services.py`
- Test: `backend/apps/project_knowledge/test_project_creation.py`

**Interfaces:**
- `get_manifest(business_line: str) -> dict`
- `create_project(*, actor, space, payload) -> Project`
- `initialize_audit_accounts(*, project, period, accounts, assignments) -> list[ResponsibilityUnit]`

- [ ] Test manifests for audit, tax, deals, and consulting against the cross-business-line contract.
- [ ] Test six-step audit initialization creates the pinned template version, period, entity scope, account units, owner/reviewer assignments, starter Markdown blocks, empty index release, and health baseline atomically.
- [ ] Implement only the manifest resolver and transactional initialization needed by those tests.
- [ ] Verify duplicate initialization is rejected without partial records.

### Task 3: Project APIs, assignment, workflow, and block versions

**Files:**
- Create: `backend/apps/project_knowledge/serializers.py`
- Create: `backend/apps/project_knowledge/views.py`
- Create: `backend/apps/project_knowledge/urls.py`
- Modify: `backend/config/urls.py`
- Test: `backend/apps/project_knowledge/test_api.py`

**Interfaces:**
- `POST /api/v1/projects/audit/`
- `POST /api/v1/projects/{projectId}/periods/{fy}/accounts:initialize/`
- `PATCH /api/v1/project-accounts/{accountId}/assignment/`
- `POST /api/v1/knowledge-blocks/{blockId}/versions/{versionId}:submit/`
- `POST /api/v1/knowledge-blocks/{blockId}/versions/{versionId}:approve/`
- `GET /api/v1/projects/{projectId}/periods/{fy}/accounts/{accountId}/health/`

- [ ] Test workspace isolation and role/owner/reviewer ABAC for every mutation.
- [ ] Test draft → in-review → approved transitions, self-approval rejection, approval prerequisites, and immutable version lineage.
- [ ] Implement serializers and endpoints with transactions and explicit 400/403/409 responses.
- [ ] Verify tests plus OpenAPI-compatible response shapes.

### Task 4: Incremental index releases and governed retrieval

**Files:**
- Create: `backend/apps/project_knowledge/indexing.py`
- Create: `backend/apps/project_knowledge/retrieval.py`
- Modify: `backend/apps/rag/retriever.py`
- Test: `backend/apps/project_knowledge/test_indexing.py`
- Test: `backend/apps/project_knowledge/test_retrieval.py`

**Interfaces:**
- `publish_version(version) -> IndexRelease`
- `retrieve_project_evidence(context, question, actor) -> EvidencePackage`

- [ ] Test changed-block-only indexing, tombstones, shadow validation, atomic active release switching, and rollback retention.
- [ ] Test mandatory project/FY/entity/account/status/ACL filters, approved vs working separation, prior-year opt-in, conflicts, and evidence-gate refusal.
- [ ] Implement stable chunk IDs, release documents, validation gates, and hybrid-ranking adapter.
- [ ] Verify stale, superseded, unauthorized, and wrong-FY content cannot be recalled.

### Task 5: Roll-forward, freeze, timeline, graph, and health

**Files:**
- Modify: `backend/apps/project_knowledge/services.py`
- Modify: `backend/apps/project_knowledge/views.py`
- Test: `backend/apps/project_knowledge/test_rollforward.py`
- Test: `backend/apps/project_knowledge/test_views.py`

**Interfaces:**
- `POST /api/v1/projects/{projectId}/periods:roll-forward/`
- Project dashboard response containing matrix, alerts, timeline, graph, and health summaries.

- [ ] Test inheritance from approved versions without copying the prior-year tree.
- [ ] Test confirm, update/fork, not-applicable, replacement, freeze, and amendment behavior.
- [ ] Implement dashboard projections from real relations and review/index state.
- [ ] Verify health scores do not use document count as the primary signal.

### Task 6: Project workbench frontend

**Files:**
- Create: `frontend/src/api/projectKnowledge.ts`
- Create: `frontend/src/pages/ProjectKnowledgePage.tsx`
- Create: `frontend/src/pages/ProjectKnowledgePage.css`
- Create: `frontend/src/pages/ProjectKnowledgePage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/layout/ScopedConsoleLayout.tsx`

**Interfaces:**
- Route: `/workspace/:spaceId/manage/projects/:projectId`
- Displays locked context, responsibility queue, account matrix, alerts, Markdown block editor, review actions, timeline, graph, and health.

- [ ] Test locked context and approved/working mode visibility.
- [ ] Test account ownership controls and forbidden edit/review actions are absent.
- [ ] Implement project dashboard and account workspace using existing Markdown and diff components.
- [ ] Run frontend unit tests, typecheck, and production build.

### Task 7: AI response contract and full acceptance audit

**Files:**
- Modify: `backend/apps/chat/serializers.py`
- Modify: `backend/apps/chat/services.py`
- Modify: `frontend/src/components/chat/MessageBubble.tsx`
- Test: relevant backend chat and frontend citation tests
- Create: `docs/specs/project_team_knowledge_acceptance_matrix.md`

**Interfaces:**
- Every project answer exposes scope, evidence count, last approval time, working-mode warning, and openable citation cards.

- [ ] Test evidence refusal, conflict disclosure, structured numeric-source priority, and historical-mode separation.
- [ ] Implement project retrieval routing and citation metadata without weakening generic chat behavior.
- [ ] Map all MVP items and §35 acceptance criteria to tests or runtime evidence.
- [ ] Run backend project/chat suites, frontend suite, typecheck, build, and migration checks; record results in the acceptance matrix.

