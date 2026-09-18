"""P2-B：pending、风格、情节向量检索。"""

from __future__ import annotations

from pathlib import Path

from src.memory.store import MemoryStore


def _store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(
        tmp_path / "memory.sqlite",
        seed=False,
        vector_path=tmp_path / "vectors",
    )


def test_pending_fact_not_in_profile(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.ingest_candidates(
        [{"key": "relationship", "value": "已婚", "layer": "profile"}],
        parse_ok=True,
    )
    rel = store.get_by_key("relationship")
    assert rel is not None
    assert rel.status == "pending"
    assert "已婚" not in store.profile_block()
    store.update_fact(rel.id, status="active")
    assert "已婚" in store.profile_block()


def test_protected_active_not_overwritten_by_extract(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite", seed=True, vector_path=tmp_path / "v")
    store.ingest_candidates(
        [{"key": "relationship", "value": "已婚", "layer": "profile"}],
        parse_ok=True,
    )
    rel = store.get_by_key("relationship")
    assert rel is not None
    assert rel.value == "与四季夏目"
    assert rel.status == "active"


def test_style_candidate_not_injected_until_confirm(tmp_path: Path) -> None:
    store = _store(tmp_path)
    term = store.add_style_term("加糖", "事情顺利", usage="随口说")
    assert term.status == "candidate"
    assert store.style_block() == ""
    store.confirm_style(term.id)
    block = store.style_block()
    assert "加糖" in block
    assert "不是当前对话" in block


def test_retrieve_active_episode_not_pending(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pending = store.add_episode("他说明天要出差开会", status="pending")
    assert store.retrieve("出差开会") == []
    store.update_episode(pending.id, status="active")
    store.add_episode("上周一起喝了加很多糖的咖啡", status="active")
    hits = store.retrieve("出差 开会")
    assert hits
    assert any("出差" in item.summary for item in hits)
    assert all(item.status == "active" for item in hits)
    block = store.episodes_block("明天出差")
    assert "不是当前对话" in block
    assert "出差" in block


def test_summarize_turns_one_line() -> None:
    import asyncio

    from src.core.session import Turn
    from src.memory.summarize import summarize_turns

    class _Fake:
        async def chat(self, messages: list[dict[str, str]]) -> str:
            del messages
            return "你们约了早点睡\n第二行不要"

    text = asyncio.run(summarize_turns(_Fake(), [Turn(role="user", text="今晚早点睡")]))
    assert text == "你们约了早点睡"
