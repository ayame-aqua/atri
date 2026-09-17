"""Agent：日语台词译成中文气泡（假 LLM）。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.core.agent import Agent
from src.core.llm import LLMError
from src.core.session import SessionStore
from src.core.types import InboundMessage
from src.memory.store import MemoryStore

PERSONA = Path(__file__).resolve().parents[1] / "characters" / "natsume.md"


class FakeLLM:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if not self._replies:
            raise LLMError("empty script")
        return self._replies.pop(0)


def _inbound(message_id: str, text: str) -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        channel="web",
        chat_type="dm",
        chat_id="web:local",
        sender_id="user",
        sender_name="你",
        text=text,
    )


def test_agent_returns_chinese_bubble_and_japanese_speech() -> None:
    llm = FakeLLM(
        [
            '風、うるさい。\n\n[[natsume]]\n{"emotion":"shy","silent":false,"memory_candidates":[]}',
            "今晚风有点大。",
        ]
    )
    agent = Agent(
        persona_path=str(PERSONA),
        llm=llm,  # type: ignore[arg-type]
        sessions=SessionStore(max_turns=40),
        memory=MemoryStore(),
    )
    outbound = asyncio.run(agent.run(_inbound("m1", "外面好吵")))
    assert outbound.speech_ja == "風、うるさい。"
    assert outbound.texts == ["今晚风有点大。"]
    assert outbound.emotion == "shy"
    assert outbound.silent is False
    assert "[[natsume]]" not in outbound.texts[0]
    assert agent._memory.profile_block() == ""


def test_agent_keeps_history_for_next_turn() -> None:
    llm = FakeLLM(
        [
            'うん。\n\n[[natsume]]\n{"emotion":"neutral","silent":false,"memory_candidates":[]}',
            "嗯。",
            'さっき「こんにちは」って言ったでしょ。\n\n[[natsume]]\n{"emotion":"neutral","silent":false,"memory_candidates":[]}',
            "你上一句说了你好。",
        ]
    )
    agent = Agent(
        persona_path=str(PERSONA),
        llm=llm,  # type: ignore[arg-type]
        sessions=SessionStore(max_turns=40),
        memory=MemoryStore(),
    )
    asyncio.run(agent.run(_inbound("m1", "你好")))
    asyncio.run(agent.run(_inbound("m2", "我上一句说了什么")))
    third_prompt = llm.calls[2]
    user_contents = [item["content"] for item in third_prompt if item["role"] == "user"]
    assert "你好" in user_contents
