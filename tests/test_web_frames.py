"""Web 帧解析。"""

from __future__ import annotations

from src.channels.web import assistant_audio_frame, parse_user_text_frame, user_transcript_frame
from src.core.errors import BAD_REQUEST
from src.core.types import InboundMessage, OutboundMessage


def test_parse_ok() -> None:
    inbound = parse_user_text_frame({"type": "user_text", "message_id": "abc", "text": " 你好 "})
    assert isinstance(inbound, InboundMessage)
    assert inbound.text == "你好"
    assert inbound.chat_id == "web:local"


def test_parse_missing_id() -> None:
    assert parse_user_text_frame({"type": "user_text", "text": "hi"}) == BAD_REQUEST


def test_assistant_audio_frame() -> None:
    outbound = OutboundMessage(
        message_id="out",
        reply_to_id="in",
        chat_id="web:local",
        texts=["嗯"],
        emotion="shy",
    )
    frame = assistant_audio_frame(outbound, url="/media/tts/ab", duration_ms=1200)
    assert frame["type"] == "assistant_audio"
    assert frame["url"] == "/media/tts/ab"
    assert frame["duration_ms"] == 1200
    assert frame["emotion"] == "shy"


def test_user_transcript_frame() -> None:
    frame = user_transcript_frame("m1", "在吗")
    assert frame["type"] == "user_transcript"
    assert frame["text"] == "在吗"
    assert frame["unclear"] is False
