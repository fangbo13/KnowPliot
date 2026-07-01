# KnowPilot Phase 3B File Validation Test Audit Report V7.3

**Date:** 2026-07-01
**Branch:** `Verision_7.3`
**Scope:** Single/batch upload policy convergence and frontend upload repair
**Result:** PASS
**Next-phase decision:** GO for Phase 3C retrieval safety

## 1. Requirements Audited

| Requirement | Result | Evidence |
|---|---|---|
| One current-version format policy | PASS | PDF, DOCX, HTML/HTM, TXT, Markdown |
| Server derives canonical type | PASS | Filename extension mapped and content verified |
| Server derives actual file size | PASS | False client size is overwritten |
| Missing title is safe | PASS | Sanitized filename stem becomes title |
| Binary-as-text is rejected | PASS | NUL and invalid UTF-8 cases rejected |
| Signature/extension mismatch is rejected | PASS | PDF-as-DOCX and declared-type mismatch tests |
| Unsupported formats are rejected | PASS | DOC, CSV, XLSX, PPTX, EXE rejected |
| Batch unknown extension cannot become TXT | PASS | Regression reproduces and closes historical bypass |
| Manual/batch policy parity | PASS | All five canonical types accepted through batch validation |
| DOCX is not mistaken for nested ZIP | PASS | Dedicated RED/GREEN regression |
| Metadata cannot mutate without file replacement | PASS | PATCH type/size regression |
| Real upload endpoint works with file only | PASS | Knowledge-admin integration test |
| Frontend policy matches backend | PASS | Exact extension-list test |
| Upload carries JWT and active space | PASS | Upload uses shared Axios client/interceptors |

## 2. Current-Version Policy

| Canonical type | Accepted extensions | Validation |
|---|---|---|
| PDF | `.pdf` | `%PDF-` signature |
| DOCX | `.docx` | Valid ZIP package with DOCX content types and `word/document.xml` |
| HTML | `.html`, `.htm` | UTF-8 text with no NUL bytes |
| TXT | `.txt` | UTF-8 text with no NUL bytes |
| Markdown | `.md`, `.markdown` | UTF-8 text with no NUL bytes |

Legacy DOC, CSV, XLSX, and PPTX remain outside current-version scope.

## 3. Test-Driven Development Evidence

### Initial backend RED

Command:

```powershell
python manage.py test `
  apps.knowledge.tests_phase3_governance.FileValidationPolicyTest `
  --settings=config.settings.local_test -v 2
```

Result: 12 tests ran with 15 expected failures. Failures demonstrated:

- title/type/size were client-required instead of derived;
- false client size was persisted;
- binary bytes were accepted as TXT;
- filename extension was not authoritative;
- unsupported extensions passed when declared as TXT;
- unknown batch extensions bypassed validation and could fall back to TXT.

### Compatibility RED

Two added tests failed because legacy single/batch validator entry points still
accepted unsafe binary text or rejected Markdown. Both now delegate to the
canonical policy.

### Review-driven RED

- A five-format batch parity test failed because DOCX was misclassified as a
  nested ZIP.
- A PATCH regression failed because `file_type` and `file_size` could change
  without replacing the file.

Both defects were fixed before final verification.

### Frontend RED

Command:

```powershell
npm test -- src/api/__tests__/documents.download.test.ts
```

Result: 3 of 6 tests failed because the canonical extension exports did not
exist and upload still appended client metadata/manual multipart headers.

## 4. Final Backend Verification

Commands:

```powershell
python -m compileall -q apps\knowledge apps\core

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

- Python compilation: PASS.
- Backend regression: **85 tests passed, 0 failed**.
- Django system check: 0 errors.
- Migration dry-run: no ungenerated changes.
- Known warnings: three existing django-allauth setting deprecations.

## 5. Final Frontend Verification

Commands:

```powershell
npm test
npm run check:i18n
npm run build
```

Results:

- Vitest: **3 files, 42 tests passed, 0 failed**.
- i18n: 51 source files checked; all keys present.
- TypeScript/Vite build: exit code 0; 3,594 modules transformed.
- Known advisories:
  - mixed static/dynamic import of `src/i18n/index.ts`;
  - chunks above Vite's 500 kB advisory threshold.
- Scoped `git diff --check`: PASS after removing one trailing blank line.

## 6. Code and Security Review

No blocking findings remain.

- File type and size are authoritative on the server.
- Unsupported filename extensions are rejected before persistence.
- Text validation rejects NUL bytes and invalid UTF-8.
- DOCX validation checks package structure rather than trusting ZIP magic alone.
- No filesystem path is assembled from client input.
- Batch and single upload call the same policy.
- Historical serializer/validator import paths delegate to the canonical
  implementation; duplicate document serializer logic was removed.
- Upload uses existing backend authentication, space permission checks, rate
  throttling, and the Axios JWT/`X-Space-Id` interceptors.
- React never injects filename/title content as raw HTML.

## 7. Changed Files

Backend:

- `backend/apps/knowledge/file_policy.py`
- `backend/apps/knowledge/serializers.py`
- `backend/apps/knowledge/batch.py`
- `backend/apps/knowledge/batch_serializers.py`
- `backend/apps/knowledge/models.py`
- `backend/apps/knowledge/migrations/0007_alter_document_file_type.py`
- `backend/apps/knowledge/tests_phase3_governance.py`
- `backend/apps/core/validators.py`

Frontend:

- `frontend/src/api/documents.ts`
- `frontend/src/api/__tests__/documents.download.test.ts`
- `frontend/src/pages/admin/KnowledgeBasePage.tsx`

## 8. Residual Risks

1. Signature/structure validation is not antivirus scanning or content-disarm
   and reconstruction.
2. DOCX decompression limits during the downstream parser should be revisited
   when password-protected documents/OCR are designed.
3. PDF validation verifies the expected signature but does not prove every
   internal object is benign; parser sandboxing remains production hardening.
4. Frontend checks are UX only; the backend remains authoritative.
5. Existing Vite and django-allauth warnings remain outside Phase 3B.

## 9. Audit Decision

Phase 3B satisfies the approved design and current SPEC M4 upload-governance
scope. The audit gate passes. Phase 3C retrieval safety may begin.
