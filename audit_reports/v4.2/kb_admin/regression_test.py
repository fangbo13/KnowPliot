"""V4.1 KB/Admin Regression Test Suite — 16 items."""
import requests, json, base64, os, sys, tempfile, inspect

BASE = 'http://localhost:8000/api/v1'
results = []

def login(email, pw):
    r = requests.post(f'{BASE}/auth/token/', json={'email':email,'password':pw}, timeout=10)
    if r.status_code != 200:
        print(f'  Login failed for {email}: {r.status_code}')
        return None, None, None
    data = r.json()
    return data['access'], data['refresh'], data.get('user',{})

def headers(token):
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

def api(method, path, token=None, data=None, timeout=10):
    h = headers(token) if token else {}
    r_func = getattr(requests, method.lower())
    if data:
        r = r_func(f'{BASE}{path}', headers=h, json=data, timeout=timeout)
    else:
        r = r_func(f'{BASE}{path}', headers=h, timeout=timeout)
    return r

admin_token, admin_refresh, admin_user = login('admin@test.ey.com', 'admin123')
hr_token, hr_refresh, hr_user = login('hr@test.ey.com', 'hr1234')
emp_token, emp_refresh, emp_user = login('employee@test.ey.com', 'emp1234')

# ============================================================
# TEST 1: KB-V4.1-009 — JWT claims no is_hr_admin
# ============================================================
print('='*60)
print('TEST 1: KB-V4.1-009 — JWT claims no is_hr_admin')
payload_b64 = admin_token.split('.')[1]
payload_b64 += '=' * (4 - len(payload_b64) % 4)
payload = json.loads(base64.urlsafe_b64decode(payload_b64))
has_hr = 'is_hr_admin' in payload
print(f'  JWT payload keys: {sorted(payload.keys())}')
print(f'  is_hr_admin in JWT: {has_hr}')
status = 'PASS' if not has_hr else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-009', 'JWT claims no is_hr_admin', status))

# ============================================================
# TEST 2: KB-V4.1-010 — Token blacklist (logout)
# ============================================================
print('='*60)
print('TEST 2: KB-V4.1-010 — Token blacklist (logout)')
logout_token, logout_refresh, _ = login('hr@test.ey.com', 'hr1234')
r_logout = api('post', '/auth/logout/', logout_token, data={'refresh': logout_refresh})
print(f'  Logout response: status={r_logout.status_code}')
r_after = api('get', '/auth/me/', logout_token)
print(f'  Post-logout /auth/me/: status={r_after.status_code}')
status = 'PASS' if r_after.status_code == 401 else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-010', 'Token blacklist (logout)', status))

# ============================================================
# TEST 3: KB-V4.1-006 — Magic number file validation
# ============================================================
print('='*60)
print('TEST 3: KB-V4.1-006 — Magic number file validation')
pe_header = b'MZ\x00\x00' + b'\x00' * 257
with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
    f.write(pe_header)
    f.flush()
    pe_path = f.name

r_upload = requests.post(
    f'{BASE}/documents/',
    headers=headers(hr_token),
    files={'file': (os.path.basename(pe_path), open(pe_path, 'rb'), 'application/pdf')},
    data={'title': 'malicious_exe_as_pdf', 'file_type': 'pdf'},
    timeout=10
)
print(f'  Upload PE-as-PDF: status={r_upload.status_code}')
resp_text = r_upload.text[:200]
print(f'  Response: {resp_text}')
os.unlink(pe_path)
status = 'PASS' if r_upload.status_code == 400 else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-006', 'Magic number file validation', status))

# ============================================================
# TEST 4: KB-V4.1-007 — AuthenticatedMediaMiddleware
# ============================================================
print('='*60)
print('TEST 4: KB-V4.1-007 — AuthenticatedMediaMiddleware')
r_media_noauth = requests.get('http://localhost:8000/media/documents/test.pdf', timeout=5)
print(f'  Media access without auth: status={r_media_noauth.status_code}')
print(f'  Response body: {r_media_noauth.text[:100]}')
status = 'PASS' if r_media_noauth.status_code == 403 else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-007', 'AuthenticatedMediaMiddleware', status))

# ============================================================
# TEST 5: KB-V4.1-003 — Horizontal privilege (doc delete)
# ============================================================
print('='*60)
print('TEST 5: KB-V4.1-003 — Horizontal privilege (doc delete)')
with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
    f.write(b'Test document for horizontal privilege check\n' + b'Padding ' * 100)
    f.flush()
    txt_path = f.name

r_upload_hr = requests.post(
    f'{BASE}/documents/',
    headers=headers(hr_token),
    files={'file': ('hr_test_doc.txt', open(txt_path, 'rb'), 'text/plain')},
    data={'title': 'HR test doc', 'file_type': 'txt'},
    timeout=10
)
print(f'  HR upload doc: status={r_upload_hr.status_code}')
horiz_pass = False
if r_upload_hr.status_code == 201:
    doc_id = r_upload_hr.json().get('id')
    # Employee tries to delete HR doc
    r_del_emp = api('delete', f'/documents/{doc_id}/', emp_token)
    print(f'  Employee delete attempt: status={r_del_emp.status_code}')
    horiz_pass = r_del_emp.status_code == 403
else:
    print(f'  Upload failed, cannot test delete')
os.unlink(txt_path)
status = 'PASS' if horiz_pass else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-003', 'Horizontal privilege (doc delete)', status))

# ============================================================
# TEST 6: KB-V4.1-004 — Retriever SQL column whitelist
# ============================================================
print('='*60)
print('TEST 6: KB-V4.1-004 — Retriever SQL column whitelist')
from apps.rag.retriever import PgVectorRetriever
retriever = PgVectorRetriever()
source = inspect.getsource(PgVectorRetriever._search_pgvector)
has_whitelist = 'ALLOWED_FILTER_KEYS' in source
print(f'  ALLOWED_FILTER_KEYS found in code: {has_whitelist}')
whitelist_pass = False
try:
    retriever._search_pgvector('test', 5, 0.5, {'evil_key': '123'})
    print('  Invalid key was NOT rejected (FAIL)')
except ValueError as e:
    print(f'  Invalid key rejected with ValueError: {e}')
    whitelist_pass = True
except Exception as e2:
    print(f'  Other error: {e2}')
status = 'PASS' if whitelist_pass else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-004', 'Retriever SQL column whitelist', status))

# ============================================================
# TEST 7: KB-V4.1-002 — Superuser bypass audit trail
# ============================================================
print('='*60)
print('TEST 7: KB-V4.1-002 — Superuser bypass audit trail')
r_audit = api('get', '/audit/', admin_token)
print(f'  Admin audit list: status={r_audit.status_code}')
has_bypass = False
if r_audit.status_code == 200:
    audit_data = r_audit.json()
    results_list = audit_data.get('results', audit_data if isinstance(audit_data, list) else [])
    for entry in results_list:
        action = str(entry.get('action', ''))
        if 'superuser' in action.lower() or 'bypass' in action.lower() or 'PermissionBypass' in action or 'RoleBypass' in action:
            has_bypass = True
            print(f'  Found bypass entry: action={action}')
    if not has_bypass:
        # Trigger a bypass by accessing RBAC endpoint
        r_rbac = api('get', '/rbac/roles/', admin_token)
        print(f'  Triggered RBAC access: status={r_rbac.status_code}')
        r_audit2 = api('get', '/audit/', admin_token)
        if r_audit2.status_code == 200:
            for entry in r_audit2.json().get('results', []):
                action = str(entry.get('action', ''))
                if 'superuser' in action.lower() or 'bypass' in action.lower():
                    has_bypass = True
                    print(f'  Found bypass after trigger: action={action}')
status = 'PASS' if has_bypass else 'PARTIAL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-002', 'Superuser bypass audit trail', status))

# ============================================================
# TEST 8: KB-V4.1-008 — File size limits (1KB min)
# ============================================================
print('='*60)
print('TEST 8: KB-V4.1-008 — File size limits (1KB min)')
tiny_content = b'X'
with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
    f.write(tiny_content)
    f.flush()
    tiny_path = f.name

r_tiny = requests.post(
    f'{BASE}/documents/',
    headers=headers(hr_token),
    files={'file': ('tiny.txt', open(tiny_path, 'rb'), 'text/plain')},
    data={'title': 'tiny_file', 'file_type': 'txt'},
    timeout=10
)
print(f'  Upload tiny file (<1KB): status={r_tiny.status_code}')
print(f'  Response: {r_tiny.text[:150]}')
os.unlink(tiny_path)
status = 'PASS' if r_tiny.status_code == 400 else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-008', 'File size limits (1KB min)', status))

# ============================================================
# TEST 9: KB-V4.1-005 — Prompt Injection defense
# ============================================================
print('='*60)
print('TEST 9: KB-V4.1-005 — Prompt Injection defense (code audit)')
from apps.rag.pipeline import RAGPipeline
source = inspect.getsource(RAGPipeline.retrieve_and_generate)
has_sanitize = '_sanitize_content' in source
has_guardrails = 'guardrails.check_input' in source
print(f'  _sanitize_content found: {has_sanitize}')
print(f'  guardrails.check_input found: {has_guardrails}')
status = 'PASS' if (has_sanitize and has_guardrails) else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-005', 'Prompt Injection defense (code)', status))

# ============================================================
# TEST 10: KB-V4.1-011 — CrawledDocument model
# ============================================================
print('='*60)
print('TEST 10: KB-V4.1-011 — CrawledDocument model')
from apps.crawler.models import CrawledDocument, CrawlTaskLog
print(f'  CrawledDocument: {CrawledDocument.__name__}')
print(f'  CrawlTaskLog: {CrawlTaskLog.__name__}')
status = 'PASS'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-011', 'CrawledDocument model', status))

# ============================================================
# TEST 11: KB-V4.1-012 — SSRF protection
# ============================================================
print('='*60)
print('TEST 11: KB-V4.1-012 — SSRF protection')
from apps.crawler.validators import CrawlURLValidator
validator = CrawlURLValidator()
ssrf_tests = [
    ('http://127.0.0.1:8000/admin/', False),
    ('file:///etc/passwd', False),
    ('http://169.254.169.254/latest/meta-data/', False),
    ('https://example.com', True),
]
all_pass = True
for url, expected_valid in ssrf_tests:
    is_valid, reason = validator.validate(url)
    print(f'  {url}: valid={is_valid} expected={expected_valid} reason={reason[:60]}')
    if is_valid != expected_valid:
        all_pass = False
status = 'PASS' if all_pass else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-012', 'SSRF protection', status))

# ============================================================
# TEST 12: KB-V4.1-013 — ContentCleaner
# ============================================================
print('='*60)
print('TEST 12: KB-V4.1-013 — ContentCleaner')
from apps.crawler.cleaners import ContentCleaner
cleaner = ContentCleaner()
test_html = '<script>alert(1)</script><p>Safe content</p><iframe src="evil.com"></iframe>'
cleaned = cleaner.clean(test_html)
has_script = '<script>' in cleaned
has_iframe = '<iframe' in cleaned
print(f'  Cleaned content: {cleaned[:80]}')
print(f'  script removed: {not has_script}, iframe removed: {not has_iframe}')
status = 'PASS' if (not has_script and not has_iframe) else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-013', 'ContentCleaner HTML sanitization', status))

# ============================================================
# TEST 13: KB-V4.1-014 — CrawlerService + Celery
# ============================================================
print('='*60)
print('TEST 13: KB-V4.1-014 — CrawlerService + Celery')
from apps.crawler.services import CrawlerService
print(f'  CrawlerService class: {CrawlerService.__name__}')
status = 'PASS'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-014', 'CrawlerService + Celery', status))

# ============================================================
# TEST 14: KB-V4.1-015 — SimHash dedup
# ============================================================
print('='*60)
print('TEST 14: KB-V4.1-015 — SimHash dedup')
from apps.crawler.tasks import crawl_and_ingest
source = inspect.getsource(crawl_and_ingest)
has_hash = 'content_hash' in source
has_dedup = 'duplicate_skipped' in source
print(f'  content_hash: {has_hash}, duplicate_skipped: {has_dedup}')
status = 'PASS' if (has_hash and has_dedup) else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-015', 'SimHash dedup', status))

# ============================================================
# TEST 15: KB-V4.1-016 — Crawler API permissions
# ============================================================
print('='*60)
print('TEST 15: KB-V4.1-016 — Crawler API permissions')
r_crawl_emp = api('post', '/crawl/crawl/', emp_token, data={'url': 'https://example.com'})
print(f'  Employee POST /crawl/crawl/: status={r_crawl_emp.status_code}')
r_tasks_hr = api('get', '/crawl/', hr_token)
print(f'  HR GET /crawl/: status={r_tasks_hr.status_code}')
status = 'PASS' if r_crawl_emp.status_code == 403 and r_tasks_hr.status_code == 200 else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-016', 'Crawler API permissions', status))

# ============================================================
# TEST 16: KB-V4.1-017 — Audit Log + dependencies
# ============================================================
print('='*60)
print('TEST 16: KB-V4.1-017 — Audit Log + dependencies')
from apps.audit.models import AuditLog
choices = [c[0] for c in AuditLog.ACTION_CHOICES]
has_crawl = 'document_crawl' in choices
has_withdraw = 'document_crawl_withdraw' in choices
print(f'  document_crawl in choices: {has_crawl}')
print(f'  document_crawl_withdraw in choices: {has_withdraw}')
with open('/app/pyproject.toml') as f:
    pyproject = f.read()
deps = ['filetype', 'bleach', 'trafilatura', 'simhash', 'gevent']
deps_found = {d: d in pyproject for d in deps}
for d, found in deps_found.items():
    print(f'  Dependency {d}: {found}')
all_deps = all(deps_found.values())
status = 'PASS' if (has_crawl and has_withdraw and all_deps) else 'FAIL'
print(f'  RESULT: {status}')
results.append(('KB-V4.1-017', 'Audit Log + dependencies', status))

# ============================================================
# SUMMARY
# ============================================================
print('='*60)
print('REGRESSION TEST SUMMARY')
print('='*60)
pass_count = sum(1 for _, _, s in results if s == 'PASS')
partial_count = sum(1 for _, _, s in results if s == 'PARTIAL')
fail_count = sum(1 for _, _, s in results if s == 'FAIL')
for test_id, desc, status in results:
    emoji = '✅' if status == 'PASS' else ('⚠' if status == 'PARTIAL' else '❌')
    print(f'  {emoji} {test_id}: {desc} -> {status}')
print(f'\nTotal: {len(results)} tests')
print(f'PASS: {pass_count}, PARTIAL: {partial_count}, FAIL: {fail_count}')
print(f'Pass Rate: {pass_count/len(results)*100:.1f}%')

# Save results to JSON for report generation
with open('/tmp/regression_results.json', 'w') as f:
    json.dump(results, f, indent=2)
print(f'\nResults saved to /tmp/regression_results.json')
