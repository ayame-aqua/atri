"""P3-B Faster-Whisper 包装：不下载模型。"""

from __future__ import annotations

import asyncio

from src.speech.asr import FasterWhisperAsr, asr_model_size, is_clear_transcript


def test_asr_model_size_strips_prefix() -> None:
    assert asr_model_size("faster-whisper-small") == "small"
    assert asr_model_size("base") == "base"


def test_clear_transcript_rejects_noise() -> None:
    assert is_clear_transcript("") is False
    assert is_clear_transcript("……") is False
    assert is_clear_transcript("嗯") is False
    assert is_clear_transcript("在吗") is True
    assert is_clear_transcript("hi") is True


def test_transcribe_short_audio_returns_empty() -> None:
    asr = FasterWhisperAsr("small")
    text = asyncio.run(asr.transcribe(b"xx", "audio/webm"))
    assert text == ""
    assert asr._model is None
