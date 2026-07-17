# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERS = ROOT / "renders"
AUDIO = ROOT / "public" / "audio"

SOURCE_VIDEO = RENDERS / "KnowPilot-real-ui-walkthrough.mp4"
OUTPUT_VIDEO = RENDERS / "KnowPilot-real-ui-walkthrough-natural-voice.mp4"

VOICEOVER: list[tuple[float, str, float]] = [
    (1.8, "voiceover/s01-opening.wav", 0.9),
    (21.5, "voiceover/s02-brand.wav", 0.9),
    (38.0, "voiceover/s03-chat.wav", 0.9),
    (78.0, "voiceover/s04-knowledge.wav", 0.9),
    (118.0, "voiceover/s05-crawler.wav", 0.9),
    (148.0, "voiceover/s06-rbac.wav", 0.9),
    (177.5, "voiceover/s07-feedback.wav", 0.9),
    (196.2, "voiceover/s08-scenarios.wav", 0.9),
    (216.5, "voiceover/s09-finale.wav", 0.9),
]

SFX: list[tuple[float, str, float]] = [
    (20.2, "sfx/soft-whoosh.wav", 0.11),
    (31.4, "sfx/light-chime.wav", 0.08),
    (40.2, "sfx/soft-click.wav", 0.07),
    (44.7, "sfx/key.wav", 0.06),
    (49.2, "sfx/soft-click.wav", 0.07),
    (53.6, "sfx/ui-tick.wav", 0.055),
    (63.8, "sfx/soft-click.wav", 0.07),
    (76.2, "sfx/soft-whoosh.wav", 0.08),
    (82.8, "sfx/soft-click.wav", 0.07),
    (89.6, "sfx/light-chime.wav", 0.09),
    (101.2, "sfx/ui-tick.wav", 0.055),
    (115.3, "sfx/soft-whoosh.wav", 0.08),
    (121.8, "sfx/key.wav", 0.055),
    (126.4, "sfx/soft-click.wav", 0.07),
    (137.5, "sfx/ui-tick.wav", 0.055),
    (145.4, "sfx/soft-whoosh.wav", 0.08),
    (157.3, "sfx/ui-tick.wav", 0.055),
    (167.1, "sfx/ui-tick.wav", 0.055),
    (175.2, "sfx/soft-whoosh.wav", 0.08),
    (185.2, "sfx/light-chime.wav", 0.075),
    (212.2, "sfx/soft-whoosh.wav", 0.08),
]


def delay_ms(seconds: float) -> int:
    return round(seconds * 1000)


def main() -> None:
    inputs = ["ffmpeg", "-y", "-v", "error", "-i", str(SOURCE_VIDEO), "-i", str(AUDIO / "background-score.mp3")]
    timed_audio = VOICEOVER + SFX
    for _, file, _ in timed_audio:
        inputs.extend(["-i", str(AUDIO / file)])

    filters: list[str] = [
        "[1:a]volume='if(lt(t,30),0.18,if(lt(t,175),0.20,if(lt(t,210),0.23,if(lt(t,225),0.18*(225-t)/15,0))))':eval=frame[a1]"
    ]
    labels = ["[a1]"]
    input_index = 2
    for seconds, _, volume in timed_audio:
        label = f"a{input_index}"
        delay = delay_ms(seconds)
        filters.append(
            f"[{input_index}:a]adelay={delay}|{delay},volume={volume},"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[{label}]"
        )
        labels.append(f"[{label}]")
        input_index += 1

    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0,"
        + "atrim=0:225.045333,"
        + "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
    )

    command = [
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(OUTPUT_VIDEO),
    ]
    subprocess.run(command, check=True)
    print(f"wrote {OUTPUT_VIDEO.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
