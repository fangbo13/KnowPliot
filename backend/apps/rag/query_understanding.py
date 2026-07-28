# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Knowledge iteration spec §4 L4 — lightweight query understanding.

Regex + controlled-vocabulary matching over the query text. Recognised
entities (FY / account / SCOT / audit phase terms) are attached as soft
signals: matched term codes boost same-tagged chunks during rerank, and a
fiscal-year mention downweights chunks tagged with a *different* FY
(never a hard exclusion — history stays retrievable).

No LLM call, deterministic, cheap (one indexed query on TaxonomyTerm).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# FY26 / FY 2026 / 26财年 / 2026财年 patterns → canonical "fyNN" code.
FY_PATTERN = re.compile(r"(?:fy\s*|财年\s*)?(20)?(\d{2})\s*(?:财年|fiscal year)?", re.IGNORECASE)
EXPLICIT_FY_PATTERN = re.compile(r"fy\s*(20)?(\d{2})|(20)?(\d{2})\s*财年", re.IGNORECASE)


@dataclass(frozen=True)
class QuerySignals:
    """Detected soft retrieval signals for one query."""

    term_codes: tuple[str, ...] = ()
    fiscal_year_codes: tuple[str, ...] = ()
    matched_labels: tuple[str, ...] = field(default=())
    # P2 §A4: labels + controlled synonyms of matched terms — used to expand
    # the lexical query (e.g. 坏账准备 ↔ 信用减值损失).
    expansion_terms: tuple[str, ...] = field(default=())

    @property
    def has_signals(self) -> bool:
        return bool(self.term_codes or self.fiscal_year_codes)


def _detect_fiscal_years(query: str) -> list[str]:
    codes = []
    for match in EXPLICIT_FY_PATTERN.finditer(query):
        two_digit = match.group(2) or match.group(4)
        if two_digit:
            codes.append(f"fy{two_digit}")
    return codes


def analyze_query(query: str, *, space_id: str) -> QuerySignals:
    """Match query text against the space's org-scoped controlled vocabulary."""
    try:
        from apps.knowledge.models import TaxonomyTerm
        from apps.spaces.models import KnowledgeSpace

        space = KnowledgeSpace.objects.filter(id=space_id).only("organization_id").first()
        if space is None:
            return QuerySignals()

        query_lower = (query or "").lower()
        fy_codes = _detect_fiscal_years(query_lower)

        matched_codes: list[str] = []
        matched_labels: list[str] = []
        expansion_terms: list[str] = []
        terms = TaxonomyTerm.objects.filter(
            dimension__organization_id=space.organization_id,
            status="active",
        ).select_related("dimension").only(
            "code", "label", "synonyms", "dimension__code"
        )
        for term in terms:
            label = (term.label or "").lower()
            code_text = term.code.replace("_", " ").replace("-", " ")
            # P2 §A4: controlled synonyms count as matches too.
            synonyms = [
                s for s in (term.synonyms or []) if isinstance(s, str) and s.strip()
            ]
            synonym_hit = any(s.lower() in query_lower for s in synonyms)
            if (label and label in query_lower) or (
                len(code_text) >= 4 and code_text in query_lower
            ) or synonym_hit:
                matched_codes.append(term.code)
                matched_labels.append(term.label)
                expansion_terms.append(term.label)
                expansion_terms.extend(synonyms)
                if term.dimension.code == "fiscal_year" and term.code not in fy_codes:
                    fy_codes.append(term.code)

        # FY codes detected by regex count as term matches too (boost same-FY).
        for fy in fy_codes:
            if fy not in matched_codes:
                matched_codes.append(fy)

        return QuerySignals(
            term_codes=tuple(dict.fromkeys(matched_codes)),
            fiscal_year_codes=tuple(dict.fromkeys(fy_codes)),
            matched_labels=tuple(dict.fromkeys(matched_labels)),
            expansion_terms=tuple(dict.fromkeys(expansion_terms)),
        )
    except Exception as exc:  # pragma: no cover — QU is a soft enhancement
        logger.warning("analyze_query failed: %s", exc)
        return QuerySignals()
