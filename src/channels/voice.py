"""语音输入通道（P3-B；与 Web 共用 Agent / 记忆）。"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from src.channels.web import SENDER_ID, SENDER_NAME, WEB_CHAT_ID
from src.core.errors import BAD_REQUEST
from src.core.types import InboundMessage, OutboundMessage
from src.speech.asr import AsrError, is_clear_transcript
from src.speech.constants import (
    ASR_MAX_AUDIO_BYTES,
    USER_AUDIO_TYPE,
)
from src.speech.debug_log import speech_debug

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    async def transcribe(self, audio_bytes: bytes, mime: str) -> str: ...


@dataclass(frozen=True)
class ParsedUserAudio:
    message_id: str
    mime: str
    audio: bytes


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    unclear: bool


def parse_user_audio_frame(payload: dict[str, Any]) -> ParsedUserAudio | str:
    """成功返回音频；失败返回错误码。"""
    if payload.get("type") != USER_AUDIO_TYPE:
        return BAD_REQUEST
    message_id = payload.get("message_id")
    mime = payload.get("mime")
    data_b64 = payload.get("data_base64")
    if not isinstance(message_id, str) or not message_id.strip():
        return BAD_REQUEST
    if not isinstance(mime, str) or not mime.strip():
        return BAD_REQUEST
    if not isinstance(data_b64, str) or not data_b64.strip():
        return BAD_REQUEST
    try:
        audio = base64.b64decode(data_b64, validate=True)
    except (ValueError, TypeError):
        return BAD_REQUEST
    if not audio or len(audio) > ASR_MAX_AUDIO_BYTES:
        return BAD_REQUEST
    return ParsedUserAudio(
        message_id=message_id.strip(),
        mime=mime.strip(),
        audio=audio,
    )


def inbound_from_transcript(message_id: str, text: str) -> InboundMessage:
    return InboundMessage(
        message_id=message_id.strip(),
        channel="voice",
        chat_type="dm",
        chat_id=WEB_CHAT_ID,
        sender_id=SENDER_ID,
        sender_name=SENDER_NAME,
        text=text.strip(),
        created_at=time.time(),
    )


class VoiceChannel:
    name = "voice"

    def __init__(self, asr: Transcriber | None = None) -> None:
        self._asr = asr

    async def start(self, gateway: object) -> None:
        del gateway

    async def send(self, message: OutboundMessage) -> None:
        del message

    async def transcribe(self, parsed: ParsedUserAudio) -> TranscriptResult:
        if self._asr is None:
            logger.error("voice asr missing message_id=%s", parsed.message_id)
            return TranscriptResult(text="", unclear=True)
        try:
            text = await self._asr.transcribe(parsed.audio, parsed.mime)
        except AsrError:
            logger.exception("asr failed message_id=%s", parsed.message_id)
            speech_debug(
                "asr_fail",
                message_id=parsed.message_id,
                bytes=len(parsed.audio),
                mime=parsed.mime,
            )
            return TranscriptResult(text="", unclear=True)
        if not is_clear_transcript(text):
            logger.info("asr unclear message_id=%s chars=%s", parsed.message_id, len(text))
            speech_debug(
                "asr_unclear",
                message_id=parsed.message_id,
                text=text,
                bytes=len(parsed.audio),
            )
            return TranscriptResult(text=text, unclear=True)
        logger.info("asr ok message_id=%s chars=%s", parsed.message_id, len(text))
        speech_debug(
            "asr_ok",
            message_id=parsed.message_id,
            text=text,
            bytes=len(parsed.audio),
        )
        return TranscriptResult(text=text, unclear=False)
