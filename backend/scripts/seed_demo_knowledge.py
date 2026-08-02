"""Seed demo knowledge data for visual verification (idempotent).

Populates the target space with:
- Tagged active documents across the four audit dimensions
- A version chain (v1 superseded → v2 active) with watermark fields
- A pending_review version + ReviewRequest (review queue demo)
- A stale document and an expiring effective_to document (dashboard alerts)
- Explicit DocumentLinks (graph solid edges)
- Real DocumentChunks (no embeddings) so terms metadata / graph shared-term
  edges have substance

Usage (inside backend container):
    python scripts/seed_demo_knowledge.py <space_id>
"""
import os
import sys
import uuid as _uuid

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from datetime import timedelta

from django.utils import timezone

from apps.knowledge.models import (
    Document,
    DocumentChunk,
    DocumentLink,
    DocumentTag,
    ReviewRequest,
    TaxonomyTerm,
    TermOwnership,
)
from apps.spaces.models import KnowledgeSpace
from apps.users.models import User

SPACE_ID = "9ff9f090-9a1d-4bff-8450-f7c3c06c7c8e"
for _arg in sys.argv[1:]:
    try:
        SPACE_ID = str(_uuid.UUID(_arg))
        break
    except ValueError:
        continue  # ignore non-UUID argv noise (e.g. "shell" when exec'd)

space = KnowledgeSpace.objects.get(pk=SPACE_ID)
org = space.organization
admin = User.objects.get(email="admin@test.ey.com")
author = User.objects.filter(email="fath@ey.com").first() or admin
reviewer = User.objects.filter(email="reviewer@knowpilot.local").first() or admin

now = timezone.now()


def term(code):
    t = TaxonomyTerm.objects.filter(dimension__organization=org, code=code).first()
    if t is None:
        print(f"  ! term not found: {code}")
    return t


def chunk_doc(doc):
    """(Re)create plain chunks from text_content; sync term metadata."""
    DocumentChunk.objects.filter(document=doc).delete()
    codes = list(
        DocumentTag.objects.filter(document=doc).values_list("term__code", flat=True)
    )
    for i, para in enumerate(p for p in doc.text_content.split("\n\n") if p.strip()):
        DocumentChunk.objects.create(
            document=doc,
            space=space,
            content=para.strip(),
            chunk_index=i,
            metadata={"terms": codes},
        )
    doc.chunk_count = DocumentChunk.objects.filter(document=doc).count()
    doc.save(update_fields=["chunk_count"])


def make_doc(title, body, status="active", tags=(), updated_by=None, **extra):
    doc, created = Document.objects.get_or_create(
        space=space,
        title=title,
        version=extra.get("version", 1),
        defaults=dict(
            text_content=body,
            file_type="md",
            file_size=0,
            status=status,
            uploaded_by=extra.pop("uploaded_by", author),
            updated_by=updated_by or author,
            **{k: v for k, v in extra.items() if k != "version"},
        ),
    )
    print(("created" if created else "exists "), doc.version, doc.status, "-", title)
    for code in tags:
        t = term(code)
        if t:
            DocumentTag.objects.get_or_create(
                document=doc, term=t, defaults={"tagged_by": author}
            )
    if status in ("active", "stale"):
        chunk_doc(doc)
    return doc


# --- 1. Tagged active documents -------------------------------------------
d_ar = make_doc(
    "应收账款函证程序指引",
    "# 应收账款函证程序\n\n函证是获取应收账款存在性审计证据的关键程序。选取样本时应覆盖大额与异常账户。\n\n"
    "回函差异需执行替代程序，包括检查期后收款与销售合同。相关流程见《收入循环穿行测试模板》。",
    tags=("accounts_receivable", "fy26", "year_end", "revenue_cycle"),
)

d_rev = make_doc(
    "收入循环穿行测试模板",
    "# 收入循环穿行测试\n\n从订单到收款全流程选取一笔交易执行穿行，验证关键控制点设计与执行。\n\n"
    "控制点包括信用审批、发货复核、开票与应收账款对账。",
    tags=("revenue", "accounts_receivable", "fy26", "interim", "revenue_cycle"),
)

d_cash = make_doc(
    "货币资金监盘与银行函证要点",
    "# 货币资金审计要点\n\n库存现金监盘应突击执行并双人在场。银行函证必须由审计师直接控制收发。\n\n"
    "重点关注定期存单质押与未达账项调节表。",
    tags=("cash", "fy26", "year_end"),
)

d_inv = make_doc(
    "存货监盘计划 FY25",
    "# 存货监盘计划\n\n本计划适用于 FY25 年报审计的存货监盘安排，覆盖仓库选点与抽盘比例。\n\n"
    "注意在产品完工程度的估计依据。",
    tags=("inventory", "fy25", "year_end", "inventory_cycle"),
)

# --- 2. Version chain: v1 superseded → v2 active (watermark demo) ---------
d_pay_v1 = make_doc(
    "薪酬循环控制测试底稿说明",
    "# 薪酬循环控制测试（初版）\n\n覆盖入职审批与月度薪酬计算复核两个控制点。",
    status="superseded",
    tags=("payroll_payable", "fy26", "interim", "payroll"),
    effective_to=now.date() - timedelta(days=30),
)
d_pay_v2 = make_doc(
    "薪酬循环控制测试底稿说明",
    "# 薪酬循环控制测试（修订版）\n\n覆盖入职审批、月度薪酬计算复核与离职结算三个控制点。\n\n"
    "新增：与人力系统权限矩阵的核对步骤。",
    version=2,
    tags=("payroll_payable", "fy26", "interim", "payroll"),
    parent_document=d_pay_v1,
    updated_by=admin,
    uploaded_by=admin,
)
if d_pay_v1.status != "superseded":
    d_pay_v1.status = "superseded"
    d_pay_v1.save(update_fields=["status"])
    DocumentChunk.objects.filter(document=d_pay_v1).delete()

# --- 3. Pending review version + ReviewRequest ----------------------------
d_ar_v2 = make_doc(
    "应收账款函证程序指引",
    "# 应收账款函证程序（FY26 修订稿）\n\n新增电子函证平台使用规范与回函真实性验证步骤。\n\n"
    "待审批版本：批准后才会进入 AI 索引。",
    version=2,
    status="pending_review",
    tags=("accounts_receivable", "fy26", "year_end", "revenue_cycle"),
    parent_document=d_ar,
)
rr, rr_created = ReviewRequest.objects.get_or_create(
    space=space,
    document=d_ar_v2,
    decision="pending",
    defaults=dict(
        submitted_by=author,
        diff_summary={"added_lines": 3, "removed_lines": 1, "reason": "FY26 修订"},
        conflict_hints=[],
    ),
)
print(("created" if rr_created else "exists "), "ReviewRequest pending →", d_ar_v2.title)

# --- 4. Stale + expiring documents (dashboard alerts) ----------------------
d_stale = make_doc(
    "IT 一般控制测试指引（旧）",
    "# ITGC 测试指引\n\n涵盖访问控制、变更管理与运维三大域的测试步骤。\n\n本指引长期未复核。",
    status="stale",
    tags=("fy25", "planning"),
)
Document.objects.filter(pk=d_stale.pk).update(
    updated_at=now - timedelta(days=400)
)

d_expiring = make_doc(
    "集团审计指令 FY26（有效期内）",
    "# 集团审计指令\n\n本指令适用于 FY26 集团审计，组成部分重要性分配见附表。",
    tags=("fy26", "planning"),
    effective_from=now.date() - timedelta(days=90),
    effective_to=now.date() + timedelta(days=14),
)

# --- 5. Explicit links (graph solid edges) ---------------------------------
for src, tgt, anchor in [
    (d_ar, d_rev, "收入循环穿行测试模板"),
    (d_rev, d_pay_v2, "薪酬循环控制测试底稿说明"),
    (d_expiring, d_cash, "货币资金监盘与银行函证要点"),
]:
    _, lc = DocumentLink.objects.get_or_create(
        space=space, source=src, target=tgt, defaults={"anchor_text": anchor}
    )
    print(("created" if lc else "exists "), "link", src.title, "→", tgt.title)

# --- 6. Term ownership (my-terms view) --------------------------------------
t_ar = term("accounts_receivable")
if t_ar:
    _, oc = TermOwnership.objects.get_or_create(space=space, term=t_ar, owner=author)
    print(("created" if oc else "exists "), "TermOwnership accounts_receivable →", author.email)

print("done. docs in space:", Document.objects.filter(space=space).count())
