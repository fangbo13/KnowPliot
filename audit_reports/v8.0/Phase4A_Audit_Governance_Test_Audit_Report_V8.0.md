# Phase 4A Audit Governance Test Audit Report — V8.0

**Date:** 2026-07-02

**Baseline commit:** `b3c3f22`

**Phase commit subject:** `feat(audit): add scoped governance audit`

## Scope and data migration

- Added nullable, indexed `organization_id`, `business_line_id`, and `space_id`
  UUID fields to preserve immutable scope without cascade behavior.
- Added indexed `result` values: `success`, `denied`, and `failure`.
- Migration `audit.0009_audit_scope_and_result` is additive. Existing records
  remain unscoped and are visible only to platform administrators.

## Requirement traceability

| Requirement | Evidence | Result |
| --- | --- | --- |
| Platform administrator sees all records | Platform visibility test | PASS |
| Organization administrator is tenant-scoped | Cross-organization test | PASS |
| Business administrator is line-scoped | Cross-business-line test | PASS |
| Legacy HR flag grants no global audit access | Explicit 403 test | PASS |
| API is immutable through normal routes | POST returns 405 | PASS |
| Scope/result/date/action/user filters exist | API implementation and filter tests | PASS |
| Role, scope, and result are serialized | Response field assertions | PASS |
| Sensitive targets receive scope | Target/actor scope inference and tests | PASS |
| Frontend failures are visible | Admin audit component test | PASS |

## Verification evidence

```text
Backend focused: 13 tests passed.
Backend regression: 107 tests passed.
Django system check: passed with 3 known django-allauth deprecation warnings.
Migration dry-run: No changes detected.
Frontend: 43 tests passed.
i18n: all keys present.
TypeScript: passed.
Production build: passed with the existing Vite chunk warnings.
```

## Negative tests

- Organization and business administrators cannot see another tenant's logs.
- Unscoped historical records are hidden from non-platform administrators.
- A legacy `is_hr_admin` user receives 403.
- Audit records cannot be created through the list endpoint.
- A rejected frontend request produces visible user feedback.

## Residual risks

- Historical logs are deliberately not assigned guessed tenant scope.
- Audit retention, export, and bad-answer reconstruction remain Phase 4C/5 work.
- `SPEC.MD` legacy encoding remains unchanged; the UTF-8 progress tracker holds
  the current implementation evidence.

## Verdict

**PASS** — Phase 4A satisfies the scoped audit governance gate and may proceed
to Phase 4B.
