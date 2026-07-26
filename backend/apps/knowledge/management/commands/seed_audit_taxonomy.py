# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Seed the audit business line's controlled taxonomy (spec §2).

Creates the four preset dimensions for the assurance (审计) line:
  - account       会计科目 (hierarchical, required)
  - fiscal_year   财年 (organization-wide, required)
  - audit_phase   审计阶段
  - scot          SCOT 流程

Run after migrations:  python manage.py seed_audit_taxonomy
Safe to re-run: existing records are skipped (get_or_create).
"""

from django.core.management.base import BaseCommand

from apps.knowledge.models import TaxonomyDimension, TaxonomyTerm
from apps.spaces.models import BusinessLine, Organization

# (code, label, children)
ACCOUNT_TREE = [
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
FISCAL_YEARS = [("fy25", "FY25"), ("fy26", "FY26"), ("fy27", "FY27")]
AUDIT_PHASES = [
    ("planning", "计划阶段"),
    ("interim", "中期审计"),
    ("year_end", "年末审计"),
]
SCOT_PROCESSES = [
    ("revenue_cycle", "收入循环"),
    ("purchase_payment", "采购付款"),
    ("payroll", "薪酬循环"),
    ("inventory_cycle", "存货循环"),
    ("financial_reporting", "财报编制"),
]


class Command(BaseCommand):
    help = "Seed the assurance line's controlled metadata taxonomy (spec §2)."

    def handle(self, *args, **options):
        out = self.stdout
        org = Organization.objects.order_by("created_at").first()
        if org is None:
            org, _ = Organization.objects.get_or_create(
                slug="default", defaults={"name": "KnowPilot Demo Org"}
            )
        audit_bl = BusinessLine.objects.filter(
            organization=org, code="assurance"
        ).first()
        if audit_bl is None:
            audit_bl, _ = BusinessLine.objects.get_or_create(
                organization=org, code="assurance", defaults={"name": "Assurance"}
            )
        out.write(f"Seeding audit taxonomy for org={org.slug} bl={audit_bl.code}...")

        def get_or_create_dimension(*, code, name, business_line, **defaults):
            dim, created = TaxonomyDimension.objects.get_or_create(
                organization=org,
                business_line=business_line,
                code=code,
                defaults={"name": name, **defaults},
            )
            out.write(f"  {'+' if created else '='} Dimension: {code}")
            return dim

        def get_or_create_term(dim, code, label, *, parent=None, sort_order=0):
            term, created = TaxonomyTerm.objects.get_or_create(
                dimension=dim,
                code=code,
                defaults={"label": label, "parent": parent, "sort_order": sort_order},
            )
            out.write(f"    {'+' if created else '='} Term: {code}")
            return term

        # 1. 会计科目 — hierarchical + required.
        account = get_or_create_dimension(
            code="account", name="会计科目", business_line=audit_bl,
            is_hierarchical=True, required=True, sort_order=1,
        )
        for i, (code, label, children) in enumerate(ACCOUNT_TREE):
            parent = get_or_create_term(account, code, label, sort_order=i)
            for j, (child_code, child_label) in enumerate(children):
                get_or_create_term(
                    account, child_code, child_label, parent=parent, sort_order=j
                )

        # 2. 财年 — organization-wide (business_line=None) + required.
        fiscal_year = get_or_create_dimension(
            code="fiscal_year", name="财年", business_line=None,
            required=True, sort_order=2,
        )
        for i, (code, label) in enumerate(FISCAL_YEARS):
            get_or_create_term(fiscal_year, code, label, sort_order=i)

        # 3. 审计阶段.
        audit_phase = get_or_create_dimension(
            code="audit_phase", name="审计阶段", business_line=audit_bl, sort_order=3,
        )
        for i, (code, label) in enumerate(AUDIT_PHASES):
            get_or_create_term(audit_phase, code, label, sort_order=i)

        # 4. SCOT 流程.
        scot = get_or_create_dimension(
            code="scot", name="SCOT 流程", business_line=audit_bl, sort_order=4,
        )
        for i, (code, label) in enumerate(SCOT_PROCESSES):
            get_or_create_term(scot, code, label, sort_order=i)

        out.write(self.style.SUCCESS("[OK] seed_audit_taxonomy complete."))
