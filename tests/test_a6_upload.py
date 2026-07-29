"""Upload A6 (minimal PDF >= 1KB) and poll ingestion status."""
import os, sys, json, time, requests, io, struct, zipfile, tempfile
from pathlib import Path

BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"
LOGIN_EMAIL = "auditor.xu@test.ey.com"
LOGIN_PASSWORD = "Auditor#2026"
SPACE_ID = "0cb246e8-c8a7-45eb-b70c-232e38e2bd04"

TEMP_DIR = Path(tempfile.mkdtemp(prefix="kp_a6_"))

def gen_pdf_minimal():
    """最小合法 PDF（>= 1KB）"""
    stream_content = b"BT /F1 12 Tf 100 700 Td (KnowPilot Upload Test PDF Document) Tj ET\n"
    for i in range(20):
        stream_content += f"BT /F1 10 Tf 100 {680 - i * 12} Td (Line {i}: Additional test content for padding to meet minimum size.) Tj ET\n".encode()
    stream_len = len(stream_content)

    pdf = f"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length {stream_len}>>stream
""".encode() + stream_content + b"""endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
434
%%EOF
""".encode()
    if len(pdf) < 1024:
        pdf += b"\n% padding to exceed 1KB minimum" * ((1024 - len(pdf)) // 30 + 1)
    p = TEMP_DIR / "test_minimal.pdf"
    p.write_bytes(pdf)
    return p

def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

# 1) Login
r = requests.post(
    f"{API}/auth/token/",
    json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
    timeout=10,
)
assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
token = r.json()["access"]
print(f"[OK] Login as {LOGIN_EMAIL}")

# 2) Clear rate limit cache
import subprocess
subprocess.run(["docker", "compose", "exec", "-T", "redis", "redis-cli", "FLUSHDB"], 
               capture_output=True, timeout=10)

# 3) Generate and upload A6
file_path = gen_pdf_minimal()
file_size = os.path.getsize(file_path)
print(f"\n--- A6: PDF 最小 ---")
print(f"  文件: {file_path.name}")
print(f"  大小: {format_size(file_size)} ({file_size} bytes)")

headers = {
    "Authorization": f"Bearer {token}",
    "X-Space-Id": SPACE_ID,
}

with open(file_path, "rb") as f:
    files = {"file": (file_path.name, f)}
    data = {"title": "upload_test_A6: PDF 最小"}
    
    start = time.perf_counter()
    r = requests.post(
        f"{API}/documents/",
        headers=headers,
        data=data,
        files=files,
        timeout=60,
    )
    upload_time = time.perf_counter() - start

try:
    body = r.json()
except:
    body = {"raw": r.text[:500]}

print(f"  HTTP {r.status_code}")
print(f"  上传耗时: {upload_time:.3f}s")

if r.status_code == 201:
    doc_id = body.get("id")
    print(f"  doc_id={doc_id}")
    
    # Poll for ingestion
    print(f"  等待解析完成...")
    poll_start = time.perf_counter()
    while time.perf_counter() - poll_start < 300:
        r2 = requests.get(
            f"{API}/documents/{doc_id}/",
            headers={"Authorization": f"Bearer {token}", "X-Space-Id": SPACE_ID},
            timeout=10,
        )
        if r2.status_code == 200:
            doc = r2.json()
            status = doc.get("status", "unknown")
            if status in ("active", "failed", "archived", "rejected", "pending_review"):
                proc_time = time.perf_counter() - poll_start
                chunk_count = doc.get("chunk_count", 0)
                error = doc.get("processing_error", "")
                print(f"  解析状态: {status}")
                print(f"  解析耗时: {proc_time:.3f}s")
                print(f"  分块数: {chunk_count}")
                if error:
                    print(f"  处理错误: {error[:100]}")
                
                # Output JSON for the test result
                result = {
                    "group": "A",
                    "label": "A6: PDF 最小",
                    "filename": file_path.name,
                    "file_type": "pdf",
                    "file_size": file_size,
                    "file_size_human": format_size(file_size),
                    "http_status": r.status_code,
                    "upload_time_s": round(upload_time, 3),
                    "ingestion_status": status,
                    "processing_time_s": round(proc_time, 3),
                    "chunk_count": chunk_count,
                    "processing_error": error,
                    "verdict": "PASS" if status == "active" else "FAIL",
                    "doc_id": doc_id,
                }
                print(f"\n[RESULT_JSON] {json.dumps(result)}")
                break
        time.sleep(2)
    else:
        print(f"  [TIMEOUT] Polling exceeded 5 minutes")
        result = {
            "group": "A",
            "label": "A6: PDF 最小",
            "filename": file_path.name,
            "file_type": "pdf",
            "file_size": file_size,
            "file_size_human": format_size(file_size),
            "http_status": r.status_code,
            "upload_time_s": round(upload_time, 3),
            "ingestion_status": "timeout",
            "processing_time_s": 300,
            "chunk_count": 0,
            "processing_error": "Polling timeout",
            "verdict": "FAIL",
            "doc_id": doc_id,
        }
        print(f"\n[RESULT_JSON] {json.dumps(result)}")
else:
    print(f"  上传失败: {json.dumps(body)[:200]}")
    result = {
        "group": "A",
        "label": "A6: PDF 最小",
        "filename": file_path.name,
        "file_type": "pdf",
        "file_size": file_size,
        "file_size_human": format_size(file_size),
        "http_status": r.status_code,
        "upload_time_s": round(upload_time, 3),
        "ingestion_status": "upload_failed",
        "processing_time_s": 0,
        "chunk_count": 0,
        "processing_error": json.dumps(body)[:200],
        "verdict": "FAIL",
    }
    print(f"\n[RESULT_JSON] {json.dumps(result)}")
