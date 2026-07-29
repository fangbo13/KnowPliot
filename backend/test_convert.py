import os, django, json, tempfile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from django.test import Client

c = Client(HTTP_HOST='localhost')

# 1. Login
r = c.post('/api/v1/auth/token/',
           data='{"email":"admin@test.ey.com","password":"admin123"}',
           content_type='application/json')
token = json.loads(r.content)['access']
print('Login:', r.status_code)

# 2. Create a valid PDF (>1KB)
pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 100 700 Td (Hello KnowPilot Test) Tj ET
endstream
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
"""
# Pad to >1KB
pdf += b'\n' * 600

f = tempfile.NamedTemporaryFile(suffix='.pdf')
f.write(pdf)
f.seek(0)
print('PDF size:', len(pdf), 'bytes')

# 3. Test conversion endpoint
r2 = c.post('/api/v1/documents/convert/',
            data={'file': f},
            HTTP_AUTHORIZATION='Bearer ' + token)
print('Convert STATUS:', r2.status_code)
print('Convert BODY:', r2.content[:1000].decode('utf-8', errors='replace'))
f.close()
