"""拼 prompt、调 LLM、解析尾块、译成中文气泡。"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from src.core.llm import LLMClient, LLMError
from src.core.persona import load_persona
from src.core.protocol import parse
from src.core.session import SessionStore, Turn
from src.core.translate import japanese_to_chinese
from src.core.types import InboundMessage, OutboundMessage
from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)

WEB_CHANNEL_RULES: Final[str] = (
    "现在是网页私聊。必须回复。"
    "[[natsume]] 里 silent 必须是 false。"
    "用户说中文；你只输出日语台词，不要输出中文正文。"
)


class Agent:
    def __init__(
        self,
        *,
        persona_path: str,
        llm: LLMClient,
        sessions: SessionStore,
        memory: MemoryStore | None = None,
    ) -> None:
        self._persona_path = persona_path
        self._llm = llm
        self._sessions = sessions
        self._memory = memory or MemoryStore()

    async def run(self, inbound: InboundMessage) -> OutboundMessage:
        persona = load_persona(self._persona_path)
        profile = self._memory.profile_block()
        system_parts = [persona, WEB_CHANNEL_RULES]
        if profile:
            system_parts.append("核心事实：\n" + profile)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(system_parts)},
        ]
        for turn in self._sessions.history(inbound.chat_id):
            messages.append({"role": turn.role, "content": turn.text})
        messages.append({"role": "user", "content": inbound.text})

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

        speech_ja = parsed.visible_text.strip()
        if not speech_ja:
            raise LLMError("empty speech after parse")

        zh = await japanese_to_chinese(self._llm, speech_ja)
        outbound = OutboundMessage(
            message_id=str(uuid.uuid4()),
            reply_to_id=inbound.message_id,
            chat_id=inbound.chat_id,
            texts=[zh],
            speech_ja=speech_ja,
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
                speech_ja=speech_ja,
            ),
        )
        return outbound
