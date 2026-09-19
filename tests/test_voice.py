"""P3-B 语音帧与没听清降级。"""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

from src.channels.voice import VoiceChannel, inbound_from_transcript, parse_user_audio_frame
from src.channels.web import user_transcript_frame
from src.core.errors import BAD_REQUEST
from src.core.types import InboundMessage
from src.gateway import HandleResult
from src.main import _handle_user_audio
from src.speech.constants import UNCLEAR_REPLY


def test_parse_user_audio_ok() -> None:
    raw = base64.b64encode(b"abcd" * 80).decode()
    parsed = parse_user_audio_frame(
        {
            "type": "user_audio",
            "message_id": "m1",
            "mime": "audio/webm",
            "data_base64": raw,
        }
    )
    assert not isinstance(parsed, str)
    assert parsed.message_id == "m1"
    assert parsed.audio == b"abcd" * 80


def test_parse_user_audio_bad_base64() -> None:
    assert (
        parse_user_audio_frame(
            {
                "type": "user_audio",
                "message_id": "m1",
                "mime": "audio/webm",
                "data_base64": "%%%",
            }
        )
        == BAD_REQUEST
    )


def test_inbound_from_transcript_uses_voice_channel() -> None:
    inbound = inbound_from_transcript("m1", " 晚上喝茶 ")
    assert inbound.channel == "voice"
    assert inbound.chat_id == "web:local"
    assert inbound.text == "晚上喝茶"


def test_user_transcript_frame() -> None:
    frame = user_transcript_frame("m1", "", unclear=True)
    assert frame["type"] == "user_transcript"
    assert frame["unclear"] is True


class _FakeAsr:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def transcribe(self, audio: bytes, mime: str) -> str:
        del audio, mime
        self.calls += 1
        return self.text


class _FakeGateway:
    def __init__(self) -> None:
        self.seen: list[InboundMessage] = []

    async def handle(self, inbound: InboundMessage) -> HandleResult:
        self.seen.append(inbound)
        return HandleResult(error_code="LLM_FAILED")


class _FakeSocket:
    def __init__(self, voice: VoiceChannel) -> None:
        self.sent: list[dict] = []
        self.app = SimpleNamespace(state=SimpleNamespace(voice=voice))

    async def send_json(self, frame: dict) -> None:
        self.sent.append(frame)


def _audio_payload() -> dict:
    return {
        "type": "user_audio",
        "message_id": "m-voice",
        "mime": "audio/webm",
        "data_base64": base64.b64encode(b"abcd" * 80).decode(),
    }


def test_unclear_does_not_call_gateway() -> None:
    asr = _FakeAsr("……")
    voice = VoiceChannel(asr)
    gateway = _FakeGateway()
    socket = _FakeSocket(voice)
    asyncio.run(_handle_user_audio(socket, gateway, _audio_payload()))
    assert gateway.seen == []
    assert asr.calls == 1
    states = [frame.get("state") for frame in socket.sent if frame.get("type") == "status"]
    assert "unclear" in states
    assert any(frame.get("unclear") for frame in socket.sent)
    assert any(frame.get("message") == UNCLEAR_REPLY for frame in socket.sent)


def test_clear_transcript_goes_to_gateway() -> None:
    asr = _FakeAsr("晚上喝茶")
    voice = VoiceChannel(asr)
    gateway = _FakeGateway()
    socket = _FakeSocket(voice)
    asyncio.run(_handle_user_audio(socket, gateway, _audio_payload()))
    assert len(gateway.seen) == 1
    inbound = gateway.seen[0]
    assert isinstance(inbound, InboundMessage)
    assert inbound.text == "晚上喝茶"
    assert inbound.channel == "voice"
