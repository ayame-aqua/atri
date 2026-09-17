"""内部消息与协议常量。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ChannelName = Literal["web", "voice", "qq", "wechat"]
ChatType = Literal["dm", "group", "system"]
Emotion = Literal["neutral", "happy", "sad", "angry", "shy"]

EMOTIONS: frozenset[str] = frozenset({"neutral", "happy", "sad", "angry", "shy"})

NATSUME_MARKER = "[[natsume]]"


@dataclass
class InboundMessage:
    message_id: str
    channel: ChannelName
    chat_type: ChatType
    chat_id: str
    sender_id: str
    sender_name: str
    text: str
    mentioned_self: bool = False
    created_at: float = 0.0
    reply_to: dict[str, str] | None = None
    raw_type: str | None = None
    vision: Any | None = None
    attachments: list[Any] | None = None


@dataclass
class OutboundMessage:
    message_id: str
    reply_to_id: str
    chat_id: str
    texts: list[str] = field(default_factory=list)
    emotion: Emotion = "neutral"
    audio_url: str | None = None
    visemes: Any | None = None
    silent: bool = False
    sticker_ids: list[str] | None = None


@dataclass
class ParsedNatsumeBlock:
    visible_text: str
    emotion: Emotion
    silent: bool
    memory_candidates: list[Any]
    parse_ok: bool
    log_level: str  # debug | warning | error
