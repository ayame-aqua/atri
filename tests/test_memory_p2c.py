"""P2-C：mem0 接法、检索门槛、日记、核心印象、相处状态。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.core.agent import Agent
from src.core.session import SessionStore
from src.core.types import InboundMessage
from src.memory.constants import DEFAULT_CYCLE_ENABLED, DEFAULT_EPISODE_MIN_SCORE
from src.memory.mood import mood_delta_from_text
from src.memory.store import MemoryStore
from src.memory.vectors import distance_to_score


def _store(tmp_path: Path, **kwargs) -> MemoryStore:
    return MemoryStore(
        tmp_path / "memory.sqlite",
        seed=False,
        vector_path=tmp_path / "vectors",
        **kwargs,
    )


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


def test_cycle_disabled_by_default() -> None:
    store = MemoryStore()
    assert store.cycle_enabled is False
    assert DEFAULT_CYCLE_ENABLED is False
    forced = MemoryStore(cycle_enabled=True)
    assert forced.cycle_enabled is False


def test_add_search_update_forget(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fact = store.add("讨厌被催", key="dislikes.rushed", status="pending")
    assert fact.status == "pending"
    assert "被催" not in store.profile_block()
    store.update(fact.id, status="active")
    hits = store.search("被催")
    assert any(hit.fact is not None and hit.fact.key == "dislikes.rushed" for hit in hits)
    store.forget("被催")
    assert "被催" not in store.profile_block()


def test_search_early_sleep_same_index(tmp_path: Path) -> None:
    store = _store(tmp_path, min_score=0.2)
    store.add_episode("上周说过要早睡", status="active")
    hits = store.search("早睡")
    assert any(hit.episode is not None and "早睡" in hit.episode.summary for hit in hits)


def test_low_score_episode_not_injected(tmp_path: Path) -> None:
    store = _store(tmp_path, min_score=0.85)
    store.add_episode("上周约了早点睡", status="active")
    assert store.retrieve("量子力学论文") == []
    assert store.episodes_block("量子力学论文") == ""


def test_pending_extract_not_in_prompt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add("明天去医院", key="promise.hospital", status="pending")
    assert "医院" not in store.profile_block()


def test_impression_and_diary_blocks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pending = store.set_impression("她觉得你会熬夜", status="pending")
    assert store.impression_block() == ""
    store.update_impression(pending.id, status="active")
    block = store.impression_block()
    assert "熬夜" in block
    assert "不是刚才这句" in block
    store.upsert_diary("今天说了早点睡", day="2026-09-19")
    diary = store.diary_block()
    assert "2026-09-19" in diary
    assert "日记，不是此刻" in diary


def test_mood_praise_and_order(tmp_path: Path) -> None:
    store = _store(tmp_path)
    praised = store.apply_mood_from_text("谢谢你 喜欢你")
    assert praised.affection > 0
    ordered = store.apply_mood_from_text("快点给我做 闭嘴")
    assert ordered.irritation > praised.irritation
    prompt = store.mood_prompt_block()
    assert "相处状态" in prompt
    assert "不要改 emotion" in prompt


def test_mood_delta_helpers() -> None:
    praise = mood_delta_from_text("谢谢")
    order = mood_delta_from_text("快点给我做")
    assert praise.affection > 0
    assert order.irritation > 0
    assert distance_to_score(0.0) == 1.0
    assert distance_to_score(2.0) == 0.0


def test_export_markdown_not_empty(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add_fact("prefers.tea", "喝茶", category="preference", status="active")
    dest = tmp_path / "export.md"
    path = store.export_markdown(dest)
    text = path.read_text(encoding="utf-8")
    assert "喝茶" in text
    assert "cycle_enabled: False" in text


def test_agent_assembly_order_and_pending_hidden(tmp_path: Path) -> None:
    from tests.test_agent import PERSONA

    class _Fake:
        def __init__(self) -> None:
            self.calls: list[list[dict[str, str]]] = []

        async def chat(self, messages: list[dict[str, str]]) -> str:
            self.calls.append(messages)
            if len(self.calls) == 1:
                return (
                    '嗯\n\n[[natsume]]\n{"emotion":"neutral","silent":false,"memory_candidates":[]}'
                )
            if len(self.calls) == 2:
                return "うん"
            return (
                '{"facts":[{"key":"promise.hospital","value":"明天医院"}],'
                '"impression":null,"diary":null}'
            )

    memory = _store(tmp_path)
    memory.add("已婚", key="relationship", status="pending")
    memory.set_impression("她记得你会熬夜", status="active")
    memory.add_style_term("加糖", "事情顺利", status="confirmed")
    memory.add_episode("上周说过要早睡", status="active")
    memory.upsert_diary("聊过早睡", day="2026-09-18")
    llm = _Fake()
    agent = Agent(
        persona_path=str(PERSONA),
        llm=llm,  # type: ignore[arg-type]
        sessions=SessionStore(max_turns=40),
        memory=memory,
        extract_every_n=1,
    )
    asyncio.run(agent.run(_inbound("m1", "今晚还早睡吗")))
    system = llm.calls[0][0]["content"]
    assert "已婚" not in system
    persona_at = system.find("你是四季夏目")
    profile_at = system.find("核心事实")
    impression_at = system.find("核心印象")
    mood_at = system.find("相处状态")
    style_at = system.find("加糖")
    diary_at = system.find("最近日记")
    episode_at = system.find("早睡")
    assert persona_at != -1
    assert impression_at > persona_at
    assert mood_at > impression_at
    assert style_at > mood_at
    assert diary_at > style_at
    assert episode_at > diary_at
    if profile_at != -1:
        assert profile_at < impression_at
    hospital = memory.get_by_key("promise.hospital")
    assert hospital is not None
    assert hospital.status == "pending"
    assert "医院" not in memory.profile_block()


def test_min_score_constant() -> None:
    assert DEFAULT_EPISODE_MIN_SCORE == 0.35
