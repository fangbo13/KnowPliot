"""Deterministic metrics and corpus for versioned RAG evaluation runs."""

import hashlib
import math
import re
from datetime import timedelta
from math import ceil

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from apps.knowledge.models import Document, DocumentChunk
from apps.spaces.models import KnowledgeSpace, Organization
from apps.spaces.ownership import canonical_owner, create_space_with_owner


EVALUATION_DOCUMENTS = (
    (
        "Annual Leave Policy",
        "Employees receive 20 days of annual leave per calendar year. "
        "Leave requests must be approved by the employee's manager.",
    ),
    (
        "Security Training Guide",
        "Security awareness training must be completed within 30 days "
        "of an employee's start date.",
    ),
)

# RAG optimization spec Phase 0: an expanded bilingual corpus that exercises
# markdown tables, numeric tolerances, cross-element references and a
# same-topic version-conflict pair. Entries: (title, content, version,
# file_type). Non-markdown types are chunked exactly like real ingestion so
# the benchmark reproduces table shredding / cross-element loss.
_BEARING_SPEC = (
    "# 轴承装配工艺规范\n\n"
    "## 适用范围\n\n"
    "本规范适用于本厂全系列精密主轴轴承的装配作业，覆盖深沟球轴承、角接触球轴承与圆锥滚子轴承。"
    "装配作业必须在洁净间内进行，环境温度应保持在20℃±2℃，相对湿度不超过60%。"
    "操作人员需经过专项培训并持证上岗，装配前应核对零件批次号与工艺流转卡。\n\n"
    "## 参数代号说明\n\n"
    "为便于工艺卡片登记，关键尺寸参数采用代号表示：代号D1表示轴承内径，代号D2表示轴承外径，"
    "代号T1表示预紧扭矩，代号C1表示径向游隙。各代号对应的标准值与公差见下文参数表，"
    "登记时必须严格按代号填写，不得使用口头简称。超出公差范围的零件一律隔离处置并登记于不合格品台账。\n\n"
    "装配过程中应使用专用液压压装工具，严禁直接敲击轴承外圈。压装力应均匀施加在配合套圈端面，"
    "压装速度不宜超过2mm/s。装配完成后应手动盘转确认无卡滞，再进行下一工序。\n\n"
    "## 关键参数表\n\n"
    "| 代号 | 参数名称 | 标准值 | 公差 | 检测器具 |\n"
    "| --- | --- | --- | --- | --- |\n"
    "| D1 | 轴承内径 | 40mm | ±0.05mm | 内径千分表 |\n"
    "| D2 | 轴承外径 | 80mm | ±0.02mm | 外径千分尺 |\n"
    "| D3 | 安装孔距 | 120mm | ±0.1mm | 三坐标测量机 |\n"
    "| D4 | 定位台阶直径 | 55mm | ±0.03mm | 外径千分尺 |\n"
    "| T1 | 预紧扭矩 | 25N·m | ±1N·m | 数显扭矩扬手 |\n"
    "| T2 | 锁紧螺母扭矩 | 60N·m | ±2N·m | 数显扭矩扬手 |\n"
    "| C1 | 径向游隙 | 0.012mm | +0.008mm | 游隙测量仪 |\n"
    "| C2 | 轴向游隙 | 0.020mm | +0.010mm | 游隙测量仪 |\n"
    "| R1 | 内圈圆跳 | 0.004mm | ≤0.004mm | 千分表架 |\n"
    "| R2 | 外圈圆跳 | 0.006mm | ≤0.006mm | 千分表架 |\n"
    "| S1 | 预紧量 | 0.008mm | ±0.002mm | 专用量具 |\n"
    "| S2 | 配合过盈量 | 0.015mm | ±0.005mm | 专用量具 |\n\n"
    "## 运转测试\n\n"
    "装配完成后需在测试台上进行空载运转测试，运转时长不少于30分钟，"
    "轴承温升不得超过35℃，噪声不得超过65dB。测试记录应归档保存三年以备追溯。"
)

_MAINTENANCE_MANUAL = (
    "# 设备维护手册\n\n"
    "## 总则\n\n"
    "本手册规定了车间关键设备的日常维护、定期保养与润滑管理要求。设备操作人员应在每班次开机前"
    "完成点检，发现异常立即停机并报修。维护记录统一登记在设备台账系统，每月由设备科汇总审核。\n\n"
    "润滑部位采用部位编号管理：编号P1指主轴，编号P2指导轨，编号P3指丝杠。"
    "各编号的润滑周期与油品型号以下表为准，不得自行更换油品牌号。\n\n"
    "## 润滑参数表\n\n"
    "| 编号 | 部位名称 | 润滑周期 | 油品 | 加注量 |\n"
    "| --- | --- | --- | --- | --- |\n"
    "| P1 | 主轴 | 每500小时 | L-AN46 | 200ml |\n"
    "| P2 | 导轨 | 每周 | 锂基脂 | 适量 |\n"
    "| P3 | 丝杠 | 每200小时 | L-HG68 | 100ml |\n"
    "| P4 | 齿轮箱 | 每2000小时 | L-CKC220 | 5L |\n"
    "| P5 | 尾座套筒 | 每月 | 锂基脂 | 适量 |\n"
    "| P6 | 刀库机构 | 每3000小时 | L-HM32 | 500ml |\n"
    "| P7 | 液压站 | 每4000小时 | L-HM46 | 60L |\n\n"
    "## 年度保养\n\n"
    "每年停机检修一次，更换全部密封件与老化管路，同步校准各轴定位精度。"
    "检修计划由设备科于每年十一月编制，报厂部批准后执行。"
)

RAGOPT_EVALUATION_DOCUMENTS = (
    (
        "Annual Leave Policy",
        "Employees receive 20 days of annual leave per calendar year. "
        "Leave requests must be approved by the employee's manager.",
        1,
        "txt",
    ),
    (
        "Security Training Guide",
        "Security awareness training must be completed within 30 days "
        "of an employee's start date.",
        1,
        "txt",
    ),
    ("轴承装配工艺规范", _BEARING_SPEC, 1, "docx"),
    ("设备维护手册", _MAINTENANCE_MANUAL, 1, "docx"),
    (
        "电机外壳检验标准",
        "电机外壳加工完成后需检验平面度与粗糙度。平面度要求不超过0.1mm，"
        "表面粗糙度Ra不大于1.6μm。外壳安装孔位置度公差为0.2mm。",
        1,
        "txt",
    ),
    (
        "焊接质量验收规程",
        "焊缝质量按国家标准验收。焊缝余高不得超过母材厚度的5.2%。"
        "焊接接头的抗拉强度不得低于母材的90%。",
        1,
        "txt",
    ),
    (
        "液压系统压力标准",
        "液压系统工作压力为16MPa，溢流阀设定值公差为±0.5MPa。"
        "管路安装后需保压测试30分钟，压降不得超过0.5mm水柱当量的0.05%。",
        1,
        "txt",
    ),
    (
        "质检抽样标准（2025版）",
        "成品检验采用随机抽样，抽样比例为5%，不合格率超过1%时整批退回。",
        1,
        "txt",
    ),
    (
        "质检抽样标准（2026版）",
        "成品检验采用随机抽样，抽样比例调整为10%，不合格率超过0.5%时整批退回。"
        "本标准自2026年起替代2025版。",
        2,
        "txt",
    ),
    (
        "新员工安全培训要求",
        "新员工入职后必须在两周内完成车间安全培训，并通过考核方可上岗。",
        1,
        "txt",
    ),
)


def deterministic_embedding(text: str, dimensions: int = 1024) -> list[float]:
    """Create a stable normalized token vector for an offline benchmark."""
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", (text or "").lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % dimensions] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


class DeterministicEvaluationEmbedder:
    def embed(self, text: str) -> list[float]:
        return deterministic_embedding(text)


@transaction.atomic
def seed_evaluation_corpus() -> dict:
    """Idempotently provision the isolated Phase 8A benchmark corpus."""
    User = get_user_model()
    user, _ = User.objects.update_or_create(
        email="rag-evaluation@local.invalid",
        defaults={
            "username": "rag-evaluation",
            "is_active": True,
            "account_purpose": "test",
            "test_principal_expires_at": timezone.now() + timedelta(days=1),
            "test_run_id": "rag-evaluation-v1",
        },
    )
    organization, _ = Organization.objects.get_or_create(
        slug="rag-evaluation",
        defaults={"name": "RAG Evaluation"},
    )
    space = KnowledgeSpace.objects.filter(
        code="evaluation-hr",
        organization=organization,
    ).first()
    if space is None:
        space = create_space_with_owner(
            organization=organization,
            owner=user,
            code="evaluation-hr",
            name="Evaluation HR",
        )
    elif canonical_owner(space) != user:
        raise RuntimeError("evaluation_space_owner_not_ready")
    for title, content in EVALUATION_DOCUMENTS:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document, _ = Document.objects.update_or_create(
            space=space,
            title=title,
            defaults={
                "file": f"evaluation/{content_hash}.txt",
                "file_type": "txt",
                "file_size": len(content.encode("utf-8")),
                "uploaded_by": user,
                "status": "active",
                "content_hash": content_hash,
                "chunk_count": 1,
            },
        )
        embedding = deterministic_embedding(f"{title} {content}")
        chunk, _ = DocumentChunk.objects.update_or_create(
            document=document,
            chunk_index=0,
            defaults={
                "space": space,
                "content": content,
                "page_number": 1,
                "metadata": {"evaluation_dataset": "phase8a-v1"},
                "embedding": embedding,
            },
        )
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE knowledge_documentchunk
                    SET embedding_vector = %s::vector
                    WHERE id = %s
                    """,
                    [str(embedding), str(chunk.id)],
                )
    return {
        "space_id": str(space.id),
        "documents": len(EVALUATION_DOCUMENTS),
        "chunks": len(EVALUATION_DOCUMENTS),
    }


@transaction.atomic
def seed_ragopt_corpus() -> dict:
    """Idempotently provision the RAG-optimization benchmark corpus.

    Mirrors ``seed_evaluation_corpus`` but seeds the expanded bilingual
    corpus (tables / tolerances / conflict pair) into its own isolated
    space so phase8a runs stay untouched.
    """
    User = get_user_model()
    user, _ = User.objects.update_or_create(
        email="rag-evaluation@local.invalid",
        defaults={
            "username": "rag-evaluation",
            "is_active": True,
            "account_purpose": "test",
            "test_principal_expires_at": timezone.now() + timedelta(days=1),
            "test_run_id": "rag-evaluation-v1",
        },
    )
    organization, _ = Organization.objects.get_or_create(
        slug="rag-evaluation",
        defaults={"name": "RAG Evaluation"},
    )
    space = KnowledgeSpace.objects.filter(
        code="evaluation-ragopt",
        organization=organization,
    ).first()
    if space is None:
        space = create_space_with_owner(
            organization=organization,
            owner=user,
            code="evaluation-ragopt",
            name="Evaluation RAG Opt",
        )
    elif canonical_owner(space) != user:
        raise RuntimeError("evaluation_space_owner_not_ready")
    from .chunker import LangChainChunker, chunk_document_text
    from .cjk import cjk_token_text

    chunker = LangChainChunker()
    for title, content, version, file_type in RAGOPT_EVALUATION_DOCUMENTS:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        document, _ = Document.objects.update_or_create(
            space=space,
            title=title,
            defaults={
                "file": f"evaluation/{content_hash}.txt",
                "file_type": file_type,
                "file_size": len(content.encode("utf-8")),
                "uploaded_by": user,
                "status": "active",
                "content_hash": content_hash,
                "version": version,
            },
        )
        # Route through the REAL chunking path so the benchmark reproduces
        # exactly what ingestion does (docx entries emulate Docling markdown
        # output; before Phase 1 they hit the plain splitter and tables shred).
        chunks = chunk_document_text(
            chunker, content, file_type, parsed_as_markdown=True
        )
        DocumentChunk.objects.filter(document=document).delete()
        vector_rows = []
        for index, chunk in enumerate(chunks):
            embedding = deterministic_embedding(f"{title} {chunk['text']}")
            row = DocumentChunk.objects.create(
                document=document,
                space=space,
                content=chunk["text"],
                content_tokens=cjk_token_text(f"{title}\n{chunk['text']}"),
                chunk_index=index,
                page_number=1,
                metadata={**chunk.get("metadata", {}), "evaluation_dataset": "ragopt-v1"},
                embedding=embedding,
            )
            vector_rows.append((row.id, embedding))
        document.chunk_count = len(chunks)
        document.save(update_fields=["chunk_count"])
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                for row_id, embedding in vector_rows:
                    cursor.execute(
                        """
                        UPDATE knowledge_documentchunk
                        SET embedding_vector = %s::vector
                        WHERE id = %s
                        """,
                        [str(embedding), str(row_id)],
                    )
    total_chunks = DocumentChunk.objects.filter(space=space).count()
    return {
        "space_id": str(space.id),
        "documents": len(RAGOPT_EVALUATION_DOCUMENTS),
        "chunks": total_chunks,
    }


def calculate_metrics(cases: list[dict]) -> dict:
    answerable = [case for case in cases if case["answerable"]]
    reciprocal_ranks = []
    recalled = 0
    for case in answerable:
        expected = set(case["expected_document_ids"])
        results = case["result_document_ids"][:5]
        matching_ranks = [
            index for index, document_id in enumerate(results, start=1)
            if document_id in expected
        ]
        if matching_ranks:
            recalled += 1
            reciprocal_ranks.append(1 / min(matching_ranks))
        else:
            reciprocal_ranks.append(0.0)

    unanswerable = [case for case in cases if not case["answerable"]]
    refusals = sum(
        bool(case.get("refused", not case["result_document_ids"]))
        for case in unanswerable
    )
    latencies = sorted(int(case["latency_ms"]) for case in cases)
    p95_index = max(0, ceil(len(latencies) * 0.95) - 1) if latencies else 0

    # RAG optimization spec Phase 0: per-tag recall breakdown so table /
    # numeric / conflict / zh improvements are individually measurable.
    recall_by_tag: dict[str, dict] = {}
    answer_hits = 0
    answer_total = 0
    for case in answerable:
        expected = set(case["expected_document_ids"])
        hit = any(
            document_id in expected
            for document_id in case["result_document_ids"][:5]
        )
        for tag in case.get("tags") or []:
            bucket = recall_by_tag.setdefault(tag, {"hits": 0, "total": 0})
            bucket["total"] += 1
            bucket["hits"] += int(hit)
        # answer_hit: any top-5 chunk carries the literal answer snippet —
        # measures chunk quality (table shredding / numeric token loss)
        # beyond document-level recall.
        if "answer_hit" in case:
            answer_total += 1
            answer_hits += int(bool(case["answer_hit"]))
    recall_by_tag_metric = {
        tag: round(bucket["hits"] / bucket["total"], 4)
        for tag, bucket in sorted(recall_by_tag.items())
        if bucket["total"]
    }

    return {
        "recall_at_5": round(recalled / len(answerable), 4) if answerable else 1.0,
        "mrr": round(sum(reciprocal_ranks) / len(answerable), 4) if answerable else 1.0,
        "refusal_accuracy": round(refusals / len(unanswerable), 4) if unanswerable else 1.0,
        "cross_space_leaks": sum(bool(case.get("space_leak")) for case in cases),
        "latency_p95_ms": latencies[p95_index] if latencies else 0,
        "recall_by_tag": recall_by_tag_metric,
        "answer_hit_rate": (
            round(answer_hits / answer_total, 4) if answer_total else None
        ),
    }
