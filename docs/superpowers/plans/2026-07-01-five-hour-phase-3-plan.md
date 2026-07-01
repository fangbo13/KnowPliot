# Phase 3 Knowledge Governance Five-Hour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Begin SPEC Phase 3 by closing document delivery authorization and
auditing file-validation gaps within a five-hour engineering window.

**Architecture:** Add one object-authorized document download endpoint and stop
serializing raw media URLs. Then regression-audit the existing upload
validators and close only confirmed gaps. Each major phase is blocked by a
fresh test audit report in a versioned `audit_reports/` folder.

**Tech Stack:** Django 5/DRF, SimpleJWT, SQLite test settings, React 18,
TypeScript, Axios, Ant Design, Vitest/Vite.

---

## File Map

### Phase 3A

- Create `backend/apps/knowledge/tests_phase3_governance.py`: document delivery
  authorization, streaming, and audit regression tests.
- Modify `backend/apps/knowledge/views.py`: protected download view.
- Modify `backend/apps/knowledge/urls.py`: document download route.
- Modify `backend/apps/knowledge/serializers.py`: write-only upload field and
  protected download URL.
- Modify `backend/apps/audit/models.py`: `document_download` action choice.
- Create `backend/apps/audit/migrations/0003_*.py`: action-choice state
  migration if `makemigrations` detects one.
- Modify `frontend/src/api/documents.ts`: Blob download client.
- Modify `frontend/src/pages/admin/KnowledgeBasePage.tsx`: download action and
  user feedback.
- Modify i18n locale files located by `rg "reindex_success" frontend/src`: new
  accessible labels and download messages.
- Create `audit_reports/v7.3/Phase3A_Document_Access_Test_Audit_Report_V7.3.md`:
  commands, results, findings, and disposition.

### Phase 3B

- Modify `backend/apps/core/validators.py`: only gaps proven by tests, including
  declared type/extension consistency and safe text detection.
- Modify `backend/apps/knowledge/serializers.py`: consistent manual-upload
  validation.
- Modify `backend/apps/knowledge/batch.py`: parity between manual and batch
  allowed types.
- Extend `backend/apps/knowledge/tests_phase3_governance.py`: spoofing,
  extension mismatch, text-binary, and valid-format tests.
- Modify `frontend/src/pages/admin/KnowledgeBasePage.tsx` and
  `frontend/src/api/documents.ts`: send the inferred `file_type`, title, and
  file size; align accept-list with backend policy.
- Create `audit_reports/v7.3/Phase3B_File_Validation_Test_Audit_Report_V7.3.md`.

### Tracking

- Modify `SPEC.MD` and
  `audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md` only after the
  corresponding audit gate passes.
- Update `task_plan.md`, `findings.md`, and `progress.md` after each phase.

## Five-Hour Schedule

| Elapsed | Major phase | Exit gate |
|---|---|---|
| 00:00â€?0:40 | Baseline, design, detailed plan, long-term roadmap | Plan audit written; no unresolved scope ambiguity |
| 00:40â€?2:25 | Phase 3A TDD: protected download backend | New tests red then green; existing space tests green |
| 02:25â€?3:05 | Phase 3A frontend integration and full audit | Backend checks + frontend checks/build green; V7.3 report saved |
| 03:05â€?4:15 | Phase 3B validation gap tests and minimal fixes | Every change backed by a witnessed failing test |
| 04:15â€?4:50 | Phase 3B regression and audit | V7.3 report saved; no Phase 3A regression |
| 04:50â€?5:00 | Progress/SPEC reconciliation | Tracker matches evidence; next phase clearly queued |

If Phase 3A's audit fails, the remaining time stays on Phase 3A. Phase 3B does
not start until the V7.3 report records a pass.

### Task 1: Establish and record the baseline

- [ ] **Step 1: Run the current focused backend baseline**

Run:

```powershell
cd backend
python manage.py test apps.spaces --settings=config.settings.local_test
```

Expected: existing multi-space isolation suite passes.

- [ ] **Step 2: Run framework and migration checks**

Run:

```powershell
python manage.py check --settings=config.settings.local_test
python manage.py makemigrations --check --dry-run --settings=config.settings.local_test
```

Expected: system check has no errors; migration command reports no changes.

- [ ] **Step 3: Run frontend baseline**

Run:

```powershell
cd ..\frontend
npm run check:i18n
npm run build
```

Expected: i18n check and build exit `0`; known Vite warnings are recorded, not
silently discarded.

### Task 2: Write Phase 3A failing authorization tests

- [ ] **Step 1: Add the test module and fixtures**

Create `backend/apps/knowledge/tests_phase3_governance.py` with a space,
reviewer, member, outsider, real temporary uploaded file, and audit-log
fixtures. Use `override_settings(MEDIA_ROOT=temp_dir)` so tests never write into
the repository media folder.

- [ ] **Step 2: Express the required endpoint behavior**

Add separate tests equivalent to:

```python
def test_member_without_download_permission_gets_403(self):
    self.client.force_authenticate(self.member)
    response = self.client.get(
        f"/api/v1/documents/{self.document.id}/download/",
        HTTP_X_SPACE_ID=str(self.space.id),
    )
    self.assertEqual(response.status_code, 403)

def test_reviewer_download_streams_and_is_audited(self):
    self.client.force_authenticate(self.reviewer)
    response = self.client.get(
        f"/api/v1/documents/{self.document.id}/download/",
        HTTP_X_SPACE_ID=str(self.space.id),
    )
    self.assertEqual(response.status_code, 200)
    self.assertEqual(b"".join(response.streaming_content), self.file_bytes)
    self.assertTrue(
        AuditLog.objects.filter(
            user=self.reviewer,
            action="document_download",
            target_id=self.document.id,
        ).exists()
    )
```

Also cover unauthenticated `401`, outsider/cross-space `404`, active-space
mismatch `404`, missing storage object `404`, and response security headers.

- [ ] **Step 3: Verify RED**

Run:

```powershell
cd backend
python manage.py test apps.knowledge.tests_phase3_governance --settings=config.settings.local_test -v 2
```

Expected: endpoint tests fail with `404` because the route is not implemented;
fixture/import errors are not an acceptable RED state.

### Task 3: Implement the minimal protected download backend

- [ ] **Step 1: Add the route and view**

Implement `DocumentDownloadView` in `backend/apps/knowledge/views.py` and route
it as:

```python
path("<uuid:pk>/download/", DocumentDownloadView.as_view(), name="document-download")
```

The view must use `DOCUMENT_DOWNLOAD`, distinguish `404` concealment from `403`
within a visible space, verify the active-space header when present, stream via
`FileResponse`, and never include the storage path in an error.

- [ ] **Step 2: Remove raw media URLs from read responses**

Make `file` write-only and add:

```python
download_url = serializers.HyperlinkedIdentityField(
    view_name="document-download",
    read_only=True,
)
```

Include `download_url` in the serializer fields. Verify list/detail JSON has no
`file` key.

- [ ] **Step 3: Add audit action state**

Add `("document_download", "Document Download")` to `AuditLog.ACTION_CHOICES`.
Run:

```powershell
python manage.py makemigrations audit --settings=config.settings.local_test
```

Review the generated migration to ensure it only changes the action choice.

- [ ] **Step 4: Verify GREEN and regressions**

Run:

```powershell
python manage.py test apps.knowledge.tests_phase3_governance apps.spaces --settings=config.settings.local_test -v 2
```

Expected: all new and existing focused tests pass.

### Task 4: Integrate the protected frontend download

- [ ] **Step 1: Add Blob client behavior**

Add `downloadDocument(id)` to `frontend/src/api/documents.ts`, using
`responseType: 'blob'` and deriving a safe filename from `Content-Disposition`
with the document title as fallback.

- [ ] **Step 2: Add the table action**

Add an accessible download button to `KnowledgeBasePage.tsx`. It calls the API,
creates an object URL, clicks a temporary anchor, and always revokes the object
URL in `finally`.

- [ ] **Step 3: Add localized labels**

Add English and Chinese keys for download, success, and failure to the existing
locale modules found by the repository search.

- [ ] **Step 4: Verify frontend**

Run:

```powershell
cd frontend
npm run check:i18n
npm test
npm run build
```

Expected: all available tests pass, locale keys match, production build exits
`0`.

### Task 5: Audit Phase 3A before advancing

- [ ] **Step 1: Run the full Phase 3A gate**

Run the focused backend suite, Django check, migration dry-run, frontend tests,
i18n check, and production build fresh.

- [ ] **Step 2: Inspect the implementation**

Confirm:

- document JSON never exposes raw media paths;
- every successful download has a `document_download` log;
- denied same-space attempts have `permission_denied` logs;
- cross-space document existence is concealed;
- output headers prevent content sniffing and shared caching;
- no unrelated dirty-worktree files changed.

- [ ] **Step 3: Save the audit**

Write
`audit_reports/v7.3/Phase3A_Document_Access_Test_Audit_Report_V7.3.md` with
scope, exact commands, pass/fail counts, known warnings, security inspection,
changed files, residual risks, and a clear GO/NO-GO for Phase 3B.

### Task 6: Audit existing file validation with failing tests

- [ ] **Step 1: Capture the current policy mismatch**

Add tests proving the backend model, validator, batch importer, and frontend
accept-list disagree today. The intended current-version policy is PDF, DOCX,
HTML, TXT, and Markdown; spreadsheet formats remain future scope per SPEC M4.

- [ ] **Step 2: Add security cases**

Add independent tests for:

- executable/binary bytes renamed `.txt`;
- PDF bytes declared as DOCX;
- `.pdf` filename declared as TXT;
- unsupported spreadsheet upload;
- valid UTF-8 TXT, PDF, DOCX, HTML, and Markdown.

- [ ] **Step 3: Verify RED**

Run the exact Phase 3 governance test module and confirm each gap test fails for
the intended current behavior, not fixture or dependency errors.

### Task 7: Apply minimal validation consistency fixes

- [ ] **Step 1: Centralize current allowed types**

Define one backend policy used by manual and batch validation. Validate declared
type against the filename extension, then validate content signature or safe
text encoding. Reject NUL-containing and undecodable text payloads.

- [ ] **Step 2: Align manual upload payload**

Update the frontend upload path to send `title`, inferred `file_type`, and
`file_size`; align `accept` with the backend's current-version policy.

- [ ] **Step 3: Verify GREEN**

Run the Phase 3 governance tests, existing space tests, batch tests discovered
with `rg`, i18n check, frontend tests, and build.

### Task 8: Audit Phase 3B and reconcile trackers

- [ ] **Step 1: Save the V7.3 audit report**

Write
`audit_reports/v7.3/Phase3B_File_Validation_Test_Audit_Report_V7.3.md` with the
same evidence structure as V7.3.

- [ ] **Step 2: Update source-of-truth progress**

Only if the audit passes, update `SPEC.MD` and
`audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md` to mark Phase 3A/3B
complete and name Phase 3C retrieval safety as next.

- [ ] **Step 3: Record session state**

Update `task_plan.md`, `findings.md`, and `progress.md` with completed phases,
test counts, audit paths, deviations, and remaining risks.

## Plan Self-Review

- SPEC coverage: Phase 3 authenticated access and validation are mapped; later
  retrieval/state work is intentionally in the long-term roadmap.
- Placeholder scan: no unresolved planning markers are present.
- Type consistency: the plan consistently uses `DOCUMENT_DOWNLOAD`,
  `document_download`, and `/api/v1/documents/{id}/download/`.
- Safety: every implementation phase has a test-first RED/GREEN sequence and a
  report gate before the next phase.
