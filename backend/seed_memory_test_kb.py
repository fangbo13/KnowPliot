"""Seed a public policy reference library + a project space for the
session-memory 20-30 round conversation test.

Idempotent. Creates:
  - Public library space 公司制度公共参考库 (policy category, published,
    5 multi-dimension docs written from a real employee's perspective).
  - Project space 星辰科技2026年报审计项目 (5 project docs).
  - The project space opts in to the policy library (+ existing IFRS lib).
  - All docs are chunked + embedded via ingest_text_content (real DashScope).

Run: docker compose exec -T backend python seed_memory_test_kb.py
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.knowledge.models import Document, ReferenceLibrary, SpaceLibraryReference
from apps.rag.pipeline import RAGPipeline
from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership
from apps.spaces.ownership import create_space_with_owner

User = get_user_model()

admin = User.objects.filter(is_superuser=True).order_by("date_joined").first()
if admin is None:
    admin = User.objects.filter(email="admin@test.ey.com").first()
org = Organization.objects.order_by("created_at").first()
print(f"admin={admin.email if admin else None} org={org.name if org else None}")

PUBLIC_DOCS = [
    ("差旅与报销管理制度", """# 差旅与报销管理制度（2026版）

大家好，我是行政部的陈静。这份制度是 2026 年 3 月修订后的最新版本，出差前请务必读一遍，能省去很多来回补材料的麻烦。

## 一、住宿标准
1. 一线城市（北京、上海、广州、深圳）：不超过 650 元/晚。
2. 其他城市：不超过 450 元/晚。
3. 超标部分原则上自理；确因客户现场或安全原因超标的，需项目经理事前邮件批准。

## 二、餐费补贴
出差期间餐补为 120 元/天，按自然天计算，无需发票，随报销单一并发放。

## 三、交通
1. 高铁二等座、经济舱为默认标准。
2. 市内打车必须取得发票或电子行程单，拼车截图不作为报销凭证。

## 四、报销时限与审批
1. 报销必须在行程结束后 15 个工作日内提交，逾期系统自动关闭入口。
2. 审批链：直属经理审批 → 财务复核。
3. 单笔金额超过 5000 元的报销，需额外经签字合伙人审批。
4. 财务复核通过后，款项在 7 个工作日内打入工资卡。

有疑问可以直接在行政服务台提单，或者找我（chenjing@ey-demo.com）。"""),
    ("考勤与休假制度", """# 考勤与休假制度

人力资源部 王悦 整理。以下是大家最常问的几个点，完整版见员工手册第 4 章。

## 一、工作时间
实行弹性工作制：核心工作时间为 10:00 - 16:00，其余时间可弹性安排，每日工作时长不少于 8 小时。

## 二、年假
1. 入职满 1 年：10 个工作日。
2. 入职满 5 年：15 个工作日。
3. 入职满 10 年：20 个工作日。
4. 年假按自然年计算，最多可结转 5 天至次年 3 月 31 日前使用。

## 三、病假
1. 病假需在 48 小时内于系统提交医疗证明。
2. 连续病假超过 3 天的，需二级及以上医院证明。
3. 病假期间薪酬按当地法规执行。

## 四、忙季调休
审计忙季（1-4 月）加班以调休为主，调休需在 6 月 30 日前使用完毕。"""),
    ("信息安全与数据保护规范", """# 信息安全与数据保护规范

IT 安全组 刘凯。去年我们处理了 3 起客户数据误发事件，都是可以避免的。请记住下面这些红线。

## 一、账号与密码
1. 域账号密码每 90 天强制更换，不得与前 5 次重复。
2. 必须启用 MFA 双因素认证。

## 二、客户数据
1. 客户数据必须存放在加密盘（BitLocker/VeraCrypt）中，禁止存放在个人云盘。
2. 严禁使用个人邮箱（QQ/163/Gmail 等）发送任何客户资料。
3. 对外发送客户数据需走安全传输平台并设置 7 天有效期。

## 三、泄露事件上报
一旦发现或怀疑数据泄露，必须在 30 分钟内上报 IT 安全组（secops@ey-demo.com），
同时通知项目签字合伙人。隐瞒不报属于一级违规。

## 四、办公环境
离开工位必须锁屏（Win+L）；打印客户资料需当场取走，会议室白板用后擦除。"""),
    ("新员工入职指南", """# 新员工入职指南

欢迎加入！我是你们的入职伙伴计划负责人 林晓。这份指南帮你度过第一个月。

## 第一周要做的事
1. 领取电脑并完成安全基线配置（IT 服务台，A 座 3 层）。
2. 完成 4 门必修合规课程（反洗钱、独立性、信息安全、职业道德）。
3. 和你的导师（buddy）见面——每位新人都会分配一位入职满 2 年以上的导师。

## 试用期
1. 试用期为 6 个月。
2. 第 3 个月有一次中期反馈面谈，第 6 个月进行转正答辩。
3. 转正答辩由部门经理 + HRBP 参加，主要看项目表现与合规记录。

## 常用系统
- 报销：Concur
- 考勤请假：Workday
- 知识库：KnowPilot（就是你现在用的这个）

任何问题先问导师，导师解决不了的找我（linxiao@ey-demo.com）。"""),
    ("会议室与办公资源使用规定", """# 会议室与办公资源使用规定

行政部提醒：

## 会议室
1. 通过 Outlook 预订，30 分钟未签到自动释放。
2. 8 人以上会议室优先保障客户会议，内部会议请使用小型讨论间。

## 办公用品
每月 25 日统一发放，紧急需求走行政服务台加急单。

## 访客
客户来访需提前 1 个工作日在系统登记，前台打印访客证；访客全程需员工陪同。"""),
]

PROJECT_DOCS = [
    ("项目基本信息备忘", """# 星辰科技2026年报审计 - 项目基本信息备忘

整理人：项目经理 李婷（2026-07-20）

- 客户全称：星辰科技股份有限公司（智能硬件制造，总部深圳南山）。
- 审计期间：2026 财年年报审计（截至 2026-12-31）。
- 签字合伙人：王强；质量复核合伙人：赵敏。
- 项目经理：李婷；现场负责人：周浩。
- 进场时间：2026-08-10；预计外勤 4 周（至 9 月上旬）。
- 客户对接人：财务总监 张伟、财务经理 孙丽。
- 上年审计意见：标准无保留意见。
- 本年重点关注：收入确认、存货减值、应收账款可回收性。"""),
    ("收入循环审计计划", """# 收入循环审计计划

编制：周浩；复核：李婷（2026-07-25）

## 重点风险
1. 经销商渠道压货导致的收入跨期风险（舞弊推定风险）。
2. 年末大额退货：星辰科技退货率去年 Q4 达 6.8%，明显高于前三季度。
3. 新上线的直播电商渠道收入确认时点。

## 应对程序
1. 细节测试：全年收入明细中选取样本 60 笔，重点覆盖 Q4。
2. 截止测试：选取年结日前后各 15 笔发货记录，核对签收单与收入入账期间。
3. 对前五大经销商执行走访并获取期末库存声明。
4. 直播渠道抽取 20 笔订单核对平台结算单。"""),
    ("存货监盘方案", """# 存货监盘方案

编制：现场负责人 周浩

## 监盘安排
- 监盘地点：深圳总仓 + 东莞工厂两个存货地点。
- 监盘日期：2026-12-31（年结日当天），备选 2027-01-02 执行回溯。
- 预计存货账面余额约 3.2 亿元。

## 抽盘策略
按 ABC 分类：
1. A 类（单项价值 50 万以上，约占金额 70%）：全部盘点。
2. B 类：抽盘 30%。
3. C 类：抽盘 10%。

## 特别关注
- 呆滞料：库龄超过 1 年的芯片物料，去年已计提减值 1200 万元，本年需重估。
- 在途物资：需取得年结日后一周内的到货签收记录。"""),
    ("应收账款函证方案", """# 应收账款函证方案

编制：审计员 吴桐；复核：周浩

## 函证范围
1. 函证覆盖率：按期末应收账款金额计算不低于 80%。
2. 前十大客户必须发函，不设金额门槛。
3. 账龄超过 1 年的余额全部发函。

## 回函管理
1. 回函率目标：70%（按发函金额）。
2. 函证一律由审计组直接寄发与回收，不得经客户之手。
3. 未回函的执行替代程序：核对期后回款 + 检查销售合同与签收单。

## 时间表
- 2026-12-20 前完成发函名单与地址核实。
- 2027-01-15 第一轮回函截止，未回的发第二轮催函。"""),
    ("项目风险评估会议纪要", """# 项目风险评估会议纪要

时间：2026-07-18 14:00；参会：王强、赵敏、李婷、周浩、吴桐
记录：吴桐

## 识别的舞弊风险
1. 收入跨期确认（管理层有业绩对赌压力，视为特别风险）。
2. 管理层凌驾于控制之上（标准推定风险）。

## 重大错报风险领域
- 收入确认（特别风险）
- 存货减值（呆滞芯片物料估值）
- 应收账款可回收性（经销商信用恶化）

## 关键审计事项候选
1. 收入确认。
2. 存货减值。

## 决议
- 收入循环细节测试样本量由 45 笔上调至 60 笔（李婷提出，王强同意）。
- IT 审计组介入测试 ERP 收入接口的自动化控制。
- 下次风险更新会议定在进场后第二周（8 月下旬）。"""),
]


def ensure_space(code, name):
    space = KnowledgeSpace.objects.filter(code=code).first()
    if space is None:
        space = create_space_with_owner(
            organization=org, owner=admin, name=name, code=code,
            visibility="organization",
        )
        print(f"[NEW] space {name} ({code}) id={space.id}")
    else:
        print(f"[EXISTS] space {name} ({code}) id={space.id}")
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
            created = True
        else:
            created = False
            if doc.text_content != body:
                doc.text_content = body
                doc.save(update_fields=["text_content"])
        if doc.chunk_count and doc.status == "active" and not created:
            print(f"  = {title} (already ingested, {doc.chunk_count} chunks)")
            continue
        chunks = pipeline.ingest_text_content(doc)
        doc.chunk_count = len(chunks)
        doc.status = "active" if chunks else "failed"
        doc.save(update_fields=["chunk_count", "status"])
        print(f"  {'+' if created else '~'} {title}: {len(chunks)} chunks")


# 1) Public policy reference library ------------------------------------------
lib_space = ensure_space("policy-public-lib", "公司制度公共参考库")
seed_docs(lib_space, PUBLIC_DOCS)

library, created = ReferenceLibrary.objects.get_or_create(
    space=lib_space,
    defaults=dict(
        name="公司制度公共参考库",
        description="差旅报销、考勤休假、信息安全等公司通用制度",
        category="policy", status="published",
        published_by=admin, published_at=timezone.now(),
    ),
)
if not created and (library.status != "published" or library.category != "policy"):
    library.status = "published"
    library.category = "policy"
    library.published_by = admin
    library.published_at = library.published_at or timezone.now()
    library.save()
print(f"reference library: {library.name} [{library.category}/{library.status}]")

# 2) Project space -------------------------------------------------------------
project = ensure_space("startech-audit-2026", "星辰科技2026年报审计项目")
seed_docs(project, PROJECT_DOCS)

# 3) Project space opts in to the policy library (+ IFRS lib when present) -----
ref, created = SpaceLibraryReference.objects.get_or_create(
    space=project, library=library,
    defaults={"enabled": True, "added_by": admin},
)
if not ref.enabled:
    ref.enabled = True
    ref.save(update_fields=["enabled"])
print(f"project -> policy library reference: {'created' if created else 'exists'}")

ifrs_lib = ReferenceLibrary.objects.filter(
    space__code="ifrs-reference-lib", status="published"
).first()
if ifrs_lib:
    SpaceLibraryReference.objects.get_or_create(
        space=project, library=ifrs_lib,
        defaults={"enabled": True, "added_by": admin},
    )
    print("project -> IFRS library reference ensured")

print(f"PROJECT_SPACE_ID={project.id}")
print("DONE")
