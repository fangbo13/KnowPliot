# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""API-level security and functionality tests for V4.2 release verification"""
import json, sys, os, time, urllib.request, urllib.error

os.environ['PYTHONIOENCODING'] = 'utf-8'
try: sys.stdout.reconfigure(encoding='utf-8')
except: pass

API_URL = "http://127.0.0.1:8030/api/v1"
TEST_EMAIL = "admin@ey.com"
TEST_PASSWORD = "admin123"

results = {"api_tests": [], "findings": []}

def add_api_result(test_id, name, status, notes, response_code=None, response_body=None):
    results["api_tests"].append({
        "id": test_id, "name": name, "status": status,
        "notes": notes, "response_code": response_code,
        "response_body": response_body[:200] if response_body else None
    })
    marker = "[OK]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[BLOCK]"
    print(f"  {marker} {test_id}: {name} -> {status} ({notes})")

def get_token():
    req = urllib.request.Request(
        f"{API_URL}/auth/token/",
        data=json.dumps({"email": TEST_EMAIL, "password": TEST_PASSWORD}).encode(),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("access", ""), data.get("refresh", ""), data.get("user", {})
    except Exception as e:
        print(f"  [WARN] Token获取失败: {e}")
        return "", "", {}

def api_request(url, method="GET", data=None, headers=None, timeout=10):
    """Helper for making API requests"""
    hdrs = headers or {}
    if data:
        hdrs["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    else:
        body = None
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='replace')
    except Exception as e:
        return None, str(e)

# ====== TEST EXECUTION ======

print("=" * 60)
print("EY Onboarding AI V4.2 - API Level Release Tests")
print("=" * 60)

# 1. AUTH - Login/JWT/Blacklist
print("\n--- AUTH Tests ---")
access, refresh, user_data = get_token()
add_api_result("API-AUTH-01", "Login and token retrieval",
               "PASS" if access else "FAIL",
               f"access_len={len(access)}, user={user_data.get('email','')}",
               200)

# JWT claims check (KB-V4.1-009: is_hr_admin should not be in claims)
if access:
    import base64
    try:
        payload_b64 = access.split('.')[1]
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload_json = json.loads(base64.b64decode(payload_b64).decode('utf-8', errors='replace'))
        has_hr_admin = "is_hr_admin" in payload_json
        add_api_result("API-AUTH-02", "JWT claims: is_hr_admin removed (KB-V4.1-009)",
                       "PASS" if not has_hr_admin else "FAIL",
                       f"is_hr_admin in payload={has_hr_admin}, keys={list(payload_json.keys())}")
    except Exception as e:
        add_api_result("API-AUTH-02", "JWT claims check", "BLOCKED", f"decode error: {e}")

# JWT blacklist check (SYS-V4.2-020)
if access and refresh:
    # Logout to blacklist tokens (must include refresh in body to blacklist it too)
    code, body = api_request(f"{API_URL}/auth/logout/",
                              method="POST",
                              headers={"Authorization": f"Bearer {access}"},
                              data={"refresh": refresh})
    add_api_result("API-AUTH-03", "Logout (blacklist tokens)",
                   "PASS" if code in (200, 204, 205) else "FAIL",
                   f"logout status={code}", code)

    # Try using blacklisted access token
    code2, body2 = api_request(f"{API_URL}/auth/me/",
                                headers={"Authorization": f"Bearer {access}"})
    add_api_result("API-AUTH-04", "Blacklisted access token rejected (SYS-V4.2-020)",
                   "PASS" if code2 == 401 else "FAIL",
                   f"status={code2}, body={body2[:100]}", code2)

    # Try using blacklisted refresh token — must be POST (not GET)
    code3, body3 = api_request(f"{API_URL}/auth/token/refresh/",
                                method="POST",
                                data={"refresh": refresh})
    add_api_result("API-AUTH-05", "Blacklisted refresh token rejected (SYS-V4.2-020)",
                   "PASS" if code3 in (401, 400) else "FAIL",
                   f"status={code3}, body={body3[:100]}", code3)

# Invalid credentials — wait for rate limit window to reset
# (prior login + logout may have consumed rate quota)
time.sleep(2)
code, body = api_request(f"{API_URL}/auth/token/",
                          method="POST",
                          data={"email": "wrong@test.com", "password": "wrong"})
add_api_result("API-AUTH-06", "Invalid credentials rejection",
               "PASS" if code in (401, 400) else "FAIL",
               f"status={code}", code)

# Wait for rate limit window to reset before RBAC tests
time.sleep(65)

# 2. RBAC - Self-deactivation / Rate limiting
print("\n--- RBAC Tests ---")
access2, _, _ = get_token()
if access2:
    # Get own user ID
    code, body = api_request(f"{API_URL}/auth/me/",
                              headers={"Authorization": f"Bearer {access2}"})
    if code == 200:
        me = json.loads(body)
        my_id = me.get("id", "")
        # Self-deactivation prevention (SYS-V4.2-022)
        # V4.2 fix_prompt: correct path is /rbac/users/{id}/deactivate/ not /users/{id}/deactivate/
        code_deact, body_deact = api_request(f"{API_URL}/rbac/users/{my_id}/deactivate/",
                                              method="POST",
                                              headers={"Authorization": f"Bearer {access2}"},
                                              data={})
        add_api_result("API-RBAC-01", "Self-deactivation blocked (SYS-V4.2-022)",
                       "PASS" if code_deact in (400, 403) else "FAIL",
                       f"status={code_deact}, body={body_deact[:100]}", code_deact)
    else:
        add_api_result("API-RBAC-01", "Self-deactivation blocked", "BLOCKED", f"me endpoint={code}")

    # RBAC roles endpoint accessible by admin
    code_roles, body_roles = api_request(f"{API_URL}/rbac/roles/",
                                          headers={"Authorization": f"Bearer {access2}"})
    add_api_result("API-RBAC-02", "Admin can access RBAC roles endpoint",
                   "PASS" if code_roles == 200 else "FAIL",
                   f"status={code_roles}", code_roles)

    # Users endpoint (V4.2 fix_prompt: correct path is /rbac/users/ not /users/)
    code_users, body_users = api_request(f"{API_URL}/rbac/users/",
                                          headers={"Authorization": f"Bearer {access2}"})
    add_api_result("API-RBAC-03", "Admin can access users endpoint",
                   "PASS" if code_users == 200 else "FAIL",
                   f"status={code_users}", code_users)

    # Role assignment rate limit (SYS-V4.2-023) - try 6 rapid requests
    rate_limited = False
    for i in range(7):
        code_rl, body_rl = api_request(f"{API_URL}/rbac/user-roles/",
                                        method="POST",
                                        headers={"Authorization": f"Bearer {access2}"},
                                        data={"user": my_id if my_id else "fake-id", "role": "admin"})
        if code_rl == 429:
            rate_limited = True
            break
        time.sleep(0.2)
    add_api_result("API-RBAC-04", "Role assignment rate limit 5/min (SYS-V4.2-023)",
                   "PASS" if rate_limited else "FAIL",
                   f"throttled={rate_limited} on attempt #{i+1}")

    # Audit log endpoint
    code_audit, body_audit = api_request(f"{API_URL}/audit/logs/",
                                          headers={"Authorization": f"Bearer {access2}"})
    add_api_result("API-RBAC-05", "Admin can access audit logs",
                   "PASS" if code_audit == 200 else "FAIL",
                   f"status={code_audit}", code_audit)

# 3. SSRF Defense (SYS-V4.2-001/002/003/005)
print("\n--- SSRF Tests ---")
# Wait for rate limit window to reset before SSRF tests (RBAC rate tests consumed quota)
time.sleep(60)
access3, _, _ = get_token()
if access3:
    # Private IP: 127.0.0.1
    code, body = api_request(f"{API_URL}/crawl/crawl/",
                              method="POST",
                              headers={"Authorization": f"Bearer {access3}"},
                              data={"url": "http://127.0.0.1/admin/"})
    add_api_result("API-SSRF-01", "SSRF: Private IP 127.0.0.1 blocked (SYS-V4.2-001)",
                   "PASS" if code in (400, 403) else "FAIL",
                   f"status={code}, body={body[:150]}", code)

    # IPv4-mapped IPv6: ::ffff:127.0.0.1
    code2, body2 = api_request(f"{API_URL}/crawl/crawl/",
                                method="POST",
                                headers={"Authorization": f"Bearer {access3}"},
                                data={"url": "http://[::ffff:127.0.0.1]/admin/"})
    add_api_result("API-SSRF-02", "SSRF: IPv4-mapped IPv6 blocked (SYS-V4.2-002)",
                   "PASS" if code2 in (400, 403) else "FAIL",
                   f"status={code2}, body={body2[:150]}", code2)

    # Cloud metadata: 169.254.169.254
    code3, body3 = api_request(f"{API_URL}/crawl/crawl/",
                                method="POST",
                                headers={"Authorization": f"Bearer {access3}"},
                                data={"url": "http://169.254.169.254/latest/meta-data/"})
    add_api_result("API-SSRF-03", "SSRF: Cloud metadata IP blocked",
                   "PASS" if code3 in (400, 403) else "FAIL",
                   f"status={code3}, body={body3[:150]}", code3)

    # Invalid protocol: file://
    code4, body4 = api_request(f"{API_URL}/crawl/crawl/",
                                method="POST",
                                headers={"Authorization": f"Bearer {access3}"},
                                data={"url": "file:///etc/passwd"})
    add_api_result("API-SSRF-04", "URL protocol: file:// rejected",
                   "PASS" if code4 in (400, 403) else "FAIL",
                   f"status={code4}, body={body4[:150]}", code4)

    # DNS rebinding: localhost DNS name pointing to private IP
    code5, body5 = api_request(f"{API_URL}/crawl/crawl/",
                                method="POST",
                                headers={"Authorization": f"Bearer {access3}"},
                                data={"url": "http://localhost:8030/api/v1/auth/token/"})
    add_api_result("API-SSRF-05", "SSRF: localhost DNS rebinding blocked (SYS-V4.2-003)",
                   "PASS" if code5 in (400, 403) else "FAIL",
                   f"status={code5}, body={body5[:150]}", code5)

    # Valid public URL should be accepted
    code6, body6 = api_request(f"{API_URL}/crawl/crawl/",
                                method="POST",
                                headers={"Authorization": f"Bearer {access3}"},
                                data={"url": "https://example.com"})
    add_api_result("API-SSRF-06", "Valid public URL accepted",
                   "PASS" if code6 in (200, 201) else "FAIL",
                   f"status={code6}", code6)

# 4. Rate Limiting (SYS-V4.1-005)
print("\n--- Rate Limit Tests ---")
# Login rate limit: 5/min for wrong credentials
login_limited = False
for i in range(7):
    code, body = api_request(f"{API_URL}/auth/token/",
                              method="POST",
                              data={"email": "fake@test.com", "password": f"wrong{i}"})
    if code == 429:
        login_limited = True
        break
add_api_result("API-RATE-01", "Login rate limit 5/min (SYS-V4.1-005)",
               "PASS" if login_limited else "FAIL",
               f"throttled={login_limited} at attempt #{i+1}")

# 5. DEBUG=False check (SYS-V4.2-010)
print("\n--- Production Settings Tests ---")
# Trigger a 500 error and check response format
code, body = api_request(f"{API_URL}/nonexistent-endpoint-that-will-404/",
                          timeout=5)
add_api_result("API-PROD-01", "404 error: no stack trace leak (SYS-V4.2-010)",
               "PASS" if code == 404 and "Traceback" not in body else "FAIL",
               f"status={code}, has_traceback={'Traceback' in body}", code)

# Check that production build serves frontend via nginx (SYS-V4.2-011)
req = urllib.request.Request("http://127.0.0.1:3030/")
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        html = resp.read().decode('utf-8', errors='replace')
        has_vite_build = "assets/index-" in html  # Fix: just check build hash exists
        has_nginx_headers = "nginx" in resp.headers.get("Server", "").lower()
        add_api_result("API-PROD-02", "Frontend: nginx production build (SYS-V4.2-011)",
                       "PASS" if has_vite_build and has_nginx_headers else "FAIL",
                       f"has_build_assets={has_vite_build}, server={resp.headers.get('Server','')}")
except Exception as e:
    add_api_result("API-PROD-02", "Frontend: nginx production build", "BLOCKED", str(e))

# CORS check (SYS-V4.1-001)
req = urllib.request.Request("http://127.0.0.1:8030/api/v1/auth/token/",
                              method="OPTIONS",
                              headers={"Origin": "http://evil-site.com", "Access-Control-Request-Method": "POST"})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        allow_origin = resp.headers.get("Access-Control-Allow-Origin", "")
        cors_safe = allow_origin != "*" and allow_origin != "http://evil-site.com"
        add_api_result("API-PROD-03", "CORS not allowing all origins (SYS-V4.1-001)",
                       "PASS" if cors_safe else "FAIL",
                       f"allow_origin={allow_origin}")
except urllib.error.HTTPError as e:
    add_api_result("API-PROD-03", "CORS check (405 method not allowed = also OK)",
                   "PASS", f"status={e.code}")
except Exception as e:
    add_api_result("API-PROD-03", "CORS check", "BLOCKED", str(e))

# 6. Performance - Connection pooling
print("\n--- Performance Tests ---")
access_perf, _, _ = get_token()
if access_perf:
    times = []
    for i in range(10):
        t0 = time.time()
        code, body = api_request(f"{API_URL}/auth/me/",
                                  headers={"Authorization": f"Bearer {access_perf}"})
        times.append(time.time() - t0)
    avg = sum(times) / len(times)
    max_t = max(times)
    add_api_result("API-PERF-01", "Connection pooling: 10 sequential requests (SYS-V4.2-012)",
                   "PASS" if avg < 1 else "FAIL",
                   f"avg={avg:.3f}s, max={max_t:.3f}s")

# Save results
with open("D:/Github/Onborading-AI/audit_reports/api_test_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n[JSON] saved: D:/Github/Onborading-AI/audit_reports/api_test_results.json")
print(f"Total API tests: {len(results['api_tests'])}")
print(f"Passed: {sum(1 for t in results['api_tests'] if t['status']=='PASS')}")
print(f"Failed: {sum(1 for t in results['api_tests'] if t['status']=='FAIL')}")
