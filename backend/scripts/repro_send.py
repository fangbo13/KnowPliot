import os
import sys
import uuid

import django
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from apps.chat.models import ChatSession
from apps.knowledge.models import ReferenceLibrary
from apps.spaces.models import KnowledgeSpace

BASE = "http://localhost:8000/api/v1"
project = KnowledgeSpace.objects.get(code="innomed-ipo-2026")
policy = ReferenceLibrary.objects.get(space__code="policy-public-lib")
SPACE_ID = str(project.id)

with httpx.Client(timeout=60) as c:
    tok = c.post(f"{BASE}/auth/token/", json={
        "email": "auditor.xu@test.ey.com", "password": "Auditor#2026"}).json()["access"]
    h = {"Authorization": f"Bearer {tok}", "X-Space-Id": SPACE_ID}
    sid = c.post(f"{BASE}/chat/sessions/", json={"title": "REPRO-libsel"}, headers=h).json()["id"]
    print("session:", sid)
    body = {
        "content": "差旅住宿一线城市报销上限是多少？",
        "client_request_id": str(uuid.uuid4()),
        "answer_mode": "fast",
        "selected_library_ids": [str(policy.id)],
    }
    answer = []
    with c.stream("POST", f"{BASE}/chat/sessions/{sid}/send/", json=body, headers=h, timeout=120) as r:
        print("status:", r.status_code)
        ev = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and ev == "token":
                import json as J
                try:
                    answer.append(J.loads(line.split(":", 1)[1].strip()).get("token", ""))
                except Exception:
                    pass
    print("answer:", "".join(answer)[:120])

sess = ChatSession.objects.get(id=sid)
print("STORED reference_library_ids:", sess.reference_library_ids)
