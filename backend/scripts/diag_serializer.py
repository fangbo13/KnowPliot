import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from django.conf import settings

from apps.chat.serializers import ChatMessageRequestSerializer
from apps.chat.views import _canonical_selected_libraries
from apps.knowledge.models import ReferenceLibrary
from apps.spaces.models import KnowledgeSpace

print("CHAT_SESSION_LIBRARY_SELECTION_ENABLED =",
      getattr(settings, "CHAT_SESSION_LIBRARY_SELECTION_ENABLED", "MISSING"))
print("CHAT_LIBRARY_MAX_FAST =", getattr(settings, "CHAT_LIBRARY_MAX_FAST", "MISSING"))

project = KnowledgeSpace.objects.get(code="innomed-ipo-2026")
policy = ReferenceLibrary.objects.get(space__code="policy-public-lib")

# Serializer: does selected_library_ids survive into validated_data?
s = ChatMessageRequestSerializer(data={
    "content": "差旅住宿上限",
    "answer_mode": "fast",
    "selected_library_ids": [str(policy.id)],
})
print("valid:", s.is_valid(), "errors:", s.errors)
print("'selected_library_ids' in validated_data:",
      "selected_library_ids" in s.validated_data)
print("validated value:", s.validated_data.get("selected_library_ids"))

# _canonical with the validated value
canon = _canonical_selected_libraries(
    project, s.validated_data.get("selected_library_ids"), "fast"
)
print("_canonical ->", canon)
