"""用户纠正写入相处笔记。"""

from __future__ import annotations

from pathlib import Path

from src.core.living_notes import (
    LivingNotesStore,
    looks_like_correction,
    parse_extracted_rule,
)


def test_correction_markers() -> None:
    assert looks_like_correction("这句有点ooc了")
    assert looks_like_correction("太抬杠了")
    assert not looks_like_correction("你好呀")


def test_parse_extracted_rule_truncates() -> None:
    rule = parse_extracted_rule('{"rule": "被夸后不要拆成几分真假来反问"}')
    assert rule == "被夸后不要拆成几分真假来反问"
    assert parse_extracted_rule('{"rule": null}') is None


def test_store_persists_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "living_notes.json"
    store = LivingNotesStore(path, max_notes=2)
    assert store.add("被夸后不要拆逻辑")
    assert not store.add("被夸后不要拆逻辑")
    store.add("不要当咖啡馆服务员")
    store.add("不要报履历")
    again = LivingNotesStore(path, max_notes=2)
    block = again.as_block()
    assert "不要报履历" in block
    assert "不要当咖啡馆服务员" in block
    assert "拆逻辑" not in block
