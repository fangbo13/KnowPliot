"""Test whether a regular user can call the official reference library via RAG.

Scenario:
  1. Login as fath@ey.com (regular user, owner of 测试自动编码工作区)
  2. 测试自动编码工作区 has an enabled reference to 审计知识库 (published official library)
  3. Test A: Ask WITH explicit library selection → should retrieve from 审计知识库
  4. Test B: Ask WITHOUT selection (auto-routing) → category "other" has no keywords
"""

import json
import uuid
import sys
import requests

BASE = "http://localhost:8000/api/v1"
EMAIL = "fath@ey.com"
PASSWORD = "admin123"


def parse_sse_stream(resp):
    """Yield (event, data) tuples from an SSE response."""
    event = None
    for line in resp.iter_lines():
        line = line.decode("utf-8") if isinstance(line, bytes) else line
        if not line:
            event = None
            continue
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            raw = line.split(":", 1)[1].strip()
            try:
                data = json.loads(raw)
            except ValueError:
                data = raw
            yield event, data


# ── Step 1: Login ────────────────────────────────────────────────────
print("=" * 60)
print("Step 1: Login as fath@ey.com")
resp = requests.post(f"{BASE}/auth/token/", json={"email": EMAIL, "password": PASSWORD})
print(f"  Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"  Error: {resp.text[:300]}")
    sys.exit(1)
token = resp.json()["access"]
headers = {"Authorization": f"Bearer {token}"}
print(f"  Token: {token[:40]}...")

# ── Step 2: Get space info and library references ───────────────────
print("\n" + "=" * 60)
print("Step 2: Get active space + library references")
resp = requests.get(f"{BASE}/spaces/", headers=headers)
data = resp.json()
spaces = data if isinstance(data, list) else data.get("results", [])
print(f"  Spaces count: {len(spaces)}")
for sp in spaces:
    print(f"    - {sp.get('name')} (id={sp.get('id')})")

test_space = next((sp for sp in spaces if sp.get("name") == "测试自动编码工作区"), None)
if not test_space:
    print("  ERROR: 测试自动编码工作区 not found!")
    sys.exit(1)
space_id = test_space["id"]
print(f"\n  Active space: {test_space['name']} (id={space_id})")

resp = requests.get(
    f"{BASE}/documents/library-references/",
    headers={**headers, "X-Space-Id": space_id},
)
print(f"  Library references status: {resp.status_code}")
refs = resp.json()
print(f"  References count: {len(refs)}")
library_id = None
for ref in refs:
    print(f"    - library={ref.get('library_name')} | enabled={ref.get('enabled')} | status={ref.get('library_status')}")
    if ref.get("enabled") and ref.get("library_status") == "published":
        library_id = ref["library"]
if not library_id:
    print("  ERROR: No enabled+published library reference found!")
    sys.exit(1)
print(f"\n  Library ID to select: {library_id}")

# ── Helper: run a chat turn ──────────────────────────────────────────
def run_chat(session_id, question, sel_libs, label):
    print(f"\n{'=' * 60}")
    print(f"{label}")
    print(f"  Question: '{question}'")
    print(f"  selected_library_ids: {sel_libs}")
    payload = {
        "content": question,
        "client_request_id": str(uuid.uuid4()),
        "answer_mode": "fast",
        "selected_library_ids": sel_libs,
    }
    tokens, citations, retrieval_info, error = [], 0, None, None
    try:
        resp = requests.post(
            f"{BASE}/chat/sessions/{session_id}/send/",
            json=payload, headers={**headers, "X-Space-Id": space_id},
            stream=True, timeout=120,
        )
        print(f"  HTTP Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  Error body: {resp.text[:500]}")
            error = f"http_{resp.status_code}"
        else:
            for ev, d in parse_sse_stream(resp):
                # Handle both dict and list data types from SSE
                if ev == "token":
                    if isinstance(d, dict):
                        tokens.append(d.get("token", ""))
                    elif isinstance(d, str):
                        tokens.append(d)
                elif ev == "citations":
                    # citations data may be a list directly or wrapped in a dict
                    if isinstance(d, list):
                        cites = d
                    elif isinstance(d, dict):
                        cites = d.get("citations", d.get("results", []))
                        if not cites and not isinstance(cites, list):
                            cites = [d]  # single citation as dict
                    else:
                        cites = []
                    citations = len(cites)
                    print(f"  Citations: {citations}")
                    for c in cites[:5]:
                        if isinstance(c, dict):
                            title = c.get("document_title", c.get("title", "?"))
                            doc_id = c.get("document_id", "?")
                            print(f"    - title={title} | doc_id={doc_id}")
                elif ev == "retrieval":
                    if isinstance(d, list):
                        chunks = d
                    elif isinstance(d, dict):
                        chunks = d.get("chunks", d.get("results", []))
                        if not isinstance(chunks, list):
                            chunks = [chunks] if chunks else []
                    else:
                        chunks = []
                    retrieval_info = chunks
                    print(f"  Retrieval: {len(chunks)} chunks")
                    for ch in chunks[:5]:
                        if isinstance(ch, dict):
                            sp_id = ch.get("space_id", "?")
                            score = ch.get("score", "?")
                            content = str(ch.get("content", ""))[:80]
                            print(f"    - space_id={sp_id} | score={score} | {content}")
                elif ev == "error":
                    if isinstance(d, dict):
                        error = d.get("message", "unknown")
                    else:
                        error = str(d)
                    print(f"  Error: {error}")
                elif ev == "done":
                    print("  Done.")
        resp.close()
    except Exception as e:
        error = str(e)
        print(f"  Exception: {e}")
    answer = "".join(tokens)
    return answer, citations, retrieval_info, error


# ── Step 3: Create sessions + run tests ─────────────────────────────
print("\n" + "=" * 60)
print("Step 3: Create chat sessions")
resp = requests.post(
    f"{BASE}/chat/sessions/",
    json={"title": "官方库RAG测试_有选择"},
    headers={**headers, "X-Space-Id": space_id},
)
session_a = resp.json()["id"]
print(f"  Session A: {session_a}")

resp = requests.post(
    f"{BASE}/chat/sessions/",
    json={"title": "官方库RAG测试_无选择"},
    headers={**headers, "X-Space-Id": space_id},
)
session_b = resp.json()["id"]
print(f"  Session B: {session_b}")

# Test A: WITH explicit library selection
answer_a, cites_a, retr_a, err_a = run_chat(
    session_a, "审计的基本原则是什么？", [library_id],
    "Test A: WITH explicit library selection",
)

# Test B: WITHOUT library selection (auto-routing)
answer_b, cites_b, retr_b, err_b = run_chat(
    session_b, "审计的基本原则是什么？", [],
    "Test B: WITHOUT library selection (auto-routing)",
)

# ── Analysis ────────────────────────────────────────────────────────
audit_keywords = ["独立", "客观", "确认", "咨询", "增加价值", "风险管理", "控制", "治理", "审计报告"]
ref_space_id = "a1c5d627-978d-4d9b-9b5f-966d83d9f486"

print("\n" + "=" * 60)
print("ANALYSIS")
print(f"  Test A (with selection):")
print(f"    Answer: {len(answer_a)} chars | preview: {answer_a[:200]}")
print(f"    Citations: {cites_a} | Error: {err_a}")
hits_a = [kw for kw in audit_keywords if kw in answer_a]
print(f"    Keyword hits: {hits_a}")
has_doc_ref_a = "审计知识库测试文档" in answer_a or cites_a > 0
print(f"    Has document reference: {has_doc_ref_a}")
if retr_a:
    has_ref = any(isinstance(ch, dict) and str(ch.get("space_id", "")) == ref_space_id for ch in retr_a)
    print(f"    Retrieval from 审计知识库 space: {has_ref}")

print(f"\n  Test B (auto-routing):")
print(f"    Answer: {len(answer_b)} chars | preview: {answer_b[:200]}")
print(f"    Citations: {cites_b} | Error: {err_b}")
hits_b = [kw for kw in audit_keywords if kw in answer_b]
print(f"    Keyword hits: {hits_b}")
has_doc_ref_b = "审计知识库测试文档" in answer_b or cites_b > 0
print(f"    Has document reference: {has_doc_ref_b}")
if retr_b:
    has_ref_b = any(isinstance(ch, dict) and str(ch.get("space_id", "")) == ref_space_id for ch in retr_b)
    print(f"    Retrieval from 审计知识库 space: {has_ref_b}")

# ── Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SUMMARY")
# Test A passes if: answer contains audit keywords AND references the test document
a_ok = bool(hits_a) and has_doc_ref_a
# Test B passes only if it actually retrieved from the official library (not just generic knowledge)
b_ok = bool(hits_b) and has_doc_ref_b and ("通用知识" not in answer_b)

print(f"  Test A (explicit selection): {'✓ PASS' if a_ok else '✗ FAIL'}")
print(f"  Test B (auto-routing):      {'✓ PASS' if b_ok else '✗ FAIL (expected)'}")

if a_ok:
    print("\n  ✓ 用户显式选择官方库后，RAG 检索成功跨越隔离边界，")
    print("    从「审计知识库」官方库获取到了相关文档内容。")
if not b_ok:
    print("\n  ⚠ 未显式选择时（自动路由），官方库未被检索到。")
    print("    原因：「审计知识库」类别为 other，CATEGORY_KEYWORDS['other'] 为空，")
    print("    自动路由无法匹配（除非查询中包含库名「审计知识库」字面量）。")
    print("    解决：用户需在聊天界面显式选择官方库，或为库添加关键词类别。")
if not a_ok:
    print("\n  ✗ 即便显式选择官方库，RAG 检索也失败。")
    print("    请检查：DashScope API Key、embedding 服务、pgvector 配置。")
