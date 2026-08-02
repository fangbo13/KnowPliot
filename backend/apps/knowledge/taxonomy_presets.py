# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""KB optimization spec §2.1 / §3.1 — reusable taxonomy presets.

A *preset* is a named, in-code blueprint of dimensions + terms that a space can
seed as its own private taxonomy (``taxonomy_mode="space"``). This decouples
"the audit line's default account tree" from the shared, platform-managed
dimensions so each project team gets an editable, isolated copy.

``seed_space_taxonomy`` copies a preset into ``TaxonomyDimension`` /
``TaxonomyTerm`` rows scoped to a single space. It is idempotent
(get_or_create) so re-running never duplicates rows.
"""

from __future__ import annotations

from django.db import transaction

# (code, label, [children]) — mirrors seed_audit_taxonomy's ACCOUNT_TREE.
_AUDIT_ACCOUNT_TREE = [
    ("assets", "资产类", [
        ("cash", "货币资金"),
        ("accounts_receivable", "应收账款"),
        ("inventory", "存货"),
        ("fixed_assets", "固定资产"),
    ]),
    ("profit_loss", "损益类", [
        ("revenue", "收入"),
        ("expenses", "费用"),
        ("cost_of_sales", "营业成本"),
    ]),
    ("liabilities", "负债类", [
        ("accounts_payable", "应付账款"),
        ("payroll_payable", "应付职工薪酬"),
    ]),
]
_AUDIT_FISCAL_YEARS = [("fy25", "FY25"), ("fy26", "FY26"), ("fy27", "FY27")]
_AUDIT_PHASES = [
    ("planning", "计划阶段"),
    ("interim", "中期审计"),
    ("year_end", "年末审计"),
]
_AUDIT_SCOT = [
    ("revenue_cycle", "收入循环"),
    ("purchase_payment", "采购付款"),
    ("payroll", "薪酬循环"),
    ("inventory_cycle", "存货循环"),
    ("financial_reporting", "财报编制"),
]


def _flat(pairs):
    return [{"code": c, "label": lab} for c, lab in pairs]


def _tree(nodes):
    out = []
    for code, label, children in nodes:
        out.append({"code": code, "label": label, "children": _flat(children)})
    return out


# preset_code → {name, dimensions: [{code, name, is_hierarchical, required, terms}]}
# terms is a list of {code, label, children?}.
TAXONOMY_PRESETS: dict[str, dict] = {
    "audit_default": {
        "name": "审计默认科目",
        "description": "会计科目 / 财年 / 审计阶段 / SCOT 流程",
        "dimensions": [
            {
                "code": "account", "name": "会计科目",
                "is_hierarchical": True, "required": True, "sort_order": 1,
                "terms": _tree(_AUDIT_ACCOUNT_TREE),
            },
            {
                "code": "fiscal_year", "name": "财年",
                "is_hierarchical": False, "required": True, "sort_order": 2,
                "terms": _flat(_AUDIT_FISCAL_YEARS),
            },
            {
                "code": "audit_phase", "name": "审计阶段",
                "is_hierarchical": False, "required": False, "sort_order": 3,
                "terms": _flat(_AUDIT_PHASES),
            },
            {
                "code": "scot", "name": "SCOT 流程",
                "is_hierarchical": False, "required": False, "sort_order": 4,
                "terms": _flat(_AUDIT_SCOT),
            },
        ],
    },
}


def list_presets() -> list[dict]:
    """Return preset catalog for the creation wizard (code/name/description/tree)."""
    return [
        {
            "code": code,
            "name": preset["name"],
            "description": preset.get("description", ""),
            "dimensions": [
                {
                    "code": d["code"],
                    "name": d["name"],
                    "required": d.get("required", False),
                    "is_hierarchical": d.get("is_hierarchical", False),
                    "terms": d.get("terms", []),
                }
                for d in preset["dimensions"]
            ],
        }
        for code, preset in TAXONOMY_PRESETS.items()
    ]


def get_preset(preset_code: str) -> dict | None:
    return TAXONOMY_PRESETS.get(preset_code)


@transaction.atomic
def seed_space_taxonomy(space, preset_code: str = "audit_default") -> int:
    """Copy a preset into space-private dimensions/terms. Idempotent.

    Returns the number of dimensions created (0 if the preset is unknown or all
    dimensions already exist).
    """
    from .models import TaxonomyDimension, TaxonomyTerm

    preset = TAXONOMY_PRESETS.get(preset_code)
    if preset is None:
        return 0

    created_dims = 0
    for dim_spec in preset["dimensions"]:
        dimension, dim_created = TaxonomyDimension.objects.get_or_create(
            space=space,
            organization_id=space.organization_id,
            code=dim_spec["code"],
            defaults={
                "name": dim_spec["name"],
                "is_hierarchical": dim_spec.get("is_hierarchical", False),
                "required": dim_spec.get("required", False),
                "sort_order": dim_spec.get("sort_order", 0),
            },
        )
        if dim_created:
            created_dims += 1

        def _create_terms(terms, parent=None):
            for i, term_spec in enumerate(terms):
                term, _ = TaxonomyTerm.objects.get_or_create(
                    dimension=dimension,
                    code=term_spec["code"],
                    defaults={
                        "label": term_spec["label"],
                        "parent": parent,
                        "sort_order": i,
                    },
                )
                children = term_spec.get("children") or []
                if children:
                    _create_terms(children, parent=term)

        _create_terms(dim_spec.get("terms", []))

    return created_dims
