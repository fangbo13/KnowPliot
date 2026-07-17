# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "public" / "audio" / "voiceover"
TMP_DIR = ROOT / "renders" / "voiceover-tmp"

VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+7%"
PITCH = "-2Hz"

CLIPS: list[tuple[str, str]] = [
    (
        "s01-opening",
        "专业服务团队每天都在找答案。流程在哪，准则怎么用，这个判断为什么这么做。"
        "信息常常散在文件、网页，和历史记录里。",
    ),
    (
        "s02-brand",
        "KnowPilot，知识领航。它把这些知识接进统一知识库。团队提问，系统先检索，再给出带来源的回答。",
    ),
    (
        "s03-chat",
        "比如这个问题。用户点开新对话，直接输入租赁准则差异。"
        "KnowPilot 开始连接，检索，然后生成回答。"
        "最后，来源就在答案下面。复核时，不用再翻半天。",
    ),
    (
        "s04-knowledge",
        "管理员上传文档。系统会先校验格式，然后自动切块、建立索引。"
        "处理状态，分块数量，重新索引，都在表格里清楚可见。",
    ),
    (
        "s05-crawler",
        "网页内容也可以采集。输入网址，打开 Internal Only，然后提交。"
        "处理进度会一步步显示。内容过期，或者授权变化时，可以直接撤回。",
    ),
    (
        "s06-rbac",
        "权限部分，也放在真实后台里。普通用户只看到聊天入口。"
        "内容管理员维护知识库。系统管理员管理用户、采集和系统健康。"
        "不同角色，只看到自己该看的功能。",
    ),
    (
        "s07-feedback",
        "企业工具要让人放心。上传成功、格式错误、离线、重试、停止生成，都有明确反馈。"
        "关键操作，也会自动进入审计日志。",
    ),
    (
        "s08-scenarios",
        "同一套引擎，可以放到不同团队里。新人查流程，项目组追历史判断，审计团队问准则。"
        "知识被沉淀，也被再次使用。",
    ),
    (
        "s09-finale",
        "KnowPilot，让组织知识可用、可管、可追溯。",
    ),
]


async def synthesize_clip(name: str, text: str) -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mp3_path = TMP_DIR / f"{name}.mp3"
    wav_path = OUT_DIR / f"{name}.wav"

    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate=RATE,
        pitch=PITCH,
    )
    await communicate.save(str(mp3_path))

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(mp3_path),
            "-ar",
            "48000",
            "-ac",
            "2",
            str(wav_path),
        ],
        check=True,
    )
    print(f"generated {wav_path.relative_to(ROOT)}")


async def main() -> None:
    for name, text in CLIPS:
        await synthesize_clip(name, text)


if __name__ == "__main__":
    asyncio.run(main())
