import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from apps.chat.models import ChatSession, ChatTurn
from apps.knowledge.models import ReferenceLibrary, SpaceLibraryReference
from apps.rag.library_routing import resolve_selected_libraries
from apps.rag.retriever import PgVectorRetriever
from apps.rag.hybrid import HybridRetriever
from apps.spaces.models import KnowledgeSpace

project = KnowledgeSpace.objects.get(code="innomed-ipo-2026")
policy = ReferenceLibrary.objects.get(space__code="policy-public-lib")
print("project space:", project.id)
print("policy library id:", policy.id, "policy space:", policy.space_id)

# 1) Does resolve return the policy library space?
space_ids, names = resolve_selected_libraries(project, [str(policy.id)], 1)
print("resolve_selected_libraries ->", space_ids, names)

# 2) Session B snapshot
sess = ChatSession.objects.filter(space=project, title="B-Fast-制度库").order_by("-created_at").first()
if sess:
    print("session B reference_library_ids:", sess.reference_library_ids)
    turn = ChatTurn.objects.filter(session=sess).order_by("started_at").first()
    if turn:
        print("first turn reference_library_ids:", turn.reference_library_ids)

# 3) Retrieve across primary + policy space for a reimbursement question
retriever = HybridRetriever(vector_retriever=PgVectorRetriever())
results = retriever.search(
    query="差旅住宿一线城市报销上限是多少",
    space_id=str(project.id),
    space_ids=[str(project.id), *space_ids],
    top_k=8,
    similarity_threshold=0.55,
)
print(f"\nretrieved {len(results)} chunks:")
for r in results:
    print(" -", str(r.get("space_id"))[:8], (r.get("content") or "")[:50])
