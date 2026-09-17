"""Web 帧解析。"""

from __future__ import annotations

from src.channels.web import parse_user_text_frame
from src.core.errors import BAD_REQUEST
from src.core.types import InboundMessage


def test_parse_ok() -> None:
    inbound = parse_user_text_frame({"type": "user_text", "message_id": "abc", "text": " 你好 "})
    assert isinstance(inbound, InboundMessage)
    assert inbound.text == "你好"
    assert inbound.chat_id == "web:local"


def test_parse_missing_id() -> None:
    assert parse_user_text_frame({"type": "user_text", "text": "hi"}) == BAD_REQUEST


def test_parse_empty_text() -> None:
    assert (
        parse_user_text_frame({"type": "user_text", "message_id": "x", "text": "  "}) == BAD_REQUEST
    )
