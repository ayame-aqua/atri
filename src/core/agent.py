"""拼 prompt、调 LLM、解析尾块、中文气泡译成日语备 TTS。"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from src.core.living_notes import (
    LivingNotesStore,
    absorb_correction,
    looks_like_correction,
)
from src.core.llm import LLMClient, LLMError
from src.core.lore import CONSTANT_FACTS, SCENARIO, trailing_system
from src.core.persona import load_persona
from src.core.protocol import parse
from src.core.session import SessionStore, Turn
from src.core.text_style import soften_chinese_punctuation
from src.core.translate import chinese_to_japanese
from src.core.types import InboundMessage, OutboundMessage
from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)

WEB_CHANNEL_RULES: Final[str] = (
    "现在是网页私聊，必须回复。"
    "[[natsume]] 里 silent 必须是 false。"
    "用户说中文；你只输出中文台词。"
)


class Agent:
    def __init__(
        self,
        *,
        persona_path: str,
        llm: LLMClient,
        sessions: SessionStore,
        memory: MemoryStore | None = None,
        living_notes: LivingNotesStore | None = None,
    ) -> None:
        self._persona_path = persona_path
        self._llm = llm
        self._sessions = sessions
        self._memory = memory or MemoryStore()
        self._living_notes = living_notes

    async def run(self, inbound: InboundMessage) -> OutboundMessage:
        if self._living_notes is not None and looks_like_correction(inbound.text):
            await absorb_correction(
                self._llm,
                self._living_notes,
                user_text=inbound.text,
                last_reply=self._last_assistant(inbound.chat_id),
            )
        self._memory.apply_user_text(inbound.text)
        persona = load_persona(self._persona_path)
        profile = self._memory.profile_block()
        system_parts = [persona]
        if profile:
            system_parts.append("核心事实：\n" + profile)
        system_parts.extend([WEB_CHANNEL_RULES, SCENARIO, CONSTANT_FACTS])
        notes_block = self._living_notes.as_block() if self._living_notes else ""
        if notes_block:
            system_parts.append(notes_block)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(system_parts)},
        ]
        for turn in self._sessions.history(inbound.chat_id):
            messages.append({"role": turn.role, "content": turn.text})
        messages.append({"role": "user", "content": inbound.text})
        messages.append({"role": "system", "content": trailing_system(inbound.text)})

        try:
            raw = await self._llm.chat(messages)
        except LLMError:
            logger.exception("agent llm failed message_id=%s", inbound.message_id)
            raise

        parsed = parse(raw)
        if parsed.log_level == "error":
            logger.error("natsume block parse failed message_id=%s", inbound.message_id)
        elif parsed.log_level == "warning":
            logger.warning("natsume block degraded message_id=%s", inbound.message_id)
        self._memory.ingest_candidates(parsed.memory_candidates, parse_ok=parsed.parse_ok)

        zh = soften_chinese_punctuation(parsed.visible_text)
        if not zh:
            raise LLMError("empty speech after parse")

        speech_ja = await chinese_to_japanese(self._llm, zh)
        outbound = OutboundMessage(
            message_id=str(uuid.uuid4()),
            reply_to_id=inbound.message_id,
            chat_id=inbound.chat_id,
            texts=[zh],
            speech_ja=speech_ja or None,
            emotion=parsed.emotion,
            silent=False,
        )
        self._sessions.append(
            inbound.chat_id,
            Turn(role="user", text=inbound.text),
        )
        self._sessions.append(
            inbound.chat_id,
            Turn(
                role="assistant",
                text=zh,
                emotion=parsed.emotion,
                speech_ja=speech_ja or None,
            ),
        )
        return outbound

    def _last_assistant(self, chat_id: str) -> str:
        for turn in reversed(self._sessions.history(chat_id)):
            if turn.role == "assistant":
                return turn.text
        return ""
