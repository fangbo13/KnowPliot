import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from apps.chat.models import SessionMemory

memory = SessionMemory.objects.filter(
    session_id="a9ba0876-ea81-468f-ac5d-2961327ce390"
).first()
if memory is None:
    print("NOT FOUND")
else:
    print(f"version={memory.summary_version} until={memory.summarized_until}")
    print("--- summary ---")
    print(memory.summary)
    print("--- key_facts ---")
    for fact in memory.key_facts:
        print("-", fact)
