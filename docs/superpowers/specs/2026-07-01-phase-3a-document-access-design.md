# Phase 3A Authenticated Document Access Design

**Status:** Proposed for user review
**Date:** 2026-07-01
**Source:** `SPEC.MD` M4/M8/M9 and
`audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md`

## Goal

Ensure an uploaded document can only be downloaded by an authenticated user
who has `document.download` for that document's knowledge space, and make every
successful or denied attempt reconstructable from the audit log.

## Current Gap

- `DocumentSerializer` exposes the storage-backed `file` URL.
- `/media/` middleware verifies JWT identity but cannot determine whether the
  authenticated user may download the requested document.
- There is no document-bound download API and no `document_download` audit
  action.
- A member or guest may have `document.view` without `document.download`; the
  delivery layer must preserve that distinction.

## Approaches Considered

### A. Document-bound API endpoint â€?recommended

Add `GET /api/v1/documents/{id}/download/`. Resolve the `Document`, verify its
space and `document.download`, stream it with `FileResponse`, and audit the
result. Mark the serializer's `file` field write-only and return a protected
`download_url`.

Advantages: one authorization path, natural object-level audit target, simple
frontend integration, no URL expiry infrastructure. Trade-off: Django streams
the file in the pilot deployment; production can later hand off an authorized
request to nginx/object storage.

### B. Short-lived signed storage URLs

After object authorization, mint a temporary object-storage URL.

Advantages: application workers do not stream large files. Trade-off: current
local `FileSystemStorage` has no signing layer and production object-storage
details are not settled, so this introduces premature infrastructure.

### C. Object-aware media middleware

Map `/media/...` paths to `Document.file`, then apply space permissions in
middleware.

Advantages: existing URLs keep working. Trade-off: authorization and audit
logic become coupled to storage paths, ambiguous when files are versioned or
shared, and duplicated outside DRF.

## Recommended Architecture

1. `DocumentSerializer.file` remains accepted on upload but becomes
   `write_only`.
2. `DocumentSerializer.download_url` points to the document API endpoint.
3. `DocumentDownloadView`:
   - requires authentication;
   - retrieves the document without exposing cross-space existence;
   - returns `404` when the user has no effective role in the document space;
   - returns `403` when the user can see the space/document but lacks
     `document.download`;
   - returns `404` for a missing storage object;
   - streams authorized files as an attachment;
   - sets `X-Content-Type-Options: nosniff` and `Cache-Control: private,
     no-store`;
   - records successful `document_download` and denied `permission_denied`
     audit events.
4. The frontend requests the endpoint as a Blob through the existing API
   client, preserving JWT and `X-Space-Id`, then triggers a local browser
   download.
5. Raw `/media/` remains JWT-protected for compatibility but is no longer
   returned by document APIs. A later storage migration can remove that legacy
   route completely.

## Authorization Rules

| Actor | Result |
|---|---|
| Unauthenticated | `401` |
| No effective role in document space | `404` |
| Member/guest with view but no download | `403`, denied attempt audited |
| Reviewer/knowledge admin/owner | `200`, success audited |
| Org/business/platform admin in scope | `200`, success audited |
| Authorized user with mismatched active-space header | `404` |

## Error Handling

- Missing database row or unauthorized foreign-space row: generic `404`.
- Missing file in storage: generic `404`; do not disclose storage path.
- Authorization failure within a visible space: generic `403`.
- The audit record stores document ID, space ID, result, and safe filename; it
  does not store file content or token data.

## Verification

Backend tests cover unauthenticated access, cross-space concealment,
view-without-download denial, authorized streaming, missing storage, security
headers, and success/denial audit records. Frontend tests cover Blob handling
and the download action. The phase audit also runs the existing space-isolation
suite, migration dry-run, Django system check, frontend i18n check, and
production build.

## Scope Boundary

Phase 3A does not add inline preview, signed URLs, object storage, watermarking,
download quotas, or a new document viewer. Those are separate future slices.

## Self-Review

- No placeholders or unresolved implementation choices remain.
- The design preserves the existing role matrix where members can view
  metadata but cannot download source files.
- The endpoint is compatible with the current pilot stack and leaves a clean
  production handoff seam.
