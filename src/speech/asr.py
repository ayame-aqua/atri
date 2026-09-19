"""ASR：中文优先 SenseVoice-Small；没有 FunASR 时退回 Faster-Whisper。"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path

from src.speech.constants import (
    ASR_BEAM_SIZE,
    ASR_INITIAL_PROMPT,
    ASR_LANGUAGE,
    ASR_MAX_AUDIO_BYTES,
    ASR_MIN_AUDIO_BYTES,
    ASR_MIN_TEXT_CHARS,
    ASR_MODEL_PREFIX,
    ASR_NO_SPEECH_MAX,
    ASR_WAV_RATE,
    DEFAULT_ASR_MODEL,
    SENSEVOICE_LANGUAGE,
    SENSEVOICE_MODEL_ID,
    SENSEVOICE_VAD_MAX_MS,
    SENSEVOICE_VAD_MODEL,
    WHISPER_FALLBACK_SIZE,
)
from src.speech.debug_log import speech_debug

logger = logging.getLogger(__name__)

_SENSEVOICE_TAG = re.compile(r"<\|[^|]*\|>")

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


class SenseVoiceAsr:
    def __init__(self, model_id: str = SENSEVOICE_MODEL_ID) -> None:
        self._model_id = model_id
        self._model: object | None = None

    async def transcribe(self, audio_bytes: bytes, mime: str) -> str:
        path = _write_temp_audio(audio_bytes, mime)
        if path is None:
            return ""
        wav_path: Path | None = None
        try:
            wav_path = await asyncio.to_thread(_ensure_wav, path)
            model = await asyncio.to_thread(self._ensure_model)
            return await asyncio.to_thread(self._transcribe_path, model, wav_path)
        finally:
            if wav_path is not None and wav_path != path:
                wav_path.unlink(missing_ok=True)
            path.unlink(missing_ok=True)

    def _ensure_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            from funasr import AutoModel
        except ImportError as exc:
            msg = "funasr is not installed"
            raise AsrError(msg) from exc
        device = _torch_device()
        logger.info("asr loading model=sensevoice-small device=%s", device)
        speech_debug("asr_load", backend="sensevoice", device=device)
        try:
            self._model = AutoModel(
                model=self._model_id,
                vad_model=SENSEVOICE_VAD_MODEL,
                vad_kwargs={"max_single_segment_time": SENSEVOICE_VAD_MAX_MS},
                device=device,
                disable_update=True,
            )
        except Exception as exc:
            msg = "sensevoice load failed"
            raise AsrError(msg) from exc
        return self._model

    def _transcribe_path(self, model: object, path: Path) -> str:
        generate = getattr(model, "generate", None)
        if generate is None:
            msg = "sensevoice missing generate"
            raise AsrError(msg)
        try:
            raw = generate(
                input=str(path),
                cache={},
                language=SENSEVOICE_LANGUAGE,
                use_itn=True,
                batch_size_s=60,
            )
        except Exception as exc:
            msg = "sensevoice infer failed"
            raise AsrError(msg) from exc
        text = _sensevoice_text(raw)
        speech_debug("asr_text", backend="sensevoice", text=text)
        return text


class FasterWhisperAsr:
    def __init__(self, model_name: str = WHISPER_FALLBACK_SIZE) -> None:
        self._model_size = asr_model_size(model_name)
        self._model: object | None = None

    async def transcribe(self, audio_bytes: bytes, mime: str) -> str:
        path = _write_temp_audio(audio_bytes, mime)
        if path is None:
            return ""
        try:
            model = await asyncio.to_thread(self._ensure_model)
            return await asyncio.to_thread(self._transcribe_path, model, path)
        finally:
            path.unlink(missing_ok=True)

    def _ensure_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            msg = "faster-whisper is not installed"
            raise AsrError(msg) from exc
        device, compute_type = _pick_whisper_device()
        logger.info(
            "asr loading model=%s device=%s compute=%s",
            self._model_size,
            device,
            compute_type,
        )
        speech_debug(
            "asr_load",
            backend="faster-whisper",
            model=self._model_size,
            device=device,
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
                initial_prompt=ASR_INITIAL_PROMPT,
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
        text = "".join(texts).strip()
        speech_debug("asr_text", backend="faster-whisper", text=text)
        return text


class FallbackAsr:
    """先 SenseVoice，装不上再 Faster-Whisper。"""

    def __init__(self, model_name: str = DEFAULT_ASR_MODEL) -> None:
        self._primary: SenseVoiceAsr | FasterWhisperAsr
        if _wants_sensevoice(model_name):
            self._primary = SenseVoiceAsr()
            self._fallback: FasterWhisperAsr | None = FasterWhisperAsr(WHISPER_FALLBACK_SIZE)
        else:
            self._primary = FasterWhisperAsr(model_name)
            self._fallback = None

    async def transcribe(self, audio_bytes: bytes, mime: str) -> str:
        try:
            return await self._primary.transcribe(audio_bytes, mime)
        except AsrError:
            if self._fallback is None:
                raise
            logger.exception("asr primary failed, falling back to whisper")
            speech_debug("asr_fallback", to="faster-whisper")
            return await self._fallback.transcribe(audio_bytes, mime)


def build_asr(model_name: str = DEFAULT_ASR_MODEL) -> FallbackAsr:
    return FallbackAsr(model_name)


def asr_model_size(name: str) -> str:
    raw = (name or "").strip().lower()
    if raw.startswith(ASR_MODEL_PREFIX):
        raw = raw[len(ASR_MODEL_PREFIX) :]
    if _wants_sensevoice(raw):
        return "sensevoice-small"
    return raw or WHISPER_FALLBACK_SIZE


def is_clear_transcript(text: str) -> bool:
    """只认中文。英文幻觉（如 T very social）当没听清。"""
    cjk = re.findall(r"[\u4e00-\u9fff]", text or "")
    return len(cjk) >= ASR_MIN_TEXT_CHARS


def _ensure_wav(path: Path) -> Path:
    """SenseVoice 吃 wav；浏览器上行是 webm，复用 Faster-Whisper 的解码。"""
    if path.suffix.lower() == ".wav":
        return path
    try:
        from faster_whisper.audio import decode_audio
    except ImportError as exc:
        msg = "faster-whisper decode missing"
        raise AsrError(msg) from exc
    try:
        samples = decode_audio(str(path), sampling_rate=ASR_WAV_RATE)
    except Exception as exc:
        msg = "asr decode failed"
        raise AsrError(msg) from exc
    dest = path.with_suffix(".wav")
    _write_pcm_wav(dest, samples)
    return dest


def _write_pcm_wav(dest: Path, samples: object) -> None:
    import wave

    import numpy as np

    pcm = np.asarray(samples, dtype=np.float32).reshape(-1)
    pcm = np.clip(pcm, -1.0, 1.0)
    ints = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(dest), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(ASR_WAV_RATE)
        handle.writeframes(ints.tobytes())


def _write_temp_audio(audio_bytes: bytes, mime: str) -> Path | None:
    if len(audio_bytes) < ASR_MIN_AUDIO_BYTES:
        logger.info("asr skip short audio bytes=%s", len(audio_bytes))
        speech_debug("asr_skip", reason="short", bytes=len(audio_bytes))
        return None
    if len(audio_bytes) > ASR_MAX_AUDIO_BYTES:
        msg = f"asr audio too large bytes={len(audio_bytes)}"
        raise AsrError(msg)
    suffix = _suffix_for_mime(mime)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(audio_bytes)
        return Path(handle.name)


def _suffix_for_mime(mime: str) -> str:
    raw = (mime or "").split(";", 1)[0].strip().lower()
    return _MIME_SUFFIX.get(raw, ".webm")


def _wants_sensevoice(name: str) -> bool:
    raw = (name or "").strip().lower()
    return "sensevoice" in raw or raw in {"funasr", "paraformer"}


def _sensevoice_text(raw: object) -> str:
    text = ""
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict):
            piece = first.get("text")
            if isinstance(piece, str):
                text = piece
        elif isinstance(first, str):
            text = first
    elif isinstance(raw, dict):
        piece = raw.get("text")
        if isinstance(piece, str):
            text = piece
    elif isinstance(raw, str):
        text = raw
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess

        text = rich_transcription_postprocess(text)
    except Exception:
        text = _SENSEVOICE_TAG.sub("", text)
    return " ".join(text.split()).strip()


def _torch_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
    except ImportError:
        pass
    return "cpu"


def _pick_whisper_device() -> tuple[str, str]:
    try:
        import ctranslate2

        if int(ctranslate2.get_cuda_device_count()) > 0:
            return "cuda", "float16"
    except Exception:
        pass
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16"
    except ImportError:
        pass
    return "cpu", "int8"
