# Phase 3B File Validation Consistency Design

**Status:** Proposed for user review
**Date:** 2026-07-01
**Source:** `SPEC.MD` M4 and the V7.3 Phase 3A audit

## Goal

Create one enforceable current-version document policy for single upload, batch
upload, persistence, ingestion, and the frontend. Reject mislabeled, unsupported,
binary-as-text, and structurally invalid files before a `Document` or ingestion
job is created.

## Current Gaps

- The model supports PDF, DOCX, HTML, and TXT.
- Core MIME validation also lists legacy DOC, CSV, XLSX, and PPTX, but omits
  HTML and Markdown.
- Batch mapping accepts more formats than the model/parser and treats an unknown
  extension as `None`; the validation branch is skipped and the batch view
  persists it as TXT.
- The frontend accepts DOC/CSV/XLSX/PPTX but not HTML/Markdown.
- The upload widget posts only the file, while the serializer requires title,
  declared type, and client-supplied size.
- Plain-text validation accepts any unrecognized byte stream as TXT/CSV.
- The parser's final fallback decodes arbitrary bytes with `errors="ignore"`,
  which is not evidence of safe spreadsheet or legacy Office support.

## Current-Version Policy

The accepted formats are exactly those required by SPEC M4:

| Canonical type | Extensions | Content rule |
|---|---|---|
| PDF | `.pdf` | PDF signature/MIME |
| DOCX | `.docx` | DOCX ZIP package/MIME |
| HTML | `.html`, `.htm` | Valid UTF-8 text, no NUL bytes |
| TXT | `.txt` | Valid UTF-8 text, no NUL bytes |
| Markdown | `.md`, `.markdown` | Valid UTF-8 text, no NUL bytes |

DOC, CSV, XLSX, and PPTX are not supported in this version. Spreadsheet support
remains future scope as stated by SPEC M4.

## Approaches Considered

### A. Central server-derived policy â€?recommended

Create one backend policy that maps filename extensions to canonical types and
validates content. Single and batch upload both call it. The server derives and
stores `file_type` and actual `file_size`; a supplied legacy `file_type` is
accepted only when it matches the derived type. Title may default safely from
the filename.

Advantages: no client trust boundary for size/type, one policy, repaired upload
widget, backward-compatible validation for clients that still send
`file_type`. Trade-off: serializers gain cross-field validation.

### B. Keep client-declared metadata mandatory

Centralize validators but continue requiring `file_type`, `file_size`, and
title from every client.

Advantages: smallest serializer signature change. Trade-off: duplicated client
logic remains a correctness and security boundary, and the current UI stays
fragile unless every caller is repaired.

### C. Expand support to every currently listed format

Add DOC/CSV/XLSX/PPTX to models and build format-specific parsing.

Advantages: broader file coverage. Trade-off: materially expands parser,
security, and testing scope beyond the SPEC; XLSX is explicitly future work.

## Recommended Architecture

1. Add a single policy module in `apps.knowledge` containing:
   - canonical types and extensions;
   - extension-to-type derivation;
   - binary signature/MIME checks;
   - safe UTF-8 text checks;
   - a bytes/file-object interface shared by manual and batch upload.
2. `DocumentSerializer.validate()`:
   - requires a supported filename extension;
   - validates content using the central policy;
   - rejects a supplied `file_type` that differs from the derived type;
   - overwrites `file_size` with the actual uploaded size;
   - supplies a sanitized filename-derived title when absent.
3. Batch validation:
   - rejects unknown/unsupported extensions explicitly;
   - delegates content validation to the same policy;
   - never falls back to TXT for an unknown extension.
4. Model choices add Markdown and remove no persisted historical value through
   a destructive data migration. New writes are restricted by the policy.
5. Frontend:
   - accept-list matches the five canonical formats;
   - upload goes through `documentApi`/Axios so JWT and `X-Space-Id` are present;
   - only the file and optional category/title are sent; type and size are
     authoritative on the server.

## Validation and Error Contract

- Unsupported extension: `400`, â€œUnsupported file extensionâ€?
- Declared/derived type mismatch: `400`, â€œDeclared file type does not matchâ€?
- Binary signature mismatch: `400`, existing spoofing-safe message.
- Invalid text encoding or NUL bytes: `400`, â€œFile is not valid UTF-8 textâ€?
- Too small/large: existing size-policy message.
- Batch result includes a per-file safe rejection reason and never creates a
  `Document` for rejected content.

Errors do not expose filesystem paths or raw file content.

## Test Strategy

Backend RED/GREEN tests cover:

- valid PDF, DOCX, HTML, TXT, and Markdown;
- executable/binary bytes renamed TXT;
- PDF content named DOCX;
- unsupported DOC/CSV/XLSX/PPTX;
- supplied type mismatching filename;
- actual size overriding a false client value;
- missing title defaulting from a sanitized filename;
- batch unknown-extension rejection;
- manual/batch parity for every canonical type.

Frontend RED/GREEN tests cover:

- the API upload uses multipart data and relies on Axios interceptors;
- accepted extensions match backend policy;
- unsupported spreadsheet/legacy Office files are rejected before upload.

The V7.3 audit gate runs Phase 3A/3B, space, V7, template, frontend, i18n,
system-check, migration, and build regressions.

## Scope Boundary

This phase does not add antivirus scanning, content-disarm/reconstruction,
spreadsheet parsing, legacy `.doc`, OCR, password-protected document support,
or object storage. These require separate designs.

## Self-Review

- The policy matches SPEC M4 rather than historical UI drift.
- Unknown batch extensions can no longer bypass validation.
- The server, not the browser, owns authoritative type and size.
- No placeholders or unresolved implementation choices remain.
