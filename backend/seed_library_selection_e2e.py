"""Seed data for the session-library-selection E2E.

Idempotent. Ensures FOUR published public reference libraries (so Deep's
cap of 3 leaves a 4th disabled for a clean boundary test), builds a fresh
"from-0" project space with multi-dimensional project knowledge, and opts
that space into all four libraries via the SAME helper the workspace-creation
flow uses (_apply_reference_library_optin).

Run: docker compose exec -T backend python seed_library_selection_e2e.py
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.knowledge.models import Document, ReferenceLibrary, SpaceLibraryReference
from apps.rag.pipeline import RAGPipeline
from apps.spaces.creation_services import _apply_reference_library_optin
from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership
from apps.spaces.ownership import create_space_with_owner

User = get_user_model()

admin = User.objects.filter(is_superuser=True).order_by("date_joined").first()
org = Organization.objects.order_by("created_at").first()
print(f"admin={admin.email if admin else None} org={org.name if org else None}")

auditor = User.objects.filter(email="auditor.xu@test.ey.com").first()

# ── Public reference libraries (4 total, all published) ──────────────
PUBLIC_LIBS = [
    ("ifrs-reference-lib", "IFRS 参考库", "ifrs", [
        ("IFRS 15 收入确认", "IFRS 15 规定五步法收入确认模型：识别合同、识别履约义务、确定交易价格、分摊价格、在履约义务满足时确认收入。"),
        ("IFRS 16 租赁", "IFRS 16 要求承租人对几乎所有租赁确认使用权资产和租赁负债，短期租赁和低价值租赁可豁免。"),
    ]),
    ("policy-public-lib", "公司制度公共参考库", "policy", [
        ("差旅与报销管理制度", "一线城市住宿不超过650元/晚；餐补120元/天；报销须在行程结束后15个工作日内提交；单笔超5000元需签字合伙人审批。"),
    ]),
    ("cas-reference-lib", "中国会计准则参考库", "cas", [
        ("企业会计准则第14号-收入", "企业应当在履行了合同中的履约义务，即在客户取得相关商品控制权时确认收入。"),
        ("企业会计准则第8号-资产减值", "资产存在减值迹象的，应当估计其可收回金额；可收回金额低于账面价值的，计提减值准备。"),
    ]),
    ("ipo-cases-lib", "IPO 案例参考库", "ipo_cases", [
        ("科创板IPO审核要点", "科创板重点关注科创属性、收入确认合规性、研发费用资本化、关联交易与资金占用、内控有效性。"),
        ("IPO收入核查案例", "对经销模式收入，审核关注终端销售真实性、退货率异常、期末压货与跨期确认风险。"),
    ]),
]


def ensure_space(code, name):
    space = KnowledgeSpace.objects.filter(code=code).first()
    if space is None:
        space = create_space_with_owner(
            organization=org, owner=admin, name=name, code=code,
            visibility="organization",
        )
        print(f"[NEW] space {name} ({code})")
    SpaceMembership.objects.get_or_create(
        space=space, user=admin,
        defaults={"role": SpaceMembership.ROLE_OWNER, "status": "active"},
    )
    return space


def seed_docs(space, docs):
    pipeline = RAGPipeline(ingestion=True)
    for title, body in docs:
        doc = Document.objects.filter(space=space, title=title).first()
        if doc is None:
            doc = Document.objects.create(
                space=space, title=title, text_content=body,
                file_type="md", file_size=0, uploaded_by=admin, status="draft",
            )
        elif doc.text_content != body:
            doc.text_content = body
            doc.save(update_fields=["text_content"])
        if doc.chunk_count and doc.status == "active":
            continue
        chunks = pipeline.ingest_text_content(doc)
        doc.chunk_count = len(chunks)
        doc.status = "active" if chunks else "failed"
        doc.save(update_fields=["chunk_count", "status"])
        print(f"  ~ {title}: {len(chunks)} chunks")


library_ids = []
for code, name, category, docs in PUBLIC_LIBS:
    lib_space = ensure_space(code, name)
    seed_docs(lib_space, docs)
    library, _ = ReferenceLibrary.objects.get_or_create(
        space=lib_space,
        defaults=dict(name=name, category=category, status="published",
                      published_by=admin, published_at=timezone.now()),
    )
    changed = False
    if library.status != "published":
        library.status = "published"
        library.published_at = library.published_at or timezone.now()
        changed = True
    if library.category != category:
        library.category = category
        changed = True
    if changed:
        library.save()
    library_ids.append(str(library.id))
    print(f"library ready: {name} [{category}/{library.status}]")

# ── Fresh "from-0" project space with multi-dimensional knowledge ────
PROJECT_DOCS = [
    ("项目立项备忘", """# 创新药械2026 IPO审计项目 - 立项备忘

- 客户：创新药械股份有限公司（专注高端医疗器械研发与生产，总部苏州）。
- 拟上市板块：科创板。审计期间：2024-2026 三个报告期。
- 签字合伙人：陈志远；质量复核合伙人：林晚；项目经理：苏敏；现场负责人：郑凯。
- 进场时间：2026-09-01，预计外勤 6 周。
- 客户对接：财务总监 何军、财务经理 徐蕾。
- 关键风险：研发支出资本化、收入确认（经销+直销）、关联方与资金占用、存货减值。"""),
    ("研发支出资本化政策", """# 研发支出资本化政策与审计关注

- 公司将研究阶段支出费用化，开发阶段满足资本化条件后计入无形资产。
- 2025年资本化开发支出 8600 万元，占研发投入 42%。
- 审计关注：资本化时点是否恰当、技术可行性与经济利益流入证据、后续摊销与减值。
- 重点核查三个在研项目的可行性报告、里程碑验收记录与预算执行。"""),
    ("收入循环与经销模式", """# 收入循环与经销模式核查

- 收入构成：直销占 55%，经销占 45%。
- 经销商信用期 90 天，期末存在压货风险；2025Q4 退货率 5.2%，高于前三季度均值 2.1%。
- 审计程序：细节测试样本 80 笔（Q4 加权）；截止测试年结日前后各 20 笔；前十大经销商函证 + 走访。
- 直播电商为新渠道，关注收入确认时点与平台结算单核对。"""),
    ("关联方与资金占用", """# 关联方交易与资金占用

- 识别关联方 23 家，其中 5 家发生经常性交易。
- 关注实控人及其近亲属控制企业的采购、销售与拆借。
- 报告期内曾存在向关联方短期拆借 3000 万元，已于 2025 年末清理归还。
- 审计程序：关联方完整性测试、定价公允性分析、资金流水穿行。"""),
    ("内部控制与关键审计事项", """# 内部控制评价与关键审计事项候选

- IT 一般控制：ERP 权限、变更管理、数据备份；关注收入接口自动化控制。
- 关键审计事项候选：一、研发支出资本化；二、收入确认（经销退货与跨期）；三、存货减值。
- 存货：库龄超一年的电子元器件与试剂存在减值风险，上年计提 900 万元。
- 下次风险评估会议定于进场后第二周。"""),
]

project = ensure_space("innomed-ipo-2026", "创新药械2026 IPO审计项目")
seed_docs(project, PROJECT_DOCS)

# Opt the fresh space into all 4 public libraries via the creation helper.
_apply_reference_library_optin(project, library_ids, admin)
enabled = SpaceLibraryReference.objects.filter(space=project, enabled=True).count()
print(f"project opted into {enabled} public libraries")

if auditor is not None:
    SpaceMembership.objects.get_or_create(
        space=project, user=auditor,
        defaults={"role": SpaceMembership.ROLE_MEMBER, "status": "active"},
    )
    print(f"auditor.xu is a member of {project.name}")

print(f"PROJECT_SPACE_ID={project.id}")
print("DONE")
