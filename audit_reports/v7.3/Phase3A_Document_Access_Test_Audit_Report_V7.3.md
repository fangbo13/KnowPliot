# KnowPilot Phase 3A Document Access Test Audit Report V7.3

**Date:** 2026-07-01
**Branch:** `Verision_7.3`
**Scope:** Authenticated, object-authorized, audited document delivery
**Result:** PASS
**Next-phase decision:** GO for Phase 3B file-validation hardening

## 1. Requirements Audited

| Requirement | Result | Evidence |
|---|---|---|
| Unauthenticated document download is rejected | PASS | API regression returns `401` |
| Space/object authorization is enforced server-side | PASS | `document.download` checked against the document's space |
| Cross-space existence is concealed | PASS | Outsider and active-space mismatch return `404` |
| View permission does not imply download permission | PASS | Member receives `403`; reviewer receives `200` |
| Raw storage URL is not exposed by document APIs | PASS | `file` is write-only; responses expose protected `download_url` |
| Missing storage object is handled safely | PASS | Generic `404` without filesystem path |
| Successful and denied access is auditable | PASS | `document_download` and `permission_denied` records verified |
| Download response is browser-safe | PASS | Attachment disposition, `nosniff`, and `private, no-store` |
| Frontend uses authenticated API delivery | PASS | Axios Blob request uses existing JWT/space interceptors |
| Temporary browser download URL is released | PASS | `URL.revokeObjectURL` executes in `finally` |

## 2. Test-Driven Development Evidence

### Backend RED

Command:

```powershell
python manage.py test apps.knowledge.tests_phase3_governance `
  --settings=config.settings.local_test -v 2
```

Initial result: 8 tests discovered; 5 failed for the expected reasons:

- protected route returned `404` because it did not exist;
- unauthenticated request returned route-level `404` instead of `401`;
- member denial returned `404` instead of `403`;
- successful delivery/audit did not exist;
- document JSON still exposed `file` and lacked `download_url`.

The three concealment/missing-route cases returned `404` before implementation
and remained as regression guards.

### Frontend RED

Command:

```powershell
npm test -- src/api/__tests__/documents.download.test.ts
```

Initial result: 3/3 tests failed because `downloadDocument` and
`extractDownloadFilename` did not exist.

## 3. Final Backend Verification

Commands:

```powershell
python manage.py shell --settings=config.settings.local_test -c `
  "from django.urls import reverse,resolve; ..."

python manage.py test `
  apps.knowledge.tests_phase3_governance `
  apps.spaces `
  apps.users.tests_v7_identity `
  apps.scenario_templates.tests_phase2a `
  --settings=config.settings.local_test -v 1

python manage.py check --settings=config.settings.local_test
python manage.py makemigrations --check --dry-run `
  --settings=config.settings.local_test
```

Results:

- Route reverse/resolve: `/api/v1/documents/{uuid}/download/` resolves to
  `document-download`.
- Backend regression: **68 tests passed, 0 failed**.
- Django system check: 0 errors.
- Migration state: no ungenerated model changes.
- Known warnings: three existing django-allauth setting deprecations.

The 68-test gate includes:

- 8 Phase 3A document-access tests;
- 19 multi-space isolation/RBAC tests;
- V7 identity/governance regression tests;
- Phase 2A/2B template-center regression tests.

## 4. Final Frontend Verification

Commands:

```powershell
npm test
npm run check:i18n
npm run build
```

Results:

- Vitest: **3 files, 39 tests passed, 0 failed**.
- i18n: 51 source files checked; all keys present.
- TypeScript/Vite production build: exit code 0; 3,594 modules transformed.
- Known advisories:
  - mixed static/dynamic import of `src/i18n/index.ts`;
  - chunks above Vite's 500 kB advisory threshold.

## 5. Security and Code Review

No blocking findings were identified.

- ORM UUID lookup is used; no raw SQL or injection surface was introduced.
- The user-supplied active-space value is compared, not used in a filesystem
  path.
- The file is opened only through the authorized `Document.file` storage
  object.
- Cross-space and non-member access returns a generic `404`.
- Same-space users lacking `document.download` receive `403` and an audit
  record.
- Filenames are reduced to basenames on both server and client.
- React does not inject downloaded metadata as HTML.
- `select_related("space")` avoids an extra document-space lookup.
- `git diff --check` reports no whitespace errors in the scoped changes.

## 6. Changed Files

Backend:

- `backend/apps/knowledge/views.py`
- `backend/apps/knowledge/urls.py`
- `backend/apps/knowledge/serializers.py`
- `backend/apps/knowledge/tests_phase3_governance.py`
- `backend/apps/audit/models.py`
- `backend/apps/audit/migrations/0008_alter_auditlog_action.py`

Frontend:

- `frontend/src/api/documents.ts`
- `frontend/src/api/__tests__/documents.download.test.ts`
- `frontend/src/pages/admin/KnowledgeBasePage.tsx`
- `frontend/src/i18n/locales/en/common.json`
- `frontend/src/i18n/locales/zh/common.json`

## 7. Residual Risks

1. Django `FileResponse` is appropriate for the pilot deployment; production
   object storage should later support an authorization-checked internal
   redirect or short-lived URL to avoid tying up application workers.
2. Production reverse proxies must not add a public `/media/` alias. Django does
   not route raw media, and document APIs no longer emit raw media URLs.
3. The knowledge table shows a download action and relies on the backend for
   final permission enforcement. A later frontend permission-aware UX pass can
   hide the button from members who lack `document.download`.
4. Existing Vite chunk-size and django-allauth deprecation warnings remain
   outside Phase 3A.

## 8. Audit Decision

Phase 3A satisfies the approved design and SPEC M4/M8/M9 access-governance
requirements in scope. The audit gate passes. Phase 3B may begin.
