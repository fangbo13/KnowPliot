# KnowPilot V7 Functional Smoke Report

> **Date**: 2026-07-01
> **Vite Frontend URL**: http://localhost:3000
> **Django Backend URL**: http://127.0.0.1:8000
> **Environment**: Windows local test with SQLite database

---

## 1. Test Accounts & Seeds

Seeded using `python manage.py seed_identity`:
- **Super Admin**: `admin@ey.com` / `admin123` (reset password locally for validation verification)
- **Normal User (Created during smoke run)**: e.g., `smoke_hvoh22@test.com` / `StrongPass123!` (assigned to service line `tax`, mapped to default space `tax-onboarding`)
- **Admin User (Created via generated code)**: e.g., `smoke_admin@test.com` / `StrongPass123!` (with business admin role)

---

## 2. Functional Test Checklist & Results

| Section | Process | Status | Description / Verification |
|---|---|---|---|
| **A. Login Page** | Access frontend landing URL, verify entry points | **PASS** | Validated that login UI points (Sign In, Register, Admin tabs) are available. Static i18n switching is safe. |
| **B. Regular User** | Register without `service_line` | **PASS** | API returned `400 Bad Request` with field error as designed. |
| **B. Regular User** | Register with `service_line=tax` | **PASS** | API returned `201 Created` with JWT access token. User object returned. |
| **B. Regular User** | Access space view and profile me endpoint | **PASS** | Authorized user can retrieve profile info, sees only their assigned spaces (e.g. `tax-onboarding`). |
| **C. Admin User** | Authenticate via token exchange | **PASS** | Super admin credentials validated. Token returned correctly with `is_superuser=True`. |
| **D. Admin Codes** | Generate super_admin code | **PASS** | Designs strictly prevent super_admin code generation. Attempt returned `400 Bad Request`. |
| **D. Admin Codes** | Generate business_admin code | **PASS** | Org admin/superuser can generate code, plaintext code returned exactly once. |
| **D. Admin Codes** | Register via business_admin code | **PASS** | User registered successfully using code, granted `is_business_admin=True` role. |
| **E. Announcements** | Publish public announcement (audience=all) | **PASS** | Successfully published broadcast announcements visible to all users. |
| **E. Announcements** | Scoped announcement without target | **PASS** | Scoping to `org`/`business_line`/`role` requires `audience_ref`. Omission returns `400 Bad Request`. |
| **F. Notifications** | Fetch targeted notifications feed | **PASS** | New user retrieves targeted welcome notification. Feed successfully accessed. |
| **F. Notifications** | Fetch unread count & dismiss | **PASS** | Dismiss all notifications updates count to `0` successfully. |
| **G. Space Members**| Space membership / email invite validation | **PASS** | Basic logic checks pass. Offline invites handled via `SpaceEmailInvite` records. |

---

## 3. Issues Found & Resolutions

1. **Issue: Admin Login Credentials mismatched**
   - *Detail*: Default seed credentials list `admin@test.ey.com` but database contained `admin@ey.com`.
   - *Fix*: Reset `admin@ey.com`'s password to `admin123` via Django shell, updated test script. Live smoke API test now executes perfectly.

---

## 4. Verification Check

All regression validation checks are successfully executed and green:
- **`npm run check:i18n`**: ✅ Passed. 0 missing keys.
- **`npm run build`**: ✅ Passed (3592 modules, 16.19s).
- **Backend Tests (`tests_v7_identity` + `tests_v7_smoke`)**: ✅ Passed.
  ```
  Ran 20 tests in 18.278s
  OK
  ```
