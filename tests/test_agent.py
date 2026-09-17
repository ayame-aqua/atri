"""Agent：中文台词译成日语备 TTS（假 LLM）。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.core.agent import Agent
from src.core.living_notes import LivingNotesStore
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
            '四季夏目。就这些。\n\n[[natsume]]\n{"emotion":"shy","silent":false,"memory_candidates":[]}',
            "ナツメだけど",
        ]
    )
    agent = Agent(
        persona_path=str(PERSONA),
        llm=llm,  # type: ignore[arg-type]
        sessions=SessionStore(max_turns=40),
        memory=MemoryStore(),
    )
    outbound = asyncio.run(agent.run(_inbound("m1", "外面好吵")))
    first_prompt = llm.calls[0]
    assert first_prompt[-2]["role"] == "user"
    assert first_prompt[-1]["role"] == "system"
    assert "发消息" in first_prompt[-1]["content"]
    assert outbound.speech_ja == "ナツメだけど"
    assert outbound.texts == ["四季夏目，就这些"]
    assert outbound.emotion == "shy"
    assert outbound.silent is False
    assert "[[natsume]]" not in outbound.texts[0]
    assert agent._memory.profile_block() == ""


def test_agent_keeps_history_for_next_turn() -> None:
    llm = FakeLLM(
        [
            '嗯\n\n[[natsume]]\n{"emotion":"neutral","silent":false,"memory_candidates":[]}',
            "うん",
            '你上一句说了你好\n\n[[natsume]]\n{"emotion":"neutral","silent":false,"memory_candidates":[]}',
            "さっき「こんにちは」って言ったでしょ",
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


def test_agent_absorbs_correction_into_prompt(tmp_path: Path) -> None:
    notes = LivingNotesStore(tmp_path / "living_notes.json")
    llm = FakeLLM(
        [
            '{"rule": "被夸后不要拆成几分真假来反问"}',
            '嗯\n\n[[natsume]]\n{"emotion":"shy","silent":false,"memory_candidates":[]}',
            "うん",
        ]
    )
    agent = Agent(
        persona_path=str(PERSONA),
        llm=llm,  # type: ignore[arg-type]
        sessions=SessionStore(max_turns=40),
        memory=MemoryStore(),
        living_notes=notes,
    )
    asyncio.run(agent.run(_inbound("m1", "这句有点ooc了")))
    assert "拆成几分" in notes.as_block()
    assert "拆成几分" in llm.calls[1][0]["content"]
