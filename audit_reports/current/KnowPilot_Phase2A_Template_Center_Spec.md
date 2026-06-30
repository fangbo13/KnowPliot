# KnowPilot Phase 2A: Scenario Template Center Spec

This document details the design and implementation of the backend infrastructure for the **Scenario Template Center MVP (Phase 2A)**.

---

## 1. Goal Description

The Scenario Template Center enables workspace creation from predefined blueprints (templates) tailored to specific industry or departmental scenarios (e.g., Audit, Tax, Onboarding). This accelerates the kickoff process by pre-configuring default settings, language preferences, default visibility, and sample prompt questions (quick questions) on the chat interface.

---

## 2. ScenarioTemplate Model Schema

The template configuration is stored in the `ScenarioTemplate` model:

| Field | Type | Options / Description |
|---|---|---|
| `id` | `UUID` | Primary key, automatically generated. |
| `name` | `CharField` | Human-readable name of the template (max length: 200). |
| `code` | `SlugField` | Globally unique slug for internal reference/routing (unique=True). |
| `description` | `TextField` | Extended description of what the template covers. |
| `scenario_type` | `CharField` | Scoped choices: `onboarding`, `audit`, `tax`, `consulting`, `core_services`, `standards_qa`, `project_ai`. |
| `default_language` | `CharField` | Default language for the space (default: `'en'`). |
| `icon` | `CharField` | Default icon name for frontend visualization. |
| `quick_questions` | `JSONField` | Array of preseeded chat prompt questions (default: `[]`). |
| `prompt_policy` | `JSONField` | Config dict for system prompts or custom system instructions. |
| `retrieval_policy` | `JSONField` | Config dict for RAG search thresholds/ratios. |
| `default_visibility`| `CharField` | Choices matching standard KnowledgeSpace visibilities: `private` (default), `business_line`, `organization`, `public_demo`. |
| `is_active` | `BooleanField` | Active status. Inactive templates are only visible to administrators. |
| `organization` | `ForeignKey` | Optional organization scope. Empty means platform-global template. |
| `business_line` | `ForeignKey` | Optional business-line scope. Empty means global or organization-wide template. |
| `created_by` | `ForeignKey` | Reference to the user who created it (nullable). |
| `created_at` | `DateTimeField` | Automatically recorded creation timestamp. |
| `updated_at` | `DateTimeField` | Automatically updated modification timestamp. |

The read API also returns:

| Field | Type | Description |
|---|---|---|
| `can_manage` | `Boolean` | Whether the requesting admin can edit/delete the template. |
| `usage_count` | `Integer` | Number of template applications visible within the requester's admin scope. |
| `last_applied_at` | `DateTime` | Most recent visible template application timestamp, or `null`. |
| `latest_version` | `Integer` | Latest recorded template revision version. |

Template application history is stored in `ScenarioTemplateApplication`:

| Field | Type | Description |
|---|---|---|
| `template` | `ForeignKey` | Applied template. |
| `space` | `ForeignKey` | Created `KnowledgeSpace`; nullable to preserve history if the space is deleted. |
| `organization` | `ForeignKey` | Organization where the space was created. |
| `business_line` | `ForeignKey` | Business line where the space was created, if any. |
| `created_by` | `ForeignKey` | User who instantiated the template. |
| `template_snapshot` | `JSONField` | Immutable snapshot of key template metadata at application time. |
| `created_at` | `DateTimeField` | Application timestamp. |

Template revision history is stored in `ScenarioTemplateRevision`:

| Field | Type | Description |
|---|---|---|
| `template` | `ForeignKey` | Template being revised. |
| `version` | `PositiveIntegerField` | Monotonic version number per template. |
| `snapshot` | `JSONField` | Immutable snapshot after create/update. |
| `change_note` | `CharField` | System note such as `created` or `updated`. |
| `created_by` | `ForeignKey` | User who created the revision. |
| `created_at` | `DateTimeField` | Revision timestamp. |

---

## 3. Implemented API Endpoints

All endpoints are hosted under `/api/v1/templates/`:

### 1. List Templates
- **URL**: `GET /api/v1/templates/`
- **Authentication**: Required.
- **Query Parameters**:
  - `q`: Search visible templates by name, code, or description.
  - `scenario_type`: Filter by one scenario type.
  - `is_active`: Admin-only active/inactive filter (`true` / `false`).
  - `scope`: Filter by `global`, `organization`, or `business_line`.
  - `organization`: Filter by organization id within the requester's visible scope.
  - `business_line`: Filter by business-line id within the requester's visible scope.
- **Behavior**:
  - Regular users retrieve active platform-global templates (`is_active=True`, no organization/business-line scope).
  - Platform admins retrieve all templates.
  - Org admins retrieve platform-global templates plus templates scoped to organizations they administer.
  - Business admins retrieve platform-global templates plus templates scoped to business lines they administer.
  - RBAC/scope visibility is applied before query filters, so filters never reveal out-of-scope templates.

### 2. Template Detail
- **URL**: `GET /api/v1/templates/{id}/`
- **Authentication**: Required.
- **Behavior**:
  - Returns template detail. Regular users receive 404 for inactive templates.

### 3. Create Template
- **URL**: `POST /api/v1/templates/`
- **Authentication**: Required.
- **Role Permission**: Platform Admin / Org Admin / Business Admin only. Ordinary employees receive `403 Forbidden`.
- **Scope Behavior**:
  - Platform admins may create global or scoped templates.
  - Org admins create templates inside their administered organization.
  - Business admins create templates inside their administered business line.

### 4. Update Template
- **URL**: `PATCH /api/v1/templates/{id}/` (or `PUT`)
- **Authentication**: Required.
- **Role Permission**: Platform Admin / Org Admin / Business Admin only.
- **Scope Behavior**:
  - Platform admins may update or delete any template.
  - Scoped admins may update/delete only templates in their own organization/business line.
  - Platform-global templates are platform-owned; scoped admins may instantiate them but cannot edit/delete them.

### 5. Create Space from Template
- **URL**: `POST /api/v1/templates/{id}/create-space/`
- **Authentication**: Required.
- **Role Permission**: Platform Admin / Org Admin / Business Admin only.
- **Request Body**:
  ```json
  {
    "name": "Audit IPO Assistant Space",
    "code": "audit-ipo-assistant-space",
    "organization": "uuid (optional)",
    "business_line": "uuid (optional)",
    "visibility": "private (optional)"
  }
  ```
- **Instantiation Logic**:
1. Validates input parameters. Checks if the space code is unique (returns `400 Bad Request` if duplicate).
  2. Resolves organization and business-line scope:
     - Platform admins may target any organization/business line; if omitted, the default organization is used.
     - Org admins may create spaces only inside organizations they administer.
     - Business admins may create spaces only inside business lines they administer; if only one business line is in scope, it is used as the default.
     - A selected business line must belong to the selected organization.
  3. Provisions a new `KnowledgeSpace` using description, icon, default language, and default visibility from the template unless overridden by request parameters.
  4. Stores template metadata in the `settings` JSON field of the created space:
     ```json
     {
       "template_id": "...",
       "template_code": "...",
       "scenario_type": "...",
       "quick_questions": [...]
     }
     ```
  5. Attaches the creating user as the `owner` of the newly created space with `active` status.
  6. Emits a `space_create` event into the audit log.
  7. Creates a `ScenarioTemplateApplication` history record.
  8. Returns the serialized `KnowledgeSpace` data (`201 Created`).

### 6. List Template Applications
- **URL**: `GET /api/v1/templates/{id}/applications/`
- **Authentication**: Required.
- **Role Permission**: Platform Admin / Org Admin / Business Admin only.
- **Scope Behavior**:
  - Platform admins see all application records for the template.
  - Org admins see only application records in organizations they administer.
  - Business admins see only application records in business lines they administer.

### 7. List Template Revisions
- **URL**: `GET /api/v1/templates/{id}/revisions/`
- **Authentication**: Required.
- **Role Permission**: Platform Admin / Org Admin / Business Admin only.
- **Behavior**:
  - Returns immutable revision snapshots ordered by newest version first.
  - Revisions are created automatically when templates are created or updated.
  - Scoped admins can view revisions only for templates visible within their template scope.

### 8. Clone Template
- **URL**: `POST /api/v1/templates/{id}/clone/`
- **Authentication**: Required.
- **Role Permission**: Platform Admin / Org Admin / Business Admin only.
- **Request Body**:
  ```json
  {
    "name": "Audit Methodology Q&A - China",
    "code": "audit-methodology-qa-china",
    "organization": "uuid (optional)",
    "business_line": "uuid (optional)",
    "is_active": true
  }
  ```
- **Behavior**:
  - Clones description, scenario type, language, icon, quick questions, prompt policy, retrieval policy, and default visibility from the source template.
  - Platform admins may clone into global or scoped templates.
  - Org admins may clone visible templates into organizations they administer.
  - Business admins may clone visible templates into business lines they administer.
  - Clone creation records revision `v1` with a `cloned from <source-code>` change note.

### 9. Archive Template
- **URL**: `POST /api/v1/templates/{id}/archive/`
- **Authentication**: Required.
- **Role Permission**: Platform Admin / Org Admin / Business Admin only.
- **Behavior**:
  - Sets `is_active=false` without deleting the template, revisions, or application history.
  - Scoped admins can archive only templates they can manage.
  - Platform-global templates can only be archived by platform admins.
  - Records a new revision with `change_note=archived`.

### 10. Restore Template
- **URL**: `POST /api/v1/templates/{id}/restore/`
- **Authentication**: Required.
- **Role Permission**: Platform Admin / Org Admin / Business Admin only.
- **Behavior**:
  - Sets `is_active=true`.
  - Scoped admins can restore only templates they can manage.
  - Platform-global templates can only be restored by platform admins.
  - Records a new revision with `change_note=restored`.

---

## 4. Default Seeded Templates

Seeded via `python manage.py seed_scenario_templates`:

1. **New Hire Onboarding** (`new-hire-onboarding`) — onboarding
2. **Audit Methodology Q&A** (`audit-methodology-qa`) — audit
3. **Tax Policy Assistant** (`tax-policy-assistant`) — tax
4. **Consulting Engagement Assistant** (`consulting-engagement`) — consulting
5. **Core Services Helpdesk** (`core-services-helpdesk`) — core_services

---

## 5. Out of Scope

The following items are explicit non-goals for Phase 2A:
- **Template Sharing / Marketplace**: Cross-organization sharing options.
- **Advanced Analytics Dashboard**: Charts, leaderboards, and adoption trend visualizations.
- **Rollback / Diff Viewer**: Reverting to prior revisions or comparing revision snapshots.
- **Automated Document Binding**: Automatically duplicating or linking documents from a template into a newly created space.

---

## 6. Phase 2B: Discovery and Operations

Phase 2B starts the operational layer on top of Phase 2A.

Completed in the current Phase 2B filter slice:

- Scope-safe template search and filters on `/api/v1/templates/`.
- Admin UI filters for search text, scenario type, active status, template scope, organization, and business line.
- Continued lifecycle operations through clone, archive, restore, applications, and revisions.
- Regression tests proving `organization` and `business_line` filters narrow the requester's visible scope without exposing out-of-scope templates.

Deferred to later Phase 2B/2C slices:

- Template tags/categories and recommendation ordering.
- Saved filter state in URL query params.
- Pagination, sorting, and larger-list ergonomics.
- Template marketplace/sharing and advanced analytics.
