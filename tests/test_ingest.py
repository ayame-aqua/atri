"""群导出清洗与离线入库。"""

from __future__ import annotations

from pathlib import Path

from src.memory.ingest import clean_export, ingest_candidates, load_candidates_json
from src.memory.store import MemoryStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_clean_drops_system_ads_and_long_digits() -> None:
    raw = (FIXTURES / "group_export_sample.txt").read_text(encoding="utf-8")
    lines = clean_export(raw)
    joined = "\n".join(lines)
    assert "系统消息" not in joined
    assert "加入了群" not in joined
    assert "13812345678" not in joined
    assert "加糖" in joined
    assert "早点睡" in joined


def test_ingest_sample_json_only_pending(tmp_path: Path) -> None:
    store = MemoryStore(
        tmp_path / "memory.sqlite",
        seed=True,
        vector_path=tmp_path / "vectors",
    )
    rows = load_candidates_json(FIXTURES / "group_export_candidates.json")
    written = ingest_candidates(store, rows)
    assert written >= 1
    fact = store.get_by_key("prefers.early_sleep")
    assert fact is not None
    assert fact.status == "pending"
    assert "早点睡" not in store.profile_block()
    styles = store.list_style()
    assert styles
    assert all(item.status == "candidate" for item in styles)
    assert store.style_block() == ""
    episodes = store.list_episodes()
    assert episodes
    assert all(item.status == "pending" for item in episodes)
    assert store.retrieve("早点睡") == []


def test_ingest_script_offline(tmp_path: Path) -> None:
    import subprocess
    import sys

    from src.config import REPO_ROOT

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "ingest_group_export.py"),
            str(FIXTURES / "group_export_sample.txt"),
            "--candidates-json",
            str(FIXTURES / "group_export_candidates.json"),
            "--sqlite",
            str(tmp_path / "memory.sqlite"),
            "--vector",
            str(tmp_path / "vectors"),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    store = MemoryStore(
        tmp_path / "memory.sqlite",
        seed=True,
        vector_path=tmp_path / "vectors",
    )
    fact = store.get_by_key("prefers.early_sleep")
    assert fact is not None
    assert fact.status == "pending"
    assert fact.source == "group_import"
