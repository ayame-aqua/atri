"""本机 GPT-SoVITS TTS（P3-A）。只合成日语；失败由调用方降级为纯文字。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import struct
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from src.speech.constants import (
    AUDIO_ID_LEN,
    DEFAULT_CACHE_DIR,
    DEFAULT_REF_DIR,
    DEFAULT_TTS_API_BASE,
    DEFAULT_TTS_TIMEOUT_S,
    EMOTION_REF_FILES,
    ERROR_BODY_MAX,
    PROMPT_LANG,
    PROMPTS_FILE,
    SAD_FALLBACK_EMOTION,
    TTS_CONNECT_TIMEOUT_S,
    TTS_MEDIA_TYPE,
    TTS_TEXT_LANG,
    TTS_TEXT_SPLIT_METHOD,
    WAV_HEADER_SIZE,
)

logger = logging.getLogger(__name__)

_AUDIO_ID_RE = re.compile(rf"^[0-9a-f]{{{AUDIO_ID_LEN}}}$")


class TtsError(Exception):
    """合成失败。不得让整轮聊天失败。"""


@dataclass(frozen=True)
class CachedClip:
    audio_id: str
    path: Path
    duration_ms: int | None


class SoVitsTts:
    def __init__(
        self,
        *,
        api_base: str = DEFAULT_TTS_API_BASE,
        ref_dir: Path | str = DEFAULT_REF_DIR,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        timeout_s: float = DEFAULT_TTS_TIMEOUT_S,
        text_lang: str = TTS_TEXT_LANG,
        gpt_weights: Path | str | None = None,
        sovits_weights: Path | str | None = None,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._ref_dir = Path(ref_dir)
        self._cache_dir = Path(cache_dir)
        self._timeout_s = float(timeout_s)
        self._text_lang = text_lang
        self._gpt_weights = _existing_file(gpt_weights)
        self._sovits_weights = _existing_file(sovits_weights)
        self._weights_applied = False
        self._prompts = _load_prompts(self._ref_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize_to_cache(self, text: str, emotion: str) -> CachedClip:
        speech = (text or "").strip()
        if not speech:
            raise TtsError("empty speech_ja")
        audio_id = _audio_id(speech, emotion)
        path = self._cache_dir / f"{audio_id}.{TTS_MEDIA_TYPE}"
        if path.is_file() and path.stat().st_size > WAV_HEADER_SIZE:
            logger.info("tts cache hit audio_id=%s emotion=%s", audio_id, emotion)
            return CachedClip(audio_id=audio_id, path=path, duration_ms=_wav_duration_ms(path))
        started = time.monotonic()
        wav = await self._request_wav(speech, emotion)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        path.write_bytes(wav)
        duration_ms = _wav_duration_ms(path)
        logger.info(
            "tts cached audio_id=%s emotion=%s bytes=%s duration_ms=%s elapsed_ms=%s",
            audio_id,
            emotion,
            len(wav),
            duration_ms,
            elapsed_ms,
        )
        return CachedClip(audio_id=audio_id, path=path, duration_ms=duration_ms)

    def clip_path(self, audio_id: str) -> Path | None:
        if not _AUDIO_ID_RE.match(audio_id):
            return None
        path = self._cache_dir / f"{audio_id}.{TTS_MEDIA_TYPE}"
        if not path.is_file():
            return None
        return path

    async def _request_wav(self, text: str, emotion: str) -> bytes:
        ref_path, prompt_text = self._ref_for(emotion)
        payload = {
            "text": text,
            "text_lang": self._text_lang,
            "ref_audio_path": str(ref_path.resolve()),
            "prompt_text": prompt_text,
            "prompt_lang": PROMPT_LANG,
            "text_split_method": TTS_TEXT_SPLIT_METHOD,
            "media_type": TTS_MEDIA_TYPE,
            "streaming_mode": False,
        }
        url = f"{self._api_base}/tts"
        timeout = httpx.Timeout(self._timeout_s, connect=TTS_CONNECT_TIMEOUT_S)
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                await self._apply_weights(client)
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            logger.exception("tts http failed")
            raise TtsError("tts request failed") from exc
        if response.status_code >= 400:
            logger.error(
                "tts status=%s body=%s", response.status_code, _error_snippet(response.content)
            )
            raise TtsError(f"tts status {response.status_code}")
        body = response.content
        if not body.startswith(b"RIFF"):
            logger.error("tts response is not wav body=%s", _error_snippet(body))
            raise TtsError("tts not wav")
        return body

    async def _apply_weights(self, client: httpx.AsyncClient) -> None:
        if self._weights_applied:
            return
        if self._gpt_weights is not None:
            await self._set_weight(client, "set_gpt_weights", self._gpt_weights)
        if self._sovits_weights is not None:
            await self._set_weight(client, "set_sovits_weights", self._sovits_weights)
        self._weights_applied = True

    async def _set_weight(self, client: httpx.AsyncClient, endpoint: str, path: Path) -> None:
        url = f"{self._api_base}/{endpoint}"
        try:
            response = await client.get(url, params={"weights_path": str(path.resolve())})
        except httpx.HTTPError:
            logger.exception("tts %s failed path=%s", endpoint, path.name)
            return
        if response.status_code >= 400:
            logger.error(
                "tts %s status=%s body=%s",
                endpoint,
                response.status_code,
                _error_snippet(response.content),
            )
            return
        logger.info("tts %s ok path=%s", endpoint, path.name)

    def _ref_for(self, emotion: str) -> tuple[Path, str]:
        key = emotion if emotion in self._prompts else SAD_FALLBACK_EMOTION
        if emotion == "sad":
            key = SAD_FALLBACK_EMOTION
        item = self._prompts.get(key) or self._prompts.get(SAD_FALLBACK_EMOTION)
        if item is None:
            raise TtsError("no reference wav")
        path, prompt = item
        if not path.is_file():
            raise TtsError(f"ref missing path={path}")
        return path, prompt


def _load_prompts(ref_dir: Path) -> dict[str, tuple[Path, str]]:
    mapping: dict[str, tuple[Path, str]] = {}
    json_path = ref_dir / PROMPTS_FILE
    if json_path.is_file():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("tts prompts.json unreadable")
            raw = []
        if isinstance(raw, list):
            for row in raw:
                if not isinstance(row, dict):
                    continue
                emotion = row.get("emotion")
                filename = row.get("file")
                prompt = row.get("prompt_text")
                if not isinstance(emotion, str) or not isinstance(filename, str):
                    continue
                if not isinstance(prompt, str):
                    prompt = ""
                mapping[emotion] = (ref_dir / filename, prompt)
    for emotion, (filename, prompt) in EMOTION_REF_FILES.items():
        mapping.setdefault(emotion, (ref_dir / filename, prompt))
    return mapping


def _existing_file(path: Path | str | None) -> Path | None:
    if path is None:
        return None
    resolved = Path(path)
    if not resolved.is_file():
        return None
    return resolved


def _error_snippet(content: bytes) -> str:
    if not content:
        return ""
    text = content.decode("utf-8", errors="replace").replace("\n", " ")
    return text[:ERROR_BODY_MAX]


def _audio_id(text: str, emotion: str) -> str:
    digest = hashlib.sha256(f"{emotion}\0{text}".encode()).hexdigest()
    return digest[:AUDIO_ID_LEN]


def _wav_duration_ms(path: Path) -> int | None:
    try:
        data = path.read_bytes()
    except OSError:
        logger.exception("tts cache unreadable path=%s", path)
        return None
    if len(data) < WAV_HEADER_SIZE or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    byte_rate = struct.unpack_from("<I", data, 28)[0]
    data_size = len(data) - WAV_HEADER_SIZE
    if byte_rate <= 0 or data_size <= 0:
        return None
    return int(data_size / byte_rate * 1000)


async def synthesize(text: str, emotion: str = "neutral") -> bytes:
    """兼容占位签名；应用路径走 SoVitsTts.synthesize_to_cache。"""
    client = SoVitsTts()
    clip = await client.synthesize_to_cache(text, emotion)
    return clip.path.read_bytes()
