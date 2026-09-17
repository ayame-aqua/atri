"""ASR（P3）。"""

from __future__ import annotations


async def transcribe(audio_bytes: bytes, mime: str) -> str:
    del audio_bytes, mime
    raise NotImplementedError("P3: Faster-Whisper / SenseVoice")
