"""ASR（P3-B）：Faster-Whisper 转中文。模型懒加载，CI / 未安装时不挡文字聊。"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path

from src.speech.constants import (
    ASR_BEAM_SIZE,
    ASR_LANGUAGE,
    ASR_MAX_AUDIO_BYTES,
    ASR_MIN_AUDIO_BYTES,
    ASR_MIN_TEXT_CHARS,
    ASR_MODEL_PREFIX,
    ASR_NO_SPEECH_MAX,
    DEFAULT_ASR_MODEL,
)

logger = logging.getLogger(__name__)

_KEEP_CHAR = re.compile(r"[\w\u4e00-\u9fff]", re.UNICODE)

_MIME_SUFFIX = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".mp4",
    "audio/ogg": ".ogg",
}


class AsrError(Exception):
    """转写失败。调用方按没听清处理，不得写记忆。"""


class FasterWhisperAsr:
    def __init__(self, model_name: str = DEFAULT_ASR_MODEL) -> None:
        self._model_size = asr_model_size(model_name)
        self._model: object | None = None

    async def transcribe(self, audio_bytes: bytes, mime: str) -> str:
        if len(audio_bytes) < ASR_MIN_AUDIO_BYTES:
            logger.info("asr skip short audio bytes=%s", len(audio_bytes))
            return ""
        if len(audio_bytes) > ASR_MAX_AUDIO_BYTES:
            msg = f"asr audio too large bytes={len(audio_bytes)}"
            raise AsrError(msg)
        suffix = _suffix_for_mime(mime)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio_bytes)
            temp_path = Path(handle.name)
        try:
            model = await asyncio.to_thread(self._ensure_model)
            return await asyncio.to_thread(self._transcribe_path, model, temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _ensure_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            msg = "faster-whisper is not installed"
            raise AsrError(msg) from exc
        device, compute_type = _pick_device()
        logger.info(
            "asr loading model=%s device=%s compute=%s",
            self._model_size,
            device,
            compute_type,
        )
        self._model = WhisperModel(
            self._model_size,
            device=device,
            compute_type=compute_type,
        )
        return self._model

    def _transcribe_path(self, model: object, path: Path) -> str:
        transcribe = getattr(model, "transcribe", None)
        if transcribe is None:
            msg = "asr model missing transcribe"
            raise AsrError(msg)
        try:
            segments, _info = transcribe(
                str(path),
                language=ASR_LANGUAGE,
                vad_filter=True,
                beam_size=ASR_BEAM_SIZE,
            )
        except Exception as exc:
            msg = "asr infer failed"
            raise AsrError(msg) from exc
        texts: list[str] = []
        no_speech: list[float] = []
        for segment in segments:
            piece = getattr(segment, "text", "")
            if isinstance(piece, str) and piece.strip():
                texts.append(piece.strip())
            prob = getattr(segment, "no_speech_prob", None)
            if isinstance(prob, (int, float)):
                no_speech.append(float(prob))
        if no_speech and (sum(no_speech) / len(no_speech)) >= ASR_NO_SPEECH_MAX:
            logger.info("asr no_speech_prob high n=%s", len(no_speech))
            return ""
        return "".join(texts).strip()


def asr_model_size(name: str) -> str:
    raw = (name or "").strip().lower()
    if raw.startswith(ASR_MODEL_PREFIX):
        raw = raw[len(ASR_MODEL_PREFIX) :]
    return raw or "small"


def is_clear_transcript(text: str) -> bool:
    kept = "".join(_KEEP_CHAR.findall(text or ""))
    return len(kept) >= ASR_MIN_TEXT_CHARS


def _suffix_for_mime(mime: str) -> str:
    raw = (mime or "").split(";", 1)[0].strip().lower()
    return _MIME_SUFFIX.get(raw, ".webm")


def _pick_device() -> tuple[str, str]:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16"
    except ImportError:
        pass
    return "cpu", "int8"
