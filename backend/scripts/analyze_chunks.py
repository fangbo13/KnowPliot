"""Analyze document parsing accuracy via HTTP API only - no Django ORM needed."""
import json, requests, time, sys

BASE = 'http://localhost:8000/api/v1'
SPACE_ID = '0cb246e8-c8a7-45eb-b70c-232e38e2bd04'

# Login to get JWT token
login_data = {'email': 'auditor.xu@test.ey.com', 'password': 'Auditor#2026'}
r = requests.post(f'{BASE}/auth/token/', json=login_data, timeout=10)
if r.status_code != 200:
    print(f'Login failed: {r.status_code} {r.text}')
    sys.exit(1)
token = r.json().get('access')
if not token:
    print(f'No access token: {r.json()}')
    sys.exit(1)

headers = {'Authorization': f'Bearer {token}', 'X-Space-Id': SPACE_ID}

# Get all documents
r = requests.get(f'{BASE}/documents/', headers=headers, timeout=30)
docs = r.json()
if isinstance(docs, dict):
    docs = docs.get('results', docs.get('items', []))

# Filter upload_test docs
test_docs = [d for d in docs if d.get('title', '').startswith('upload_test_')]
test_docs.sort(key=lambda x: x.get('title', ''))

print(f'Total test documents: {len(test_docs)}')
print('=' * 120)

results = []

for doc in test_docs:
    doc_id = doc['id']
    title = doc.get('title', '')
    status = doc.get('status', '')
    file_type = doc.get('file_type', '')
    file_size = doc.get('file_size', 0)
    chunk_count = doc.get('chunk_count', 0)
    created_at = doc.get('created_at', '')
    updated_at = doc.get('updated_at', '')

    # Calculate actual processing time from timestamps
    try:
        from datetime import datetime
        ct = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        ut = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        actual_parse_time = (ut - ct).total_seconds()
    except:
        actual_parse_time = -1

    # Get chunks
    r2 = requests.get(f'{BASE}/documents/{doc_id}/chunks/', headers=headers, timeout=60)
    chunks_data = r2.json()
    if isinstance(chunks_data, dict):
        chunks_list = chunks_data.get('results', chunks_data.get('items', []))
    else:
        chunks_list = chunks_data

    chunk_lengths = [len(c.get('content', '')) for c in chunks_list] if chunks_list else []
    avg_len = sum(chunk_lengths) / len(chunk_lengths) if chunk_lengths else 0
    min_len = min(chunk_lengths) if chunk_lengths else 0
    max_len = max(chunk_lengths) if chunk_lengths else 0

    # Content quality checks
    all_content = ' '.join(c.get('content', '') for c in chunks_list) if chunks_list else ''
    
    has_replacement_char = '\ufffd' in all_content
    has_null_bytes = '\x00' in all_content
    has_html_tags = any(tag in all_content for tag in ['<html', '<body', '<div', '<table'])
    has_markdown = any(tag in all_content for tag in ['#', '|', '```', '- '])
    # Check for binary garbage: control chars excluding \n \r \t
    has_binary_garbage = any(ord(c) < 9 or (14 <= ord(c) <= 31) for c in all_content[:5000])
    
    # Check embedding via direct vector query
    has_embedding = False
    if chunks_list:
        sample_chunk = chunks_list[0]
        emb_field = sample_chunk.get('embedding')
        if emb_field is not None:
            has_embedding = True
    
    # First and last chunk preview
    first_chunk = chunks_list[0].get('content', '')[:300] if chunks_list else ''
    last_chunk = chunks_list[-1].get('content', '')[:300] if chunks_list else ''

    # Format validation
    format_issues = []
    if file_type == 'txt' and has_html_tags:
        format_issues.append('HTML tags in TXT')
    if file_type == 'txt' and has_binary_garbage:
        format_issues.append('Binary garbage in TXT')
    if file_type == 'md' and not has_markdown and chunk_count > 0:
        format_issues.append('No markdown structure')
    
    encoding_ok = not has_replacement_char and not has_null_bytes and not has_binary_garbage

    # Content extraction ratio (how much of the original file was extracted as text)
    extraction_ratio = 0
    if file_size > 0:
        extraction_ratio = round(len(all_content) / file_size * 100, 1)

    print(f'\n--- {title} ---')
    print(f'  Type: {file_type} | Size: {file_size}B | Status: {status} | Chunks: {chunk_count}')
    print(f'  Timestamp parse time: {actual_parse_time:.3f}s')
    print(f'  Chunk lengths: avg={avg_len:.0f}, min={min_len}, max={max_len}')
    print(f'  Total content chars: {len(all_content)}')
    print(f'  Extraction ratio: {extraction_ratio}%')
    print(f'  Encoding: replacement_char={has_replacement_char}, null_bytes={has_null_bytes}, binary_garbage={has_binary_garbage}')
    print(f'  Content type: has_html_tags={has_html_tags}, has_markdown={has_markdown}')
    print(f'  Has embedding: {has_embedding}')
    print(f'  Format issues: {format_issues if format_issues else "None"}')
    print(f'  First chunk (300 chars): {first_chunk[:300]}')
    print(f'  Last chunk (300 chars): {last_chunk[:300]}')

    results.append({
        'title': title,
        'file_type': file_type,
        'file_size': file_size,
        'status': status,
        'chunk_count': chunk_count,
        'timestamp_parse_time_s': round(actual_parse_time, 3),
        'avg_chunk_length': round(avg_len, 0),
        'min_chunk_length': min_len,
        'max_chunk_length': max_len,
        'total_content_chars': len(all_content),
        'extraction_ratio_pct': extraction_ratio,
        'encoding_ok': encoding_ok,
        'has_replacement_char': has_replacement_char,
        'has_null_bytes': has_null_bytes,
        'has_binary_garbage': has_binary_garbage,
        'has_html_tags': has_html_tags,
        'has_markdown': has_markdown,
        'has_embedding': has_embedding,
        'format_issues': format_issues,
        'first_chunk_preview': first_chunk[:300],
        'last_chunk_preview': last_chunk[:300],
    })

# Summary table
print('\n' + '=' * 120)
print('SUMMARY')
print('=' * 120)
print(f'{"Doc":<30} {"Type":<6} {"Size":>8} {"Parse(s)":>10} {"Chunks":>8} {"AvgLen":>8} {"Total":>8} {"Extr%":>6} {"EncOK":>6} {"FmtOK":>6} {"Embed":>6}')
print('-' * 120)
for r in results:
    fmt_ok = 'OK' if not r['format_issues'] else 'FAIL'
    enc_ok = 'OK' if r['encoding_ok'] else 'FAIL'
    emb_ok = 'OK' if r['has_embedding'] else 'N/A'
    print(f'{r["title"]:<30} {r["file_type"]:<6} {r["file_size"]:>8} {r["timestamp_parse_time_s"]:>10.3f} {r["chunk_count"]:>8} {r["avg_chunk_length"]:>8.0f} {r["total_content_chars"]:>8} {r["extraction_ratio_pct"]:>6.1f} {enc_ok:>6} {fmt_ok:>6} {emb_ok:>6}')

# Save JSON
output = {
    'analysis_time': time.strftime('%Y-%m-%d %H:%M:%S'),
    'documents': results,
}
out_path = '/app/test_results/chunk_analysis.json'
import os
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f'\nSaved to: {out_path}')
