# KnowPilot SPEC

> Version: V6.1
> Source: `KnowPilot.md`, `README.md`, existing V4.x audit/planning reports
> Purpose: define the modular product architecture for KnowPilot as a multi-business-line knowledge Agent platform.

## 1. Architecture Decision

### 1.1 Recommendation

KnowPilot should use **one integrated website + multi-space modular management**, not separate deployments per business line.

The recommended model is:

```text
One KnowPilot platform
  -> Organization
    -> Business Line
      -> Knowledge Space
        -> Scenario Module
          -> Documents / prompts / permissions / chat sessions
```

Users enter the same website. After login, they either:

1. choose an authorized business line / knowledge space from a workspace switcher;
2. enter a short invite/access code to join or open a specific business space;
3. land directly in a default space based on SSO profile, role, department, or project assignment.

The access code should be treated as a **space entry / invite / demo activation mechanism**, not as the main long-term security boundary. Production access still depends on SSO/JWT/RBAC and object-level permissions.

### 1.2 Why Not Deploy By Business Line

Separate deployments are only suitable when a business line has hard isolation requirements, such as legal entity isolation, client-specific deployment, separate network boundary, or different compliance regime.

For KnowPilot's stated product goal, separate deployments weaken the main value proposition:

- higher maintenance cost for repeated backend, frontend, database, vector index, Celery, Redis, monitoring, and release pipelines;
- fragmented UX, making cross-business-line switching difficult;
- duplicated RAG infrastructure and duplicated admin logic;
- harder global audit, permission governance, and knowledge quality control;
- lower reusability, which conflicts with "one deployment, unlimited replication".

### 1.3 Target Pattern

Use a **multi-tenant, multi-space architecture**:

- one shared application runtime;
- one shared authentication and admin center;
- logical isolation by `organization_id`, `business_line_id`, and `space_id`;
- optional physical isolation only for high-risk spaces;
- reusable scenario templates for onboarding, audit methodology, standards Q&A, project AI, risk identification, working-paper drafting, independence checks, and audit opinion decision support.

## 2. Product Scope

### 2.1 Product Positioning

KnowPilot is a RAG-driven knowledge application Agent. It converts organization knowledge into searchable, conversational, traceable, permission-controlled knowledge spaces.

It supports professional service teams that need to repeatedly query:

- standards and regulations;
- methodology documents;
- onboarding and internal process guides;
- project experience and historical judgment logic;
- risk cases and industry characteristics;
- working-paper templates and examples;
- independence and compliance rules.

### 2.2 Core User Groups

| User group | Primary need |
| --- | --- |
| New joiner | Quickly ask operational and methodology questions without asking colleagues repeatedly |
| Staff / senior staff | Retrieve procedures, templates, examples, and source-backed answers |
| Manager | Preserve project logic, review answers, manage team knowledge |
| Partner / director | Switch across business spaces, inspect key insights and risks |
| Knowledge admin | Upload, classify, re-index, and retire knowledge |
| System admin | Manage users, permissions, audit logs, model settings, and system health |
| Compliance reviewer | Inspect access, source usage, and sensitive operations |

## 3. Information Architecture

### 3.1 Top-Level Navigation

| Area | Purpose |
| --- | --- |
| Chat | Ask questions inside the current knowledge space |
| Spaces | Select, join, create, or manage business spaces |
| Knowledge Base | Upload documents, manage metadata, re-index content |
| Templates | Create spaces from scenario templates |
| History | Search user's chat sessions and cited answers |
| Admin | Users, roles, permissions, audit, model, monitoring |
| Profile | Language, theme, default space, account metadata |

### 3.2 Space Hierarchy

```text
Organization
  - EY internal demo / client tenant / department tenant

Business Line
  - Audit
  - Tax
  - Consulting
  - HR / Talent
  - Risk / Compliance

Knowledge Space
  - Audit Methodology
  - IFRS / CAS / HKFRS Standards
  - IPO Project A
  - Manufacturing Risk Cases
  - New Joiner Onboarding

Scenario Module
  - Q&A
  - Cross-standard comparison
  - Risk identification
  - Working-paper guide
  - Compliance check
  - Decision support
```

### 3.3 Space Entry Modes

| Entry mode | Usage | Security note |
| --- | --- | --- |
| SSO/default routing | Enterprise production | Recommended default |
| Workspace switcher | Users with multiple spaces | Uses RBAC/object permissions |
| Invite/access code | Pilot, demo, controlled joining | Code only grants a pending membership or opens an already authorized space |
| Admin assignment | Formal team onboarding | Admin grants role and space access |
| Deep link | Share question/session/source | Requires permission re-check on open |

## 4. Functional Modules

### M1. Authentication And Identity

Purpose: authenticate users and attach organization/business metadata to the session.

Functions:

- email/password login for local demo and development;
- SSO-ready abstraction for enterprise use;
- JWT access and refresh token flow;
- logout and token revocation;
- `/auth/me/` returns user profile, roles, permissions, and allowed spaces;
- default organization, business line, and knowledge space resolution;
- language/theme/default space preferences.

Acceptance criteria:

- unauthenticated users cannot access app pages or APIs;
- token refresh does not force unnecessary logout;
- frontend never treats display-only user metadata as authorization truth;
- every API verifies permissions server-side.

### M2. Organization / Business Line / Space Management

Purpose: support one platform carrying multiple business lines and many isolated knowledge spaces.

Functions:

- create and edit organizations;
- create and edit business lines;
- create, archive, clone, and transfer knowledge spaces;
- assign space owner, knowledge admin, reviewer, and member roles;
- set space visibility: private, business-line internal, organization shared, public demo;
- configure space metadata: name, code, description, icon, language, domain, retention policy;
- workspace switcher and recent spaces;
- invite/access code generation, expiration, usage count, and revocation.

Key rules:

- all documents, chunks, sessions, citations, audit logs, and prompt settings must belong to a `space_id`;
- users only see spaces where they have membership or inherited access;
- archived spaces become read-only unless restored by an admin.

Acceptance criteria:

- a user in Audit cannot see Tax spaces unless explicitly authorized;
- access code cannot bypass RBAC after membership is created;
- space switching clears active session context and reloads allowed modules.

### M3. Scenario Template Center

Purpose: make business-line replication fast without redeploying the system.

Functions:

- template library for common scenarios:
  - onboarding assistant;
  - audit project AI;
  - audit methodology query;
  - standards Q&A;
  - cross-standard comparison;
  - material misstatement risk identification;
  - working-paper drafting guide;
  - independence compliance check;
  - audit opinion decision support;
- each template defines:
  - default prompt policy;
  - citation requirement;
  - retrieval filters;
  - recommended document categories;
  - default roles;
  - suggested quick questions;
  - answer format;
  - compliance warnings;
- create a new space from a template;
- clone and customize templates by business line;
- version templates and show upgrade notes.

Acceptance criteria:

- admin can create a new business space from a template in under 5 minutes;
- template changes do not silently alter existing production spaces;
- users can see scenario-specific quick actions in chat.

### M4. Knowledge Base Management

Purpose: ingest, govern, and maintain source documents.

Functions:

- upload PDF, DOCX, HTML, TXT, Markdown, and future spreadsheet files;
- validate file type by extension, MIME, and magic number;
- scan file size, filename, encoding, and unsafe content;
- assign document category, source type, business line, space, owner, effective date, expiry date, confidentiality level;
- document status flow: uploaded -> parsing -> chunking -> embedding -> active -> stale -> archived -> failed;
- manual re-index and batch re-index;
- document deletion with permission and audit;
- source preview and citation inspection;
- stale knowledge reminders;
- duplicate and near-duplicate detection;
- knowledge quality score: freshness, citation usage, failed chunks, low-relevance answers.

Acceptance criteria:

- every answer citation links back to a source document and chunk;
- failed ingestion creates an actionable error state;
- archived documents are excluded from retrieval by default;
- sensitive files cannot be downloaded through unauthenticated media URLs.

### M5. External Collection (Not Supported In Current Version)

**Status: removed in V6.0.** The Web crawler / automatic external collection
feature is **not supported in the current version**. Knowledge is sourced only
from:

- administrator file uploads (PDF, DOCX, HTML, TXT, Markdown);
- manually maintained documents;
- future controlled import mechanisms (out of scope for V6.0).

There are no crawler jobs, crawler scheduling, crawler APIs, or crawler UI in
this version. The historical `crawler_*` database tables may remain for data
retention, but no application code exposes them. Should automated collection be
reintroduced later, it must re-establish the SSRF/robots.txt/XSS safeguards
before shipping.

### M6. RAG Retrieval And Answer Engine

Purpose: provide accurate, source-backed answers inside a selected knowledge space.

Functions:

- query rewriting and intent classification;
- retrieval limited by `space_id`, permission, document status, category, and scenario;
- pgvector semantic search with metadata filters;
- optional BM25/hybrid retrieval for exact standards references;
- reranking and source diversity control;
- prompt assembly with scenario policy and source snippets;
- answer generation through Qwen/DashScope OpenAI-compatible API;
- streaming response through SSE;
- citation generation with source title, chunk excerpt, relevance score, and URL/file link;
- refusal or escalation when source evidence is insufficient;
- answer confidence and "needs human review" markers;
- feedback loop: helpful/unhelpful, wrong source, outdated source.

Acceptance criteria:

- answers must not cite documents outside the active space;
- answer includes citations when using knowledge base content;
- low-evidence answers must say that the source base is insufficient;
- retrieval filters must use allowlisted metadata keys to avoid SQL injection.

### M7. Chat And Session Experience

Purpose: make KnowPilot usable as the primary knowledge work interface.

Functions:

- new chat in current space;
- quick questions from scenario template;
- message input with character limit and offline guard;
- SSE streaming with stop generation;
- source citation drawer;
- copy/share/regenerate answer;
- conversation title generation;
- session list by date and current space;
- search history;
- pin important sessions;
- export session as Markdown/PDF in later phase;
- clear context when switching spaces;
- mobile drawer and responsive layout.

Acceptance criteria:

- switching to another space cannot leak previous space context into the next answer;
- session history is scoped by user and space;
- citation drawer remains readable on desktop and mobile;
- interrupted streams can be stopped without corrupting session state.

### M8. RBAC And Object-Level Permission

Purpose: protect knowledge assets by role, business line, and space.

Permission dimensions:

- organization role;
- business-line role;
- space role;
- document ownership;
- scenario/module permission;
- action-level permission code.

Recommended roles:

| Role | Scope | Typical abilities |
| --- | --- | --- |
| Super Admin | Platform | system configuration, emergency access |
| Organization Admin | Organization | manage business lines, users, global audit |
| Business Admin | Business line | manage spaces and users in line |
| Space Owner | Space | configure space, assign roles, approve sources |
| Knowledge Admin | Space | upload, re-index, archive documents |
| Reviewer | Space | review answers, flag documents, inspect logs |
| Member | Space | ask questions and view allowed sources |
| Guest | Space/demo | limited Q&A, no source download |

Core permission codes:

| Domain | Example permissions |
| --- | --- |
| space | `space.view`, `space.create`, `space.update`, `space.archive`, `space.invite` |
| document | `document.view`, `document.upload`, `document.update`, `document.delete`, `document.reindex`, `document.download` |
| chat | `chat.ask`, `chat.view_history`, `chat.share`, `chat.export` |
| template | `template.view`, `template.create`, `template.update`, `template.apply` |
| admin | `user.manage`, `role.manage`, `audit.view`, `system.monitor`, `model.configure` |

Acceptance criteria:

- every write action checks explicit permission;
- object-level checks prevent one admin from modifying another space without access;
- superuser actions are allowed but always specially audited;
- frontend role guards improve UX but do not replace backend checks.

### M9. Audit, Compliance, And Governance

Purpose: make the product acceptable in audit, finance, healthcare, government, and other compliance-heavy contexts.

Functions:

- audit all sensitive actions:
  - login/logout/token refresh;
  - space create/update/archive;
  - invite code create/use/revoke;
  - document upload/download/delete/re-index;
  - role and permission changes;
  - model/prompt configuration changes;
  - failed permission attempts;
- immutable audit log fields: actor, action, target, scope, IP, user agent, timestamp, result, metadata;
- audit search and filtering;
- retention policy by organization/space;
- sensitive data and confidential document labels;
- answer review queue for low-confidence or flagged answers;
- compliance report export in later phase.

Acceptance criteria:

- security-sensitive actions can be reconstructed from logs;
- failed access attempts are visible to admins;
- users cannot edit or delete audit logs through normal APIs.

### M10. Admin Dashboard And System Monitoring

Purpose: give admins operational visibility.

Functions:

- system health: backend, database, Redis, Celery, vector DB, LLM API;
- usage metrics: active users, sessions, questions, citations, document count;
- RAG quality metrics: retrieval latency, generation latency, no-answer rate, low-confidence rate;
- ingestion queue and failed jobs;
- model/API error rate and token usage;
- permission risk summary;
- stale document and expiring source warnings.

Acceptance criteria:

- admin can identify whether a bad answer came from retrieval, stale source, prompt, model, or missing knowledge;
- failed Celery jobs are visible with retry action;
- dashboards are scoped by admin permission level.

### M11. User Feedback And Knowledge Improvement Loop

Purpose: turn usage into knowledge-base improvement.

Functions:

- answer feedback: helpful, unhelpful, incorrect, outdated, missing source;
- flag answer for review;
- suggest new document/source;
- create knowledge gap ticket;
- show top unanswered questions by space;
- show documents with high citation usage;
- show documents never retrieved;
- reviewer resolution workflow.

Acceptance criteria:

- flagged answers are attached to session, question, answer, citations, and retrieval metadata;
- knowledge admins can prioritize updates based on real usage;
- resolved issues are traceable.

### M12. Internationalization, Theme, And Accessibility

Purpose: support professional, cross-device enterprise usage.

Functions:

- Chinese and English language packs;
- user-level language preference;
- light/dark/system theme;
- responsive desktop/tablet/mobile layout;
- keyboard navigation;
- screen-reader-friendly live regions for streaming;
- reduced-motion support;
- accessible color contrast.

Acceptance criteria:

- all new navigation labels and admin states have i18n keys;
- mobile users can switch spaces, ask questions, and inspect citations;
- key flows are usable by keyboard.

## 5. Data Model Draft

### 5.1 Core Entities

| Entity | Key fields |
| --- | --- |
| Organization | `id`, `name`, `slug`, `status`, `settings`, `created_at` |
| BusinessLine | `id`, `organization_id`, `name`, `code`, `description`, `status` |
| KnowledgeSpace | `id`, `organization_id`, `business_line_id`, `template_id`, `name`, `code`, `visibility`, `status`, `settings` |
| SpaceMembership | `id`, `space_id`, `user_id`, `role_id`, `status`, `expires_at` |
| InviteCode | `id`, `space_id`, `code_hash`, `role_id`, `expires_at`, `max_uses`, `used_count`, `status` |
| ScenarioTemplate | `id`, `name`, `scenario_type`, `version`, `prompt_policy`, `retrieval_policy`, `default_permissions` |
| Document | `id`, `space_id`, `uploaded_by`, `title`, `file_type`, `source_type`, `status`, `effective_date`, `expiry_date`, `confidentiality` |
| DocumentChunk | `id`, `document_id`, `space_id`, `chunk_index`, `content`, `metadata`, `embedding_vector` |
| ChatSession | `id`, `space_id`, `user_id`, `title`, `status`, `created_at`, `updated_at` |
| ChatMessage | `id`, `session_id`, `role`, `content`, `metadata`, `created_at` |
| Citation | `id`, `message_id`, `document_id`, `chunk_id`, `score`, `excerpt`, `metadata` |
| AuditLog | `id`, `actor_id`, `action`, `target_type`, `target_id`, `scope`, `result`, `metadata`, `created_at` |
| Feedback | `id`, `message_id`, `user_id`, `type`, `comment`, `status`, `reviewer_id` |

### 5.2 Required Isolation Fields

Every business object should include one or more of:

- `organization_id`
- `business_line_id`
- `space_id`
- `owner_id`

Minimum hard rule: `Document`, `DocumentChunk`, `ChatSession`, `ChatMessage`, `Citation`, `Feedback`, and scenario configuration must be scoped by `space_id`.

## 6. API Surface Draft

### 6.1 Space APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/spaces/` | list spaces visible to current user |
| POST | `/api/v1/spaces/` | create space |
| GET | `/api/v1/spaces/{id}/` | get space detail |
| PATCH | `/api/v1/spaces/{id}/` | update space |
| POST | `/api/v1/spaces/{id}/archive/` | archive space |
| POST | `/api/v1/spaces/{id}/switch/` | set active/default space |
| POST | `/api/v1/spaces/join/` | join by invite/access code |

### 6.2 Template APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/templates/` | list scenario templates |
| POST | `/api/v1/templates/` | create template |
| POST | `/api/v1/templates/{id}/create-space/` | create space from template |
| GET | `/api/v1/templates/{id}/versions/` | list template versions |

### 6.3 Knowledge APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/spaces/{space_id}/documents/` | list space documents |
| POST | `/api/v1/spaces/{space_id}/documents/` | upload document |
| POST | `/api/v1/documents/{id}/reindex/` | re-index document |
| DELETE | `/api/v1/documents/{id}/` | delete/archive document |
| GET | `/api/v1/documents/{id}/citations/` | inspect citation chunks |

### 6.4 Chat APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/spaces/{space_id}/sessions/` | list sessions in space |
| POST | `/api/v1/spaces/{space_id}/sessions/` | create session |
| POST | `/api/v1/sessions/{id}/send/` | send message with SSE response |
| POST | `/api/v1/messages/{id}/feedback/` | submit feedback |
| GET | `/api/v1/messages/{id}/citations/` | get citations |

### 6.5 Admin / Audit APIs

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/admin/users/` | manage users |
| GET | `/api/v1/admin/roles/` | manage roles |
| GET | `/api/v1/admin/audit-logs/` | query audit logs |
| GET | `/api/v1/admin/health/` | system health |
| GET | `/api/v1/admin/metrics/` | usage and quality metrics |

## 7. Frontend Page Modules

### 7.1 Login / Entry

- login form;
- SSO entry placeholder;
- access-code entry for pilot/demo;
- after login, route to default space or space picker.

### 7.2 Space Picker

- list authorized spaces grouped by business line;
- search spaces;
- recent spaces;
- join by access code;
- create space button for admins.

### 7.3 Chat Workspace

- current space header and switcher;
- scenario quick actions;
- session sidebar scoped to space;
- chat messages and streaming answer;
- citation drawer;
- feedback controls.

### 7.4 Knowledge Admin

- document list;
- upload/re-index/delete;
- document metadata edit;
- ingestion status and errors;
- stale document warnings.

### 7.5 Template Admin

- template list;
- template detail;
- create space from template;
- prompt/retrieval policy editor for authorized admins.

### 7.6 Governance Admin

- user/role/permission management;
- space membership management;
- invite code management;
- audit log search;
- system health and usage metrics.

## 8. Deployment Model

### 8.1 Default Deployment

One Docker Compose deployment for development and pilot:

- frontend: React/Vite/nginx;
- backend: Django/DRF;
- worker: Celery;
- broker/cache: Redis;
- database/vector DB: PostgreSQL 16 + pgvector;
- model API: DashScope/Qwen through OpenAI-compatible protocol.

### 8.2 Production Evolution

Recommended production path:

1. single application deployment with logical tenant isolation;
2. separate object storage for documents;
3. managed PostgreSQL with pgvector or dedicated vector service if scale requires;
4. centralized logs and monitoring;
5. optional isolated deployment only for high-confidentiality clients or regulated business units.

### 8.3 Isolation Levels

| Level | Description | When to use |
| --- | --- | --- |
| Logical isolation | shared runtime/database, strict `space_id` filters | default |
| Schema isolation | shared runtime, separate DB schema per tenant | large client tenant |
| Database isolation | shared app, separate DB/vector index | high confidentiality |
| Full deployment isolation | separate app/runtime/network | legal or regulatory hard boundary |

## 9. Implementation Phases

This section is the canonical roadmap. Detailed implementation evidence for
delivered extensions and phase slices is collected in
`## 14. Implementation Appendix: Delivered Extensions and Phase Details`.

### Phase 1: Multi-Space Foundation

- add Organization, BusinessLine, KnowledgeSpace, SpaceMembership, InviteCode;
- add `space_id` to documents, chunks, sessions, messages, citations, feedback;
- add space switcher and space-scoped chat/session list;
- enforce backend space permission checks.

### Phase 2: Template-Driven Replication

- create scenario template model;
- implement "create space from template";
- add scenario quick questions and prompt/retrieval policy;
- seed templates for the nine KnowPilot scenarios.

Delivered slices:

- Phase 2A: Scenario Template Center MVP.
- Phase 2B: Template Discovery & Operations filter slice.

### Phase 3: Knowledge Governance Hardening

- magic number/MIME validation;
- authenticated media/document access;
- object-level document permissions;
- allowlisted retrieval filters.

Delivered and planned slices:

- Phase 3A: Authenticated Document Access.
- Phase 3B: File Validation Consistency.
- Phase 3C: Retrieval Safety.

### Phase 4: Audit And Admin Center

- expand audit log coverage;
- role/permission management UI;
- invite code management UI;
- system health and usage metrics;
- stale knowledge and quality dashboards.

### Phase 5: Knowledge Improvement Loop

- answer feedback workflow;
- flagged-answer review queue;
- knowledge gap analytics;
- exportable compliance and usage reports.

## 10. Non-Functional Requirements

### Security

- all APIs require authentication unless explicitly public;
- all space-scoped queries must filter by authorized `space_id`;
- upload inputs must be validated;
- media/document downloads must be authenticated;
- sensitive actions must be audit logged;
- superuser actions must be distinguishable in audit logs.

### Performance

- streaming answer first token target: under 3 seconds after retrieval in normal conditions;
- retrieval target: under 1 second for common space sizes;
- background ingestion through Celery;
- pagination for documents, sessions, audit logs, and users;
- caching for user permissions and frequently used embeddings where safe.

### Reliability

- ingestion jobs are retryable;
- failed documents expose clear error state;
- chat stream cancellation does not corrupt session state;
- document ingestion failures do not block unrelated spaces.

### Compliance

- source citations are required for knowledge-backed answers;
- access and changes are traceable;
- stale/expired documents are marked and excluded or warned.

## 11. Success Metrics

| Metric | Target direction |
| --- | --- |
| Time to create a new business space | decrease to minutes |
| Question-to-answer time | decrease from hours/minutes to seconds |
| Citation coverage | increase |
| No-answer rate caused by missing knowledge | tracked and reduced |
| Repeated questions to managers | reduced |
| Stale document usage | reduced |
| Spaces created per deployment | increased |
| Knowledge admin time per space | reduced |

## 12. Open Decisions

1. Should access code be available on the login page before authentication, or only after login as "join space by code"?
   - Recommendation: allow pilot/demo code before login only for non-confidential demo spaces; production join code should require login.
2. Should business lines share global templates or clone templates into each line?
   - Recommendation: global templates with business-line overrides and versioning.
3. Should cross-space search be allowed?
   - Recommendation: only for roles with explicit multi-space permission; default chat remains single-space to avoid source leakage.
4. Should each project be a space or a document category under a space?
   - Recommendation: high-confidentiality or long-running projects become spaces; small topics can be categories.
5. Should answers quote source text verbatim?
   - Recommendation: keep excerpts short, show source links, and prefer summarized answers with citations.

## 13. Final Design Principle

KnowPilot should feel like **one product** to the user and **many isolated knowledge brains** to the organization.

The platform should not multiply deployments for every business line. It should multiply spaces, templates, permissions, and knowledge bases inside one governed system. That is the architecture that best matches the product promise: one deployment, unlimited replication, full-scenario reuse.

## 14. Implementation Appendix: Delivered Extensions and Phase Details

This appendix preserves implementation details that were added after the core
SPEC was written. It should be read as evidence and clarification for the
roadmap in `## 9. Implementation Phases`, not as separate product phases.

### 14.1 V7 Identity & Governance (extension)

V7 extends §M1 / §M2 / §M8 / §M9 with the identity-access layer that was missing
in V6.x: self-registration (regular users pick a Service Line; admins use tiered
**Admin Registration Codes**), email-based space invitations, an in-app
**notification + announcement** system, a separate admin console vs employee UI,
and a frontend RBAC cleanup that stops treating organizational `role_level` as an
authorization role.

Full design, role matrix, and logic diagrams: **`audit_reports/current/KnowPilot_V7_Identity_RBAC_Spec.md`**.

Key invariants:

- Permission = "who you are in the org" (Super/Org/Business Admin / Employee) ×
  "what you can do in this space" (Owner / Knowledge Admin / Reviewer / Member / Guest).
- A "project group" is a `KnowledgeSpace`; its lead is the Space **Owner**.
- `AdminRegistrationCode.grants_role` can only be `org_admin` or `business_admin` �?  **Super Admin is never obtainable through any registration entry point** (CLI /
  console promotion only).
- The access/admin code is an *entry* mechanism; it never bypasses RBAC.

Implementation status as of 2026-07-01:

- V7 identity, admin-code registration, email space invites, notification feed,
  scoped announcements, admin console entry, and frontend RBAC cleanup are
  implemented.
- Optional signup approval is operational via
  `/api/v1/rbac/users/{id}/activate/`, audited as `signup_approved`.
- Frontend authorization no longer derives access from `role_level`; it uses
  backend roles/permissions plus V7 admin-scope flags.
- Verified with `python manage.py test apps.users.tests_v7_identity
  --settings=config.settings.local_test` and `npm run build`.

### 14.2 Phase 2A: Scenario Template Center MVP

Phase 2A delivers the Scenario Template Center MVP, enabling fast replication of domain-specific knowledge brains (onboarding, audit, tax, consulting, core_services).

Full design, fields, API definitions, and Phase 2B filter status: **`audit_reports/current/KnowPilot_Phase2A_Template_Center_Spec.md`**.

Key features:
- `ScenarioTemplate` model carrying defaults (default_language, default_visibility, icon, quick_questions, prompt_policy, retrieval_policy).
- CRUD APIs for templates, scoped to platform, organization, or business-line administrators.
- `POST /api/v1/templates/{id}/create-space/` endpoint enabling admins to instantiate a space pre-configured with template settings.
- Admin template UI with create, edit, clone, archive, restore, application history, revision history, and create-space actions.
- Chat welcome quick questions sourced from template-created space settings.
- Idempotent `seed_scenario_templates` management command seeding 5 default templates.
- Fully verified via unit test suite `apps.scenario_templates.tests_phase2a`.

### 14.3 Phase 2B: Template Discovery & Operations

Phase 2B extends the template center from CRUD into day-to-day operations and discovery.

Implementation status as of 2026-07-01:

- Scope-safe list filters are implemented on `GET /api/v1/templates/`: `q`, `scenario_type`, `is_active`, `scope`, `organization`, and `business_line`.
- RBAC/scope visibility is applied before query filters, so filters only narrow visible templates.
- Admin Template UI exposes search, scenario type, status, scope, organization, and business-line filters.
- Lifecycle operations remain available from the filtered table: clone, archive, restore, applications, revisions, and create-space.
- Verified with backend template regression tests, i18n checks, and frontend production build.

Remaining later Phase 2B/2C work:

- Template tags/categories and recommended ordering.
- Saved filter state in URL query params.
- Pagination, sorting, and larger-list ergonomics.
- Template marketplace/sharing, revision diff/rollback, analytics charts, and automatic document binding.

### 14.4 Phase 3A: Authenticated Document Access

Implementation status as of 2026-07-01:

- Added object-authorized
  `GET /api/v1/documents/{id}/download/` delivery.
- The endpoint enforces the document space's `document.download` permission,
  conceals cross-space objects, and handles missing storage safely.
- Document API responses no longer expose raw storage-backed media URLs; the
  upload field is write-only and responses provide a protected `download_url`.
- Successful downloads are audited as `document_download`; denied same-space
  attempts are audited as `permission_denied`.
- Responses use attachment disposition, `X-Content-Type-Options: nosniff`, and
  `Cache-Control: private, no-store`.
- The Knowledge Base UI downloads through the authenticated Axios client and
  safely releases temporary Blob URLs.
- Verified by 68 backend regression tests, 39 frontend tests, i18n validation,
  migration checks, Django system checks, and a production frontend build.

Audit evidence:
`audit_reports/v7.3/Phase3A_Document_Access_Test_Audit_Report_V7.3.md`.

Next Phase 3 slice: reconcile file-type policy and harden extension, MIME,
magic-number, and safe-text validation across manual upload, batch upload, and
the frontend.

### 14.5 Phase 3B: File Validation Consistency

Implementation status as of 2026-07-01:

- The current-version policy accepts PDF, DOCX, HTML/HTM, TXT, and
  Markdown; DOC/CSV/XLSX/PPTX remain unsupported.
- Manual and batch upload use one canonical backend policy for extension,
  structure/signature, UTF-8 text, minimum/maximum size, and type derivation.
- `file_type`, `file_size`, and a missing safe title are derived by the server;
  clients cannot mutate type/size without replacing the file.
- Unknown batch extensions are rejected rather than silently persisted as TXT.
- Valid DOCX batch files are distinguished from prohibited nested ZIP inputs.
- The frontend accept list matches the backend and uploads through the shared
  Axios client so JWT and active-space headers are present.
- Verified by 85 backend regression tests, 42 frontend tests, Python
  compilation, i18n validation, migrations/system checks, and production build.

Audit evidence:
`audit_reports/v7.3/Phase3B_File_Validation_Test_Audit_Report_V7.3.md`.

Next Phase 3 slice: allowlisted retrieval filters, mandatory space scoping, and
active-document status enforcement across every retrieval path.
