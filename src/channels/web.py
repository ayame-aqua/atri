"""网页 WebSocket 帧 ↔ 内部消息。"""

from __future__ import annotations

import time
from typing import Any

from src.core.errors import BAD_REQUEST
from src.core.types import InboundMessage, OutboundMessage

WEB_CHAT_ID = "web:local"
SENDER_ID = "user"
SENDER_NAME = "你"


def parse_user_text_frame(payload: dict[str, Any]) -> InboundMessage | str:
    """成功返回 Inbound；失败返回错误码。"""
    if payload.get("type") != "user_text":
        return BAD_REQUEST
    message_id = payload.get("message_id")
    text = payload.get("text")
    if not isinstance(message_id, str) or not message_id.strip():
        return BAD_REQUEST
    if not isinstance(text, str) or not text.strip():
        return BAD_REQUEST
    return InboundMessage(
        message_id=message_id.strip(),
        channel="web",
        chat_type="dm",
        chat_id=WEB_CHAT_ID,
        sender_id=SENDER_ID,
        sender_name=SENDER_NAME,
        text=text.strip(),
        created_at=time.time(),
    )


def user_transcript_frame(
    message_id: str,
    text: str,
    *,
    unclear: bool = False,
) -> dict[str, Any]:
    return {
        "type": "user_transcript",
        "message_id": message_id,
        "text": text,
        "unclear": unclear,
    }


def assistant_text_frame(outbound: OutboundMessage) -> dict[str, Any]:
    return {
        "type": "assistant_text",
        "message_id": outbound.message_id,
        "reply_to": outbound.reply_to_id,
        "texts": outbound.texts,
        "emotion": outbound.emotion,
    }


def assistant_audio_frame(
    outbound: OutboundMessage,
    *,
    url: str,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    frame: dict[str, Any] = {
        "type": "assistant_audio",
        "message_id": outbound.message_id,
        "reply_to": outbound.reply_to_id,
        "mime": "audio/wav",
        "url": url,
        "emotion": outbound.emotion,
    }
    if duration_ms is not None:
        frame["duration_ms"] = duration_ms
    return frame


class WebChannel:
    name = "web"

    async def start(self, gateway: object) -> None:
        del gateway

    async def send(self, message: OutboundMessage) -> None:
        del message
