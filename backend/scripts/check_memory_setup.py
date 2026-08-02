import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from django.conf import settings  # noqa: E402

from apps.chat.memory import build_memory_context  # noqa: E402,F401
from apps.chat.models import SessionMemory  # noqa: E402

print(
    "CHAT_MEMORY_ENABLED=", settings.CHAT_MEMORY_ENABLED,
    "TOKEN_BUDGET=", settings.CHAT_HISTORY_TOKEN_BUDGET,
    "QUERY_REWRITE=", settings.CHAT_QUERY_REWRITE_ENABLED,
    "MULTI_TURN=", settings.CHAT_MULTI_TURN_MESSAGES,
)
print("SessionMemory rows:", SessionMemory.objects.count())
