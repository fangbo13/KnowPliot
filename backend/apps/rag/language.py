# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Post-V3 Part 4: AI reply-language resolution (bilingual).

Resolution order (high -> low):
1. User `language_preference` explicit override (zh/en beats detection).
2. Query-language auto-detection (primary when user pref is auto): zh query
   -> zh reply; en query -> en reply.
3. Space `default_language` (auto/zh/en, default auto) fallback when the
   query is inconclusive.

KB content language MUST NOT drive reply language. The system prompt uses a
dynamic "Respond in {resolved_language}" instruction (no hardcoded "en").
"""

import re

LANGUAGE_AUTO = "auto"
LANGUAGE_ZH = "zh"
LANGUAGE_EN = "en"

# CJK Unified Ideographs + CJK Extension A + CJK Compatibility Ideographs +
# Hiragana/Katakana + Hangul. A query containing any CJK character is
# treated as Chinese.
_CJK_RE = re.compile(
    r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]"
)


def detect_query_language(text):
    """Detect the query language from its text.

    Returns LANGUAGE_ZH if CJK characters are present, LANGUAGE_EN for a
    non-empty query without CJK, and LANGUAGE_AUTO for an empty/whitespace
    query (so the space default fallback can apply).
    """
    if not text or not text.strip():
        return LANGUAGE_AUTO
    if _CJK_RE.search(text):
        return LANGUAGE_ZH
    return LANGUAGE_EN


def resolve_reply_language(query, user, space=None):
    """Resolve the AI reply language for a chat turn.

    Order: user.language_preference (explicit zh/en) overrides detection;
    otherwise query-language detection; otherwise space.default_language
    (explicit zh/en); otherwise LANGUAGE_EN.
    """
    user_pref = getattr(user, "language_preference", LANGUAGE_AUTO)
    if user_pref in (LANGUAGE_ZH, LANGUAGE_EN):
        return user_pref

    detected = detect_query_language(query)
    if detected in (LANGUAGE_ZH, LANGUAGE_EN):
        return detected

    if space is not None:
        space_default = getattr(space, "default_language", LANGUAGE_AUTO)
        if space_default in (LANGUAGE_ZH, LANGUAGE_EN):
            return space_default

    return LANGUAGE_EN
