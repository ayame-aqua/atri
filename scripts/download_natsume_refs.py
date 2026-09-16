"""Download community Japanese reference wavs into data/natsume/references.

These clips are inference prompts only. Do not commit them.
Weights are trained separately from dry audio in data/natsume/wavs.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEST_DIR = REPO_ROOT / "data" / "natsume" / "references"
RAW_BASE = "https://raw.githubusercontent.com/Macyear/Artemis/master/skills/tts/ref_wavs/"

# emotion aligns with [[natsume]] tail; sad falls back to neutral at runtime.
REF_FILES = [
    ("ref_01.wav", "ref_01_日常_忙しかった.wav", "あ、結構忙しかったわね", "neutral"),
    ("ref_02.wav", "ref_02_日常_お疲れ様.wav", "今日も一日、お疲れ様", "happy"),
    ("ref_06.wav", "ref_06_傲娇_変なこと.wav", "言っとくけど変なことはしないからね", "angry"),
    ("ref_11.wav", "ref_11_深情_大好き.wav", "好き、大好き", "shy"),
]


def main() -> None:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    prompts = []
    for local_name, remote_name, text, emotion in REF_FILES:
        url = RAW_BASE + urllib.request.quote(remote_name)
        out = DEST_DIR / local_name
        print("GET", remote_name)
        urllib.request.urlretrieve(url, out)
        print(" ", out.name, out.stat().st_size)
        prompts.append(
            {
                "file": local_name,
                "prompt_text": text,
                "prompt_lang": "ja",
                "emotion": emotion,
            }
        )
    (DEST_DIR / "prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("done")


if __name__ == "__main__":
    main()
