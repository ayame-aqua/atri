"""P3-B Faster-Whisper 包装：不下载模型。"""

from __future__ import annotations

import asyncio

from src.speech.asr import FasterWhisperAsr, asr_model_size, build_asr, is_clear_transcript


def test_asr_model_size_strips_prefix() -> None:
    assert asr_model_size("faster-whisper-small") == "small"
    assert asr_model_size("base") == "base"
    assert asr_model_size("sensevoice-small") == "sensevoice-small"
    assert asr_model_size("fun-asr-nano") == "fun-asr-nano"
    assert asr_model_size("funasr") == "fun-asr-nano"


def test_build_asr_prefers_funasr() -> None:
    asr = build_asr("fun-asr-nano")
    assert asr._primary.__class__.__name__ == "FunasrAsr"
    assert asr._fallback is not None
    assert asr._primary._model is None


def test_clear_transcript_rejects_noise() -> None:
    assert is_clear_transcript("") is False
    assert is_clear_transcript("……") is False
    assert is_clear_transcript("嗯") is False
    assert is_clear_transcript("在吗") is True
    assert is_clear_transcript("hi") is False
    assert is_clear_transcript("T very social.") is False


def test_transcribe_short_audio_returns_empty() -> None:
    asr = FasterWhisperAsr("small")
    text = asyncio.run(asr.transcribe(b"xx", "audio/webm"))
    assert text == ""
    assert asr._model is None
