"""P3-A GPT-SoVITS 客户端。"""

from __future__ import annotations

import asyncio
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from src.core.types import OutboundMessage
from src.main import _send_assistant_audio
from src.speech.tts import SoVitsTts, TtsError, _audio_id, _wav_duration_ms


def _tiny_wav() -> bytes:
    byte_rate = 32000
    data = b"\x00" * 3200
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 16000, byte_rate, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self.content = content


class _FakeClient:
    def __init__(self, response: _FakeResponse, captured: dict) -> None:
        self._response = response
        self._captured = captured

    def __call__(self, *args, **kwargs):
        del args, kwargs
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    async def post(self, url: str, json: dict) -> _FakeResponse:
        self._captured["url"] = url
        self._captured["json"] = json
        return self._response


def test_audio_id_stable() -> None:
    assert _audio_id("こんにちは", "happy") == _audio_id("こんにちは", "happy")
    assert _audio_id("こんにちは", "happy") != _audio_id("こんにちは", "shy")


def test_wav_duration(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    path.write_bytes(_tiny_wav())
    duration = _wav_duration_ms(path)
    assert duration is not None
    assert 90 <= duration <= 120


def test_clip_path_rejects_traversal(tmp_path: Path) -> None:
    tts = SoVitsTts(ref_dir=tmp_path / "refs", cache_dir=tmp_path / "cache")
    assert tts.clip_path("../secret") is None
    assert tts.clip_path("not-hex") is None


def test_synthesize_posts_japanese(tmp_path: Path) -> None:
    ref_dir = tmp_path / "refs"
    ref_dir.mkdir()
    (ref_dir / "ref_01.wav").write_bytes(_tiny_wav())
    captured: dict = {}
    fake = _FakeClient(_FakeResponse(200, _tiny_wav()), captured)
    tts = SoVitsTts(api_base="http://sovits.test", ref_dir=ref_dir, cache_dir=tmp_path / "cache")
    with patch("src.speech.tts.httpx.AsyncClient", fake):
        clip = asyncio.run(tts.synthesize_to_cache("ナツメだけど", "neutral"))
        again = asyncio.run(tts.synthesize_to_cache("ナツメだけど", "neutral"))
    assert clip.path.is_file()
    assert again.audio_id == clip.audio_id
    payload = captured["json"]
    assert payload["text_lang"] == "ja"
    assert payload["text"] == "ナツメだけど"
    assert payload["streaming_mode"] is False
    assert payload["text_split_method"] == "cut0"
    assert Path(payload["ref_audio_path"]).is_absolute()
    assert captured["url"].endswith("/tts")


def test_synthesize_http_error(tmp_path: Path) -> None:
    ref_dir = tmp_path / "refs"
    ref_dir.mkdir()
    (ref_dir / "ref_01.wav").write_bytes(_tiny_wav())
    captured: dict = {}
    fake = _FakeClient(_FakeResponse(502, b'{"message":"tts failed","Exception":"boom"}'), captured)
    tts = SoVitsTts(api_base="http://sovits.test", ref_dir=ref_dir, cache_dir=tmp_path / "cache")
    with patch("src.speech.tts.httpx.AsyncClient", fake):
        with pytest.raises(TtsError, match="502"):
            asyncio.run(tts.synthesize_to_cache("こんにちは", "neutral"))


def test_sad_falls_back_to_neutral_ref(tmp_path: Path) -> None:
    ref_dir = tmp_path / "refs"
    ref_dir.mkdir()
    (ref_dir / "ref_01.wav").write_bytes(_tiny_wav())
    captured: dict = {}
    fake = _FakeClient(_FakeResponse(200, _tiny_wav()), captured)
    tts = SoVitsTts(api_base="http://sovits.test", ref_dir=ref_dir, cache_dir=tmp_path / "cache")
    with patch("src.speech.tts.httpx.AsyncClient", fake):
        asyncio.run(tts.synthesize_to_cache("こんにちは", "sad"))
    assert captured["json"]["ref_audio_path"].endswith("ref_01.wav")


class _FakeSocket:
    def __init__(self, tts: object) -> None:
        self.sent: list[dict] = []
        self.app = SimpleNamespace(state=SimpleNamespace(tts=tts))

    async def send_json(self, frame: dict) -> None:
        self.sent.append(frame)


def test_assistant_audio_tts_error_keeps_chat(tmp_path: Path) -> None:
    tts = SoVitsTts(ref_dir=tmp_path / "refs", cache_dir=tmp_path / "cache")

    async def boom(text: str, emotion: str):
        del text, emotion
        raise TtsError("sovits down")

    tts.synthesize_to_cache = boom  # type: ignore[method-assign]
    outbound = OutboundMessage(
        message_id="out",
        reply_to_id="in",
        chat_id="web:local",
        texts=["嗯"],
        speech_ja="こんにちは",
        emotion="neutral",
    )
    socket = _FakeSocket(tts)
    asyncio.run(_send_assistant_audio(socket, outbound))
    assert socket.sent == [
        {"type": "status", "message_id": "out", "state": "tts_failed"},
    ]


def test_assistant_audio_skips_empty_speech(tmp_path: Path) -> None:
    tts = SoVitsTts(ref_dir=tmp_path / "refs", cache_dir=tmp_path / "cache")
    outbound = OutboundMessage(
        message_id="out",
        reply_to_id="in",
        chat_id="web:local",
        texts=["嗯"],
    )
    socket = _FakeSocket(tts)
    asyncio.run(_send_assistant_audio(socket, outbound))
    assert socket.sent == []
