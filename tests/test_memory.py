"""P2-A SQLite 事实。"""

from __future__ import annotations

from pathlib import Path

from src.core.protocol import parse
from src.memory.store import KEY_NICKNAME, MemoryStore


def test_seed_and_persist(tmp_path: Path) -> None:
    path = tmp_path / "memory.sqlite"
    first = MemoryStore(path, seed=True)
    assert "你" in first.profile_block()
    first.apply_user_text("记住：我讨厌被催")
    first.apply_user_text("我叫李雷，你叫我雷雷")
    again = MemoryStore(path, seed=True)
    block = again.profile_block()
    assert "雷雷" in block
    assert "讨厌被催" in block
    nick = again.get_by_key(KEY_NICKNAME)
    assert nick is not None
    assert nick.value == "雷雷"


def test_forget_archives(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite", seed=True)
    store.apply_user_text("记住：我讨厌被催")
    hits = store.forget("被催")
    assert hits
    assert "讨厌被催" not in store.profile_block()


def test_candidates_need_parse_ok_and_low_risk(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.sqlite", seed=False)
    store.ingest_candidates(
        [{"key": "relationship", "value": "已婚", "layer": "profile"}],
        parse_ok=True,
    )
    assert store.get_by_key("relationship") is None
    bad = parse("没有尾块")
    store.ingest_candidates(
        [{"key": "prefers.tea", "value": "喝茶"}],
        parse_ok=bad.parse_ok,
    )
    assert store.get_by_key("prefers.tea") is None
    store.ingest_candidates(
        [{"key": "prefers.tea", "value": "喝茶不喝咖啡", "layer": "profile"}],
        parse_ok=True,
    )
    tea = store.get_by_key("prefers.tea")
    assert tea is not None
    assert tea.value == "喝茶不喝咖啡"
