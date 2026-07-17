# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Small, pure helpers shared by environment-backed settings."""

from __future__ import annotations

import os
from collections.abc import Mapping


def env_bool(
    name: str,
    *,
    default: bool = False,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Read a boolean flag; only explicit true spellings enable it."""

    source = os.environ if environ is None else environ
    value = source.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
