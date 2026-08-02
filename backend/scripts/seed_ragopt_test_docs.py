"""Seed RAG-optimization E2E docs into auditor.xu's space via REAL ingestion.

Creates two markdown docs (a tolerance table doc + a version-conflict pair)
and runs the actual RAGPipeline.ingest_text_content so DashScope embeddings
are generated and the docs are searchable in the live chat UI.

Run: docker compose exec -T backend python scripts/seed_ragopt_test_docs.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from apps.knowledge.models import Document  # noqa: E402
from apps.rag.pipeline import RAGPipeline  # noqa: E402
from apps.spaces.models import SpaceMembership  # noqa: E402

User = get_user_model()

BEARING_DOC = (
    "# RAGOPT轴承装配工艺规范\n\n"
    "## 适用范围\n\n"
    "本规范适用于精密主轴轴承的装配作业。装配环境温度应保持在20℃±2℃。\n\n"
    "## 关键参数表\n\n"
    "下表给出关键尺寸参数与公差。\n\n"
    "| 代号 | 参数名称 | 标准值 | 公差 | 检测器具 |\n"
    "| --- | --- | --- | --- | --- |\n"
    "| D1 | 轴承内径 | 40mm | ±0.05mm | 内径千分表 |\n"
    "| D2 | 轴承外径 | 80mm | ±0.02mm | 外径千分尺 |\n"
    "| C1 | 径向游隙 | 0.012mm | +0.008mm | 游隙测量仪 |\n\n"
    "## 运转测试\n\n"
    "装配完成后空载运转不少于30分钟，噪声不得超过65dB。\n"
)

SAMPLING_2025 = (
    "# RAGOPT质检抽样标准（2025版）\n\n"
    "成品检验采用随机抽样，抽样比例为5%，不合格率超过1%时整批退回。\n"
)
SAMPLING_2026 = (
    "# RAGOPT质检抽样标准（2026版）\n\n"
    "成品检验采用随机抽样，抽样比例调整为10%，不合格率超过0.5%时整批退回。"
    "本标准自2026年起替代2025版。\n"
)

DOCS = [
    ("RAGOPT轴承装配工艺规范", BEARING_DOC, 1),
    ("RAGOPT质检抽样标准（2025版）", SAMPLING_2025, 1),
    ("RAGOPT质检抽样标准（2026版）", SAMPLING_2026, 2),
]


def main():
    user = User.objects.get(email="auditor.xu@test.ey.com")
    memberships = list(
        SpaceMembership.objects.filter(user=user).select_related("space")
    )
    if not memberships:
        print("ERROR: auditor.xu has no space membership")
        return

    pipeline = RAGPipeline(ingestion=True)
    for membership in memberships:
        space = membership.space
        print(f"space={space.id} name={space.name}")
        for title, content, version in DOCS:
            doc, _ = Document.objects.update_or_create(
                space=space,
                title=title,
                defaults={
                    "uploaded_by": user,
                    "updated_by": user,
                    "status": "active",
                    "file_type": "md",
                    "file_size": len(content.encode("utf-8")),
                    "text_content": content,
                    "version": version,
                },
            )
            chunks = pipeline.ingest_text_content(doc)
            print(f"  ingested '{title}' v{version}: {len(chunks)} chunks")
    print("done")


if __name__ == "__main__":
    main()
