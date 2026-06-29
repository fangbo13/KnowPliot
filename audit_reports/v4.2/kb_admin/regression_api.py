"""V4.1 KB/Admin Regression Test Suite — split into API-only and Django-only parts."""
import json, base64, requests, os

BASE = 'http://localhost:8000/api/v1'
results = []

def login(email, pw):
    r = requests.post(f'{BASE}/auth/token/', json={'email':email,'password':pw}, timeout=10)
    if r.status_code != 200:
        return None, None, None
    data = r.json()
    return data['access'], data['refresh'], data.get('user',{})

def auth_headers(token):
    return {'Authorization': f'Bearer {token}'}

def api_get(path, token, timeout=10):
    return requests.get(f'{BASE}{path}', headers=auth_headers(token), timeout=timeout)

def api_post(path, token, data=None, timeout=10):
    return requests.post(f'{BASE}{path}', headers={**auth_headers(token), 'Content-Type':'application/json'}, json=data, timeout=timeout)

def api_delete(path, token, timeout=10):
    return requests.delete(f'{BASE}{path}', headers=auth_headers(token), timeout=timeout)

def upload_doc(token, filename, content_bytes, file_type, title):
    data = {'title': title, 'file_type': file_type}
    files = {'file': (filename, content_bytes)}
    r = requests.post(f'{BASE}/documents/', headers=auth_headers(token), data=data, files=files, timeout=10)
    return r

admin_token, admin_refresh, _ = login('admin@test.ey.com', 'admin123')
hr_token, hr_refresh, _ = login('hr@test.ey.com', 'hr1234')
emp_token, emp_refresh, _ = login('employee@test.ey.com', 'emp1234')

# TEST 1: KB-V4.1-009 — JWT claims no is_hr_admin
print('TEST 1: KB-V4.1-009')
payload_b64 = admin_token.split('.')[1]
payload_b64 += '=' * (4 - len(payload_b64) % 4)
payload = json.loads(base64.urlsafe_b64decode(payload_b64))
has_hr = 'is_hr_admin' in payload
print(f'  Keys: {sorted(payload.keys())}')
print(f'  is_hr_admin in JWT: {has_hr}')
status = 'PASS' if not has_hr else 'FAIL'
print(f'  -> {status}')
results.append(('KB-V4.1-009', 'JWT claims no is_hr_admin', status, f'Keys={sorted(payload.keys())}'))

# TEST 2: KB-V4.1-010 — Token blacklist
print('TEST 2: KB-V4.1-010')
fresh_token, fresh_refresh, _ = login('hr@test.ey.com', 'hr1234')
r_logout = api_post('/auth/logout/', fresh_token, {'refresh': fresh_refresh})
print(f'  Logout: {r_logout.status_code}')
r_after = api_get('/auth/me/', fresh_token)
print(f'  Post-logout /auth/me/: {r_after.status_code}')
status = 'PASS' if r_after.status_code in [401, 403] else 'PARTIAL'
print(f'  -> {status}')
results.append(('KB-V4.1-010', 'Token blacklist', status, f'after_logout={r_after.status_code}'))

# TEST 3: KB-V4.1-006 — Magic number
print('TEST 3: KB-V4.1-006')
pe = b'MZ\x00\x00' + b'\x00' * 1500
r = upload_doc(hr_token, 'malicious_exe.pdf', pe, 'pdf', 'PE as PDF test')
print(f'  Upload PE-as-PDF: {r.status_code}, body={r.text[:100]}')
status = 'PASS' if r.status_code in [400] else 'FAIL'
print(f'  -> {status}')
results.append(('KB-V4.1-006', 'Magic number validation', status, f'status={r.status_code}'))

# TEST 4: KB-V4.1-007 — Media middleware
print('TEST 4: KB-V4.1-007')
r = requests.get('http://localhost:8000/media/documents/test.pdf', timeout=5)
print(f'  Media no auth: {r.status_code}, body={r.text[:80]}')
status = 'PASS' if r.status_code == 403 else 'FAIL'
print(f'  -> {status}')
results.append(('KB-V4.1-007', 'Media auth middleware', status, f'status={r.status_code}'))

# TEST 5: KB-V4.1-003 — Horizontal privilege
print('TEST 5: KB-V4.1-003')
txt = b'Horizontal privilege test\n' + b'Padding ' * 100
r_upload = upload_doc(hr_token, 'hr_doc.txt', txt, 'txt', 'HR horizontal test')
print(f'  HR upload: {r_upload.status_code}')
if r_upload.status_code == 201:
    doc_id = r_upload.json().get('id')
    r_del = api_delete(f'/documents/{doc_id}/', emp_token)
    print(f'  Employee delete: {r_del.status_code}, body={r_del.text[:100]}')
    status = 'PASS' if r_del.status_code == 403 else 'FAIL'
else:
    print(f'  Upload failed: {r_upload.text[:100]}')
    status = 'PARTIAL'
print(f'  -> {status}')
results.append(('KB-V4.1-003', 'Horizontal privilege', status))

# TEST 8: KB-V4.1-008 — File size 1KB min
print('TEST 8: KB-V4.1-008')
r = upload_doc(hr_token, 'tiny.txt', b'X', 'txt', 'Tiny file test')
print(f'  Upload tiny: {r.status_code}, body={r.text[:100]}')
status = 'PASS' if r.status_code == 400 else 'FAIL'
print(f'  -> {status}')
results.append(('KB-V4.1-008', 'File size 1KB min', status, f'status={r.status_code}'))

# TEST 15: KB-V4.1-016 — Crawler API permissions
print('TEST 15: KB-V4.1-016')
r_emp = api_post('/crawl/crawl/', emp_token, {'url': 'https://example.com'})
print(f'  Employee POST /crawl/crawl/: {r_emp.status_code}')
r_hr = api_get('/crawl/', hr_token)
print(f'  HR GET /crawl/: {r_hr.status_code}')
status = 'PASS' if r_emp.status_code == 403 and r_hr.status_code == 200 else 'FAIL'
print(f'  -> {status}')
results.append(('KB-V4.1-016', 'Crawler API permissions', status))

# SUMMARY
print('='*60)
print('API TESTS SUMMARY')
pass_count = sum(1 for _, _, s, *_ in results if s == 'PASS')
partial_count = sum(1 for _, _, s, *_ in results if s == 'PARTIAL')
fail_count = sum(1 for _, _, s, *_ in results if s == 'FAIL')
for r in results:
    emoji = '✅' if r[2] == 'PASS' else ('⚠' if r[2] == 'PARTIAL' else '❌')
    print(f'  {emoji} {r[0]}: {r[1]} -> {r[2]}')
print(f'PASS: {pass_count}, PARTIAL: {partial_count}, FAIL: {fail_count}')

with open('/tmp/api_regression_results.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
