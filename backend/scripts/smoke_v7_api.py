"""V7 Functional Smoke Test — API-level.

Exercises the real running server at http://127.0.0.1:8000 to verify
that the V7 Identity / Admin Console / Notification flows work end-to-end
against a live SQLite database (seeded by seed_identity).

Usage:
    D:\\Github\\Onborading-AI\\.venv\\Scripts\\python.exe scripts/smoke_v7_api.py
"""
import io
import json
import sys
import urllib.request
import urllib.error
import urllib.parse
import random
import string

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE = "http://127.0.0.1:8000"
RESULTS = []

def rand_email():
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"smoke_{suffix}@test.com"

def api(method, path, data=None, token=None):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = str(e)
        return e.code, body

def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((name, status, detail))
    icon = "[OK]" if passed else "[FAIL]"
    print(f"  {icon} {name}: {status}" + (f" -- {detail}" if detail else ""))

print("=" * 60)
print("V7 API Smoke Test")
print("=" * 60)

# ── A. Login page API health ─────────────────────────────────────
print("\n[A] API Health")
status, _ = api("GET", "/api/v1/auth/me/")
# Unauthenticated should return 401
record("A1: Unauthenticated /auth/me/ → 401", status == 401, f"got {status}")

# ── B. Regular Registration ──────────────────────────────────────
print("\n[B] Regular Registration")

# B1: Missing service_line → 400
status, body = api("POST", "/api/v1/auth/register/", {"email": rand_email(), "password": "StrongPass123!"})
record("B1: Register without service_line → 400", status == 400, f"got {status}")

# B2: With service_line → 201
reg_email = rand_email()
status, body = api("POST", "/api/v1/auth/register/", {
    "email": reg_email, "password": "StrongPass123!", "service_line": "tax"
})
record("B2: Register with service_line → 201", status == 201, f"got {status}")
user_token = body.get("access", "") if status == 201 else ""
user_data = body.get("user", {}) if status == 201 else {}

# B3: Token and identity returned
record("B3: Access token returned", bool(user_token), f"token={'yes' if user_token else 'no'}")
record("B4: User identity has email", user_data.get("email") == reg_email, f"email={user_data.get('email')}")
record("B5: User is not super_admin", user_data.get("is_super_admin") == False, f"is_super_admin={user_data.get('is_super_admin')}")

# B6: Authenticated /auth/me/ works
if user_token:
    status, me = api("GET", "/api/v1/auth/me/", token=user_token)
    record("B6: /auth/me/ with token → 200", status == 200, f"got {status}")
else:
    record("B6: /auth/me/ with token → 200", False, "no token")

# ── C. Admin Login ───────────────────────────────────────────────
print("\n[C] Admin Login")
status, body = api("POST", "/api/v1/auth/token/", {"email": "admin@ey.com", "password": "admin123"})
record("C1: Admin login → 200", status == 200, f"got {status}")
admin_token = body.get("access", "") if status == 200 else ""
admin_user = body.get("user", {}) if status == 200 else {}
record("C2: Admin has access token", bool(admin_token), "")
is_super = admin_user.get("is_super_admin", False)
record("C3: Admin is super_admin", is_super == True, f"is_super_admin={is_super}")

# ── D. Admin Registration Codes ─────────────────────────────────
print("\n[D] Admin Registration Codes")

# D1: super_admin code → 400
if admin_token:
    # Get org id
    status, orgs_body = api("GET", "/api/v1/admin/organizations/", token=admin_token)
    org_id = None
    if status == 200 and isinstance(orgs_body, list) and len(orgs_body) > 0:
        org_id = orgs_body[0].get("id")
    elif status == 200 and isinstance(orgs_body, dict):
        results = orgs_body.get("results", [])
        if results:
            org_id = results[0].get("id")
    
    # Get business line id
    status, bls_body = api("GET", "/api/v1/admin/business-lines/", token=admin_token)
    bl_id = None
    if status == 200 and isinstance(bls_body, list) and len(bls_body) > 0:
        bl_id = bls_body[0].get("id")
    elif status == 200 and isinstance(bls_body, dict):
        results = bls_body.get("results", [])
        if results:
            bl_id = results[0].get("id")
    
    record("D0: Got org_id and bl_id", org_id is not None and bl_id is not None, f"org={org_id}, bl={bl_id}")

    # D1: super_admin code → 400
    if org_id:
        status, body = api("POST", "/api/v1/admin/registration-codes/", {
            "grants_role": "super_admin", "organization": str(org_id)
        }, token=admin_token)
        record("D1: super_admin code → 400", status == 400, f"got {status}")

    # D2: business_admin code → 201
    if org_id and bl_id:
        status, body = api("POST", "/api/v1/admin/registration-codes/", {
            "grants_role": "business_admin", "organization": str(org_id), "business_line": str(bl_id)
        }, token=admin_token)
        record("D2: business_admin code → 201", status == 201, f"got {status}")
        admin_code = body.get("code", "") if status == 201 else ""
        record("D3: Code plaintext returned", bool(admin_code), f"code={'yes' if admin_code else 'no'}")
    else:
        record("D2: business_admin code → 201", False, "no org/bl")
        admin_code = ""

    # D4: Use admin code to register
    if admin_code:
        admin_reg_email = rand_email()
        status, body = api("POST", "/api/v1/auth/register-admin/", {
            "email": admin_reg_email, "password": "StrongPass123!", "code": admin_code
        })
        record("D4: Admin-code registration → 201", status == 201, f"got {status}")
        is_ba = body.get("user", {}).get("is_business_admin", False) if status == 201 else False
        record("D5: Registered user is_business_admin", is_ba == True, f"is_business_admin={is_ba}")
else:
    record("D1-D5: Admin code tests", False, "no admin token")

# ── E. Announcements ────────────────────────────────────────────
print("\n[E] Announcements")
if admin_token:
    # E1: audience=all → 201
    status, body = api("POST", "/api/v1/notifications/announcements/", {
        "title": "Smoke test announcement", "body": "This is a smoke test",
        "audience": "all", "version": "V7-smoke-live"
    }, token=admin_token)
    record("E1: Announcement audience=all → 201", status == 201, f"got {status}")

    # E2: scoped without audience_ref → 400
    status, body = api("POST", "/api/v1/notifications/announcements/", {
        "title": "Scoped test", "body": "Missing ref", "audience": "org"
    }, token=admin_token)
    record("E2: Scoped announcement without ref → 400", status == 400, f"got {status}")

    # E3: scoped with audience_ref → 201
    status, body = api("POST", "/api/v1/notifications/announcements/", {
        "title": "Org announcement", "body": "With ref", "audience": "role", "audience_ref": "employee"
    }, token=admin_token)
    record("E3: Scoped announcement with ref → 201", status == 201, f"got {status}")
else:
    record("E1-E3: Announcement tests", False, "no admin token")

# ── F. Notifications ────────────────────────────────────────────
print("\n[F] Notifications")
if user_token:
    # F1: Feed accessible
    status, body = api("GET", "/api/v1/notifications/", token=user_token)
    record("F1: Notification feed → 200", status == 200, f"got {status}")

    # F2: Unread count
    status, body = api("GET", "/api/v1/notifications/unread-count/", token=user_token)
    record("F2: Unread count → 200", status == 200, f"got {status}")
    unread = body.get("count", -1) if status == 200 else -1
    record("F3: Unread count ≥ 1 (welcome notif)", unread >= 1, f"count={unread}")

    # F4: Mark all read
    status, body = api("POST", "/api/v1/notifications/read-all/", token=user_token)
    record("F4: Mark all read → 200", status == 200, f"got {status}")

    # F5: Unread count after mark-all → 0
    status, body = api("GET", "/api/v1/notifications/unread-count/", token=user_token)
    unread_after = body.get("count", -1) if status == 200 else -1
    record("F5: Unread count after mark-all → 0", unread_after == 0, f"count={unread_after}")
else:
    record("F1-F5: Notification tests", False, "no user token")

# ── G. Spaces ───────────────────────────────────────────────────
print("\n[G] Spaces")
if user_token:
    status, body = api("GET", "/api/v1/spaces/", token=user_token)
    record("G1: Space list → 200", status == 200, f"got {status}")
    spaces = body if isinstance(body, list) else body.get("results", []) if isinstance(body, dict) else []
    record("G2: User sees ≥ 1 space", len(spaces) >= 1, f"count={len(spaces)}")
else:
    record("G1-G2: Space tests", False, "no user token")

# ── H. RBAC user list (admin only) ──────────────────────────────
print("\n[H] RBAC / Admin")
if admin_token:
    status, body = api("GET", "/api/v1/rbac/users/", token=admin_token)
    record("H1: RBAC user list → 200", status == 200, f"got {status}")
else:
    record("H1: RBAC user list", False, "no admin token")

# Regular user should NOT access admin endpoints
if user_token:
    status, _ = api("GET", "/api/v1/rbac/users/", token=user_token)
    record("H2: Regular user RBAC → 403", status == 403, f"got {status}")

# ── Summary ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
print(f"Total: {len(RESULTS)} checks — {passed} PASS, {failed} FAIL")
if failed == 0:
    print("🎉 All smoke tests passed!")
else:
    print("⚠️  Some tests failed — see details above.")
print("=" * 60)

# Write results for report
with open("smoke_results.json", "w") as f:
    json.dump(RESULTS, f, indent=2)

sys.exit(1 if failed > 0 else 0)
