"""TTS → 本机 GPT-SoVITS（P3）。"""

from __future__ import annotations


async def synthesize(text: str) -> bytes:
    del text
    raise NotImplementedError("P3: call local GPT-SoVITS API (ja only)")
