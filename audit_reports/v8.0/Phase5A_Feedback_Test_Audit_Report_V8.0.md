# Phase 5A Feedback Test Audit Report V8.0

Date: 2026-07-03  
Branch: `Version_8.0`  
Baseline: `Version_7.5` at `f2a1237`  
Final status: PASS

## Scope

Phase 5A implements the answer-feedback foundation for KnowPilot:

- Per-user answer feedback keyed by `(user, message)`.
- Feedback types: `helpful`, `unhelpful`, `incorrect`, `outdated`, `missing_source`.
- Optional comment, suggested source, explicit review flag, review status fields, reviewer/resolution metadata, safe review snapshot, and `updated_at`.
- Legacy thumbs feedback migration to the new type model.
- `ModelInvocation.question_message` linkage for success, failure, timeout, and cancelled invocations created from chat streaming.
- Feedback APIs:
  - `GET /api/v1/chat/messages/{message_id}/feedback/`
  - `POST /api/v1/chat/messages/{message_id}/feedback/` (legacy-compatible upsert)
  - `PUT /api/v1/chat/messages/{message_id}/feedback/`
  - `DELETE /api/v1/chat/messages/{message_id}/feedback/` (soft withdraw)
- MessageBubble feedback controls with bilingual labels, keyboard-friendly native controls, and ARIA labels.
- Scoped audit actions: `feedback_submit`, `feedback_update`, and `feedback_withdraw`.

## Implementation Evidence

Changed backend areas:

- `backend/apps/chat/models.py`
- `backend/apps/chat/serializers.py`
- `backend/apps/chat/views.py`
- `backend/apps/chat/migrations/0005_alter_feedback_unique_together_and_more.py`
- `backend/apps/chat/test_phase5a_feedback.py`
- `backend/apps/audit/models.py`
- `backend/apps/audit/migrations/0011_alter_auditlog_action.py`

Changed frontend areas:

- `frontend/src/api/chat.ts`
- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/styles/chat.css`
- `frontend/src/i18n/locales/en/chat.json`
- `frontend/src/i18n/locales/zh/chat.json`

## Migration Evidence

Migration `chat.0005`:

- Removes legacy unique constraint on `message`.
- Adds `user`, `feedback_type`, `suggested_source`, `flag_for_review`, status/reviewer/resolution fields, `review_context`, and `updated_at`.
- Backfills legacy feedback:
  - rating `2` -> `helpful`
  - rating `1` + reason `outdated` -> `outdated`
  - rating `1` + reason `inaccurate` -> `incorrect`
  - other rating `1` -> `unhelpful`
  - `user` from the feedback message's owning chat session.
- Applies the new `(user, message)` uniqueness rule.
- Adds `ModelInvocation.question_message`.

Migration `audit.0011`:

- Adds `feedback_submit`, `feedback_update`, and `feedback_withdraw` action choices.

Migration dry-run result: PASS, no pending model changes.

## Requirement Traceability

| Requirement | Evidence |
| --- | --- |
| Per-user idempotent feedback upsert | `Feedback.objects.update_or_create(message=..., user=...)`; tested by duplicate PUT creating one row |
| Assistant-only feedback | API rejects non-assistant messages with 400; tested |
| Owner-only feedback | API scopes message lookup to `session__user=request.user`; cross-user message returns 404; tested |
| Soft withdrawal | DELETE sets `status=withdrawn`; tested |
| Safe review snapshot | Captures question, answer, citations, retrieval count, model, timestamp; tested for question/answer/retrieval count |
| Audit actions without sensitive comment content | `feedback_submit/update/withdraw` created with safe metadata only; tested comment absence in audit details |
| Legacy POST compatibility | `FeedbackSerializer` maps legacy `rating/reason` to new `feedback_type` |
| Model invocation question link | `question_message` field added and set by streaming telemetry; tested at model level |
| Frontend controls and i18n | MessageBubble controls, API methods, English/Chinese keys, i18n check PASS |
| No transient/truncated message feedback | UI only enables feedback for non-streaming persisted UUID messages |

## Negative Tests

Targeted Phase 5A tests verify:

- PUT was initially unsupported and now performs idempotent upsert.
- Non-assistant messages are rejected.
- Cross-user assistant messages are concealed.
- DELETE withdraws rather than deleting.
- Current user does not see another user's feedback on the same message.
- `ModelInvocation.question_message` is available for reliable question linkage.

## Command Results

```text
backend\venv\Scripts\python.exe backend\manage.py test apps.chat.test_phase5a_feedback --settings=config.settings.local_test -v 1
Result: PASS, 5 tests
```

```text
backend\venv\Scripts\python.exe backend\manage.py test apps --settings=config.settings.local_test -v 1
Result: PASS, 131 tests
```

```text
backend\venv\Scripts\python.exe backend\manage.py check --settings=config.settings.local_test
Result: PASS with known allauth deprecation warnings
```

```text
backend\venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run --settings=config.settings.local_test
Result: PASS, no changes detected
```

```text
npm --prefix frontend run test
Result: PASS, 49 tests
```

```text
npm --prefix frontend run check:i18n
Result: PASS
```

```text
npm --prefix frontend run typecheck
Result: PASS
```

```text
npm --prefix frontend run build
Result: PASS
```

## Warnings

- Django check continues to report three pre-existing allauth deprecation warnings:
  - `ACCOUNT_AUTHENTICATION_METHOD`
  - `ACCOUNT_EMAIL_REQUIRED`
  - `ACCOUNT_USERNAME_REQUIRED`
- Vite production build continues to report pre-existing chunk-size warnings and an i18n dynamic/static import chunking advisory.

## Residual Risks

- Phase 5A only queues review by setting `status=pending_review`; full review workflow, reviewer assignment, immutable review events, and knowledge-gap tickets are Phase 5B.
- The frontend uses native form controls for accessibility; richer validation and admin-side review ergonomics are intentionally deferred to Phase 5B.
- Existing chunk-size warnings are outside Phase 5A scope and remain candidates for later production hardening.

## Audit Conclusion

Phase 5A / V8.0 passes targeted tests, full backend regression, frontend regression, i18n, typecheck, build, Django system check, and migration consistency. Proceed to Phase 5B / V8.1 only after committing this phase.
