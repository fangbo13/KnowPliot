# Findings

## Source Documents

- Reviewed `SPEC.MD` (V6.1 plus V7/Phase 2 extensions) and
  `audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md` dated 2026-07-01.
- Both sources identify Phase 3 Knowledge Governance Hardening as the next stage.
- The recommended Phase 3 order is authenticated document access, file
  validation, retrieval safety, explicit document states, then regression/UI
  verification.

## Repository State

- The repository already contains historical, versioned audit reports through v6.x and current v7/Phase 2A reports.
- Existing unrelated modified/untracked files are present and must remain untouched.
- Existing changes include `backend/db.sqlite3`, `frontend/tsconfig.tsbuildinfo`,
  screenshots/video assets, `.claude/`, and bundled skill content.
- The current backend already has JWT-only `/media/` middleware and removes
  Django's DEBUG media route, but it does not perform document/space
  object-level authorization.
- `DocumentSerializer` already performs size and magic-number validation through
  `apps.core.validators`; Phase 3 planning must verify coverage and close gaps
  rather than duplicate earlier V4.1 work.
- Document API serializers currently expose the raw `FileField` URL. There is no
  dedicated audited download/preview endpoint in `apps.knowledge.urls`.
- Document list/detail operations use `SpaceDocumentPermission`, but the media
  middleware only establishes identity, not `document.download` permission.

## Planning Decisions

- The execution plan will use explicit phase-level acceptance criteria, test commands, audit gates, and versioned report paths.
- Today's first implementation slice will be Phase 3A: replace raw media
  exposure with a document-bound, space-authorized, audited download endpoint.
- Phase 3B file validation will be treated as a gap-analysis/hardening slice
  because validation code already exists.
- Phase 3A is now implemented: document APIs no longer emit raw media URLs, and
  the protected download endpoint enforces `document.download`, active-space
  matching, cross-space concealment, and audit logging.
- The Phase 3A audit passed with 68 backend and 39 frontend tests. Phase 3B is
  authorized to start.
- Phase 3B's confirmed starting inconsistency is that model choices, validator
  MIME mappings, batch types, and the frontend accept list do not currently
  express one shared current-version file policy.
- Detailed Phase 3B gap analysis:
  - `Document.FILE_TYPE_CHOICES` supports PDF, DOCX, HTML, and TXT.
  - `ALLOWED_MIME_TYPES` also contains DOC, CSV, XLSX, and PPTX but omits HTML
    and Markdown.
  - Batch extension mapping accepts DOC/CSV/XLSX/PPTX and silently lets unknown
    extensions through with `file_type="txt"` because validation is skipped
    when the extension mapping returns `None`.
  - The frontend allows PDF/DOC/DOCX/TXT/CSV/XLSX/PPTX but omits HTML/Markdown.
  - The frontend Ant Upload request sends the file only; the current serializer
    requires title, declared file type, and client-provided size.
  - The ingestion parser documents PDF/DOCX/HTML/TXT support and otherwise
    falls back to UTF-8 text with `errors="ignore"`, which is unsafe evidence
    for broad binary Office/spreadsheet support.
- SPEC M4's current-version policy is PDF, DOCX, HTML, TXT, and Markdown;
  spreadsheets are explicitly future scope. Phase 3B should converge on that
  narrow policy rather than expand parser scope.
- Phase 3B is implemented and audited. Manual/batch validation now shares the
  five-format policy, server metadata is authoritative, unsafe binary text and
  unsupported extensions are rejected, and the upload UI uses the authenticated
  space-aware API client.
- Phase 3B testing also exposed and fixed a valid-DOCX batch rejection and a
  PATCH path that allowed file metadata changes without file replacement.
- The V7.3 audit passed with 85 backend and 42 frontend tests. Phase 3C
  retrieval safety is next.
