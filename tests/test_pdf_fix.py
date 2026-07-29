#!/usr/bin/env python3
"""
PDF 解析修复验证脚本

验证内容：
  1. 上传全新内容的 PDF（时间戳保证内容哈希不同，避开缓存）
  2. 等待解析完成
  3. 拉取全部分块，验证：
     - 不含 %PDF / endobj / stream 等原始 PDF 语法
     - 含有 PDF 正文中的真实文本
用法:
    python tests/test_pdf_fix.py
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = os.environ.get("KNOWPILOT_URL", "http://localhost:8000")
API = f"{BASE_URL}/api/v1"
LOGIN_EMAIL = os.environ.get("TEST_USER", "auditor.xu@test.ey.com")
LOGIN_PASSWORD = os.environ.get("TEST_PASS", "Auditor#2026")
TIMEOUT_POLL = 600  # Docling 首次运行需下载模型，放宽
POLL_INTERVAL = 3.0

TEMP_DIR = Path(tempfile.mkdtemp(prefix="kp_pdf_fix_"))
OUT_DIR = Path(os.environ.get("TEST_OUTPUT_DIR", "e:/KnowPliot/audit_reports/file_upload_tests"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
MARKER = f"PDFFIX{STAMP}"  # 出现在正文中的唯一标记


def gen_pdf():
    """生成含唯一文本的合法 PDF（未压缩文本流，便于任何解析器提取）"""
    lines = [f"KnowPilot PDF Parse Fix Verification {MARKER}"]
    for i in range(30):
        lines.append(
            f"Line {i}: audit evidence paragraph {MARKER} row {i} for extraction check."
        )
    stream = b""
    y = 750
    for ln in lines:
        stream += f"BT /F1 11 Tf 72 {y} Td ({ln}) Tj ET\n".encode()
        y -= 14
    header = b"%PDF-1.4\n"
    obj1 = b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    obj2 = b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    obj3 = (
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    )
    obj4 = (
        b"4 0 obj<</Length " + str(len(stream)).encode() + b">>stream\n"
        + stream + b"endstream\nendobj\n"
    )
    obj5 = b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"

    parts = [header, obj1, obj2, obj3, obj4, obj5]
    offsets = []
    pos = 0
    for part in parts:
        offsets.append(pos)
        pos += len(part)
    body = b"".join(parts)
    xref_pos = len(body)
    xref = b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n".encode()
    trailer = (
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n"
        + str(xref_pos).encode() + b"\n%%EOF\n"
    )
    pdf = body + xref + trailer

    p = TEMP_DIR / f"test_pdf_fix_{STAMP}.pdf"
    p.write_bytes(pdf)
    return p


def login():
    r = requests.post(
        f"{API}/auth/token/",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=10,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    print(f"[OK] Login as {LOGIN_EMAIL}")
    return r.json()["access"]


def get_space_id(token):
    r = requests.get(
        f"{API}/spaces/", headers={"Authorization": f"Bearer {token}"}, timeout=10
    )
    spaces = r.json()
    if isinstance(spaces, dict) and "results" in spaces:
        spaces = spaces["results"]
    return spaces[0]["id"] if spaces else None


def main():
    pdf_path = gen_pdf()
    size = os.path.getsize(pdf_path)
    print(f"[GEN] {pdf_path.name} ({size} bytes), marker={MARKER}")

    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    space_id = get_space_id(token)
    if space_id:
        headers["X-Space-Id"] = str(space_id)
    print(f"[OK] Space: {space_id}")

    # 上传
    with open(pdf_path, "rb") as f:
        start = time.perf_counter()
        r = requests.post(
            f"{API}/documents/",
            headers=headers,
            data={"title": f"pdf_fix_test_{STAMP}"},
            files={"file": (pdf_path.name, f)},
            timeout=60,
        )
        upload_time = time.perf_counter() - start
    print(f"[UPLOAD] HTTP {r.status_code} in {upload_time:.3f}s")
    if r.status_code != 201:
        print(f"[FAIL] Upload rejected: {r.text[:500]}")
        sys.exit(1)
    doc_id = r.json()["id"]
    print(f"[OK] Document ID: {doc_id}")

    # 轮询解析状态
    t0 = time.perf_counter()
    status = "pending"
    error = ""
    chunk_count = 0
    while time.perf_counter() - t0 < TIMEOUT_POLL:
        rr = requests.get(f"{API}/documents/{doc_id}/", headers=headers, timeout=30)
        body = rr.json()
        status = body.get("status")
        error = body.get("processing_error", "")
        chunk_count = body.get("chunk_count", 0)
        if status in ("active", "failed"):
            break
        time.sleep(POLL_INTERVAL)
    poll_time = time.perf_counter() - t0
    print(f"[PARSE] status={status} chunks={chunk_count} in {poll_time:.1f}s")
    if error:
        print(f"[PARSE] error={error[:300]}")
    if status != "active":
        print("[FAIL] Document did not become active")
        sys.exit(1)

    # 拉取全部分块（分页）
    all_chunks = []
    page = 1
    while True:
        rc = requests.get(
            f"{API}/documents/{doc_id}/chunks/?page={page}", headers=headers, timeout=30
        )
        data = rc.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        if not items:
            break
        all_chunks.extend(items)
        if isinstance(data, dict) and data.get("next"):
            page += 1
        else:
            break
    print(f"[CHUNKS] fetched {len(all_chunks)} chunks")

    # 验证内容（Docling Markdown 导出会转义下划线，先归一化）
    all_text = "\n".join(c.get("content", "") for c in all_chunks)
    normalized = all_text.replace("\\_", "_")
    has_pdf_syntax = any(
        tok in normalized for tok in ("%PDF", "endobj", "startxref", "/Type/Catalog")
    )
    has_marker = MARKER in normalized
    print(f"[CHECK] raw PDF syntax present: {has_pdf_syntax}")
    print(f"[CHECK] real text marker present: {has_marker}")
    print(f"[SAMPLE] first chunk[:300]: {all_chunks[0].get('content', '')[:300]!r}")

    verdict = "PASS" if (not has_pdf_syntax and has_marker) else "FAIL"
    result = {
        "test": "pdf_parse_fix",
        "timestamp": STAMP,
        "marker": MARKER,
        "file_size": size,
        "upload_time_s": round(upload_time, 3),
        "poll_time_s": round(poll_time, 1),
        "status": status,
        "chunk_count": chunk_count,
        "chunks_fetched": len(all_chunks),
        "has_pdf_syntax": has_pdf_syntax,
        "has_marker": has_marker,
        "first_chunk_preview": all_chunks[0].get("content", "")[:300],
        "verdict": verdict,
    }
    out = OUT_DIR / "pdf_fix_test_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[{verdict}] result saved to {out}")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
