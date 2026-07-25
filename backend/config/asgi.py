# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""ASGI config.

The Django application includes native async chat-v3 streaming views. They
must remain behind an ASGI server so Redis blocking reads do not consume a
synchronous request worker.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
application = get_asgi_application()
