# KnowPilot SPEC Implementation Progress

Date: 2026-07-01

This file is the current engineering progress tracker for `SPEC.MD`.
It records what has been implemented, what is partially complete, and what should be built next.

## Executive Status

The full SPEC is not complete yet.

Current stage:

- Phase 1 Multi-Space Foundation: mostly implemented.
- V7 Identity & Governance extension: implemented and verified.
- Phase 2A Scenario Template Center MVP: implemented and verified.
- Phase 2B Template Discovery & Operations: filter slice complete.
- Phase 3A authenticated document access: implemented and verified.
- Phase 3B file-validation consistency: implemented and verified.
- Phase 3C retrieval safety: next recommended stage.

Latest verified baseline:

- Backend migration dry-run: no changes detected.
- Django system check: passes with 3 known django-allauth deprecation warnings.
- Backend Phase 3A/3B + space + V7 + template regression suite: 85 tests OK.
- Frontend i18n check: OK.
- Frontend test suite: 42 tests OK.
- Frontend production build: OK with known Vite chunk/dynamic import warnings.

## SPEC Coverage Matrix

| SPEC Area | Status | Evidence | Remaining Work |
| --- | --- | --- | --- |
| 1. Architecture Decision | Implemented in product direction | Single integrated app, multi-space model, org/business-line scope, template replication | Production hardening and deployment topology refinements |
| 2. Product Scope | Partially implemented | RAG app, knowledge spaces, identity/governance, template center | Full quality loop, analytics, and advanced governance still pending |
| 3. Information Architecture | Mostly implemented | Chat, knowledge, space management, admin console, template admin | Deep links/share flow and some admin analytics views remain |
| M1 Authentication and Identity | Implemented | Email/password registration, admin-code registration, optional signup approval, `/auth/me` identity payload | SSO remains a placeholder/future integration |
| M2 Organization, Business Line, and Space Management | Mostly implemented | Organization, business line, KnowledgeSpace, membership, invite/access-code flows | Transfer/archive polish and broader admin ergonomics |
| M3 Scenario Templates | Implemented through Phase 2B filter slice | `ScenarioTemplate`, create-space, quick questions, prompt/retrieval policy fields, clone, archive/restore, revisions, applications, filters | Tags/categories, recommendation ordering, URL-saved filters, marketplace/sharing |
| M4 Knowledge Base and Document Lifecycle | Partially implemented | Upload/re-index/delete/archive, object-authorized delivery, and one server-enforced PDF/DOCX/HTML/TXT/Markdown validation policy | Stale/expired states, duplicate UX, quality score |
| M5 External Collection | Explicitly out of scope | SPEC says crawler collection is not supported in current version | No immediate work unless scope changes |
| M6 RAG Retrieval and Answer Engine | Partially implemented | Space-scoped chat/RAG baseline exists | Allowlisted retrieval filters, hybrid retrieval, reranking, confidence markers, stronger insufficient-evidence behavior |
| M7 Chat and Session Experience | Partially implemented | Space-scoped chat, session list, quick questions from template-created spaces | Citation drawer polish, feedback controls, export, mobile verification, stream cancellation hardening |
| M8 RBAC and Object-Level Permission | Mostly implemented | Backend RBAC/admin scopes, frontend RoleGuard cleanup, scoped template permissions | Permission matrix coverage expansion and cache/performance hardening |
| M9 Audit, Compliance, and Governance | Partially implemented | Audit log model/actions, admin audit page, V7 governance events | Compliance export, deeper audit coverage, bad-answer traceability |
| M10 Metrics, Monitoring, and Quality Dashboard | Not complete | Basic admin foundation only | Usage metrics, RAG quality metrics, ingestion queue visibility, model/API/token dashboards, stale knowledge dashboard |
| M11 User Feedback and Knowledge Improvement Loop | Not complete | No completed feedback/review workflow evidence | Helpful/unhelpful feedback, flagged-answer review queue, gap tickets, reviewer resolution workflow |
| M12 Frontend UX and Accessibility | Partially implemented | React/AntD app, admin console, responsive foundations | Formal accessibility pass, keyboard flow verification, mobile citation inspection |
| 5. Data Model Draft | Partially implemented | Core space, identity, audit, notification, and template models exist | Citation/feedback model completion and quality metrics schema |
| 6. API Surface Draft | Partially implemented | Auth, spaces, templates, notifications, audit/admin foundations, protected document download API | Metrics APIs, feedback APIs, citation-inspection APIs |
| 7. Frontend Page Modules | Partially implemented | Login, space picker/management, chat, knowledge admin, template admin, governance admin | Metrics dashboards, feedback controls, source/citation inspection polish |
| 8. Deployment Model | Partially implemented | Current `docker-compose.yml`, backend Dockerfile, frontend Dockerfile | Production deployment guide, secrets handling, observability, scaling guidance |
| 9. Implementation Phases | In progress | Phase 1, V7, Phase 2A, Phase 2B filter slice, Phase 3A, and Phase 3B delivered | Phase 3C, Phase 4, Phase 5 remain |
| 10. Non-Functional Requirements | Partially implemented | Auth required for APIs, scoped permissions, tests | Performance targets, retry visibility, stale-source compliance, caching strategy |
| 11. Success Metrics | Not complete | Metrics listed in SPEC | Instrumentation and dashboard work required |
| 12. Open Decisions | Open | Recommendations documented in SPEC | Product decisions still need confirmation before later phases |

## Completed Functional Highlights

- V7 identity and governance:
  - User registration and admin registration codes.
  - Optional signup approval.
  - Email-based space invitations.
  - Notification feed and scoped announcements.
  - Admin console routes and frontend RBAC cleanup.
- Space and governance foundation:
  - Organizations, business lines, knowledge spaces, memberships, access codes.
  - Scoped admin roles and permission checks.
  - Audit logging for sensitive governance operations.
- Scenario Template Center:
  - Template CRUD with platform/org/business-line ownership.
  - Create KnowledgeSpace from template.
  - Template quick questions on chat welcome.
  - Usage count, last applied timestamp, applications, revisions.
  - Clone, archive, restore lifecycle actions.
  - Scope-safe list filters: `q`, `scenario_type`, `is_active`, `scope`, `organization`, `business_line`.
  - Admin UI for the full template lifecycle and filters.
- Phase 3A document access:
  - Object-authorized `GET /api/v1/documents/{id}/download/`.
  - Raw storage URLs removed from document API responses.
  - `document.download` permission enforcement with cross-space concealment.
  - Success and denial audit events.
  - Frontend Blob download with safe filename parsing.
- Phase 3B file validation:
  - Canonical PDF/DOCX/HTML/TXT/Markdown policy shared by manual and batch upload.
  - Server-derived type, size, and safe default title.
  - Binary-text, signature mismatch, unknown extension, and unsupported-format rejection.
  - Batch DOCX support and unknown-extension fallback closure.
  - Frontend accept-list alignment and interceptor-aware upload.

## Next Recommended Stage

Continue Phase 3C: retrieval safety.

Suggested order:

1. Retrieval safety:
   - Add allowlisted retrieval filter keys.
   - Ensure all retrieval paths are scoped by `space_id` and document status.
2. Document states:
   - Make stale/expired/failed states explicit and visible in admin UI.
   - Exclude archived/stale documents from retrieval by default or warn clearly.
3. Verification:
   - Add backend regression tests for file validation, retrieval filters, and stale/failed states.
   - Add frontend validation for admin document error states.

## Deferred Later Work

- Template tags/categories and recommendation ordering.
- Saved template filters in URL query params.
- Template marketplace/sharing across organizations.
- Revision diff viewer and rollback.
- Advanced analytics charts.
- Automatic document binding when creating spaces from templates.
- Feedback workflow and flagged-answer review queue.
- Knowledge gap analytics and exportable compliance reports.
