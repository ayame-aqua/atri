"""HTTP 健康检查与人设元数据。"""

from __future__ import annotations

import struct
from pathlib import Path

from fastapi.testclient import TestClient
from src.config import load_config
from src.main import create_app
from src.memory.store import MemoryStore


def _tiny_wav() -> bytes:
    byte_rate = 32000
    data = b"\x00" * 3200
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 16000, byte_rate, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


def test_health_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True


def test_character_name() -> None:
    client = TestClient(create_app())
    response = client.get("/api/character")
    assert response.status_code == 200
    assert response.json()["name"] == "四季夏目"


def test_index_page() -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert "四季夏目" in response.text
    assert "/memory" in response.text
    assert "对话" in response.text


def test_memory_page() -> None:
    client = TestClient(create_app())
    response = client.get("/memory")
    assert response.status_code == 200
    assert "记忆" in response.text
    assert "待确认" in response.text


def test_tts_media_unknown_id() -> None:
    client = TestClient(create_app())
    response = client.get("/media/tts/deadbeefdeadbeef")
    assert response.status_code == 404


def test_tts_media_serves_cached(tmp_path: Path) -> None:
    cache = tmp_path / "tts_cache"
    cache.mkdir()
    audio_id = "0123456789abcdef"
    (cache / f"{audio_id}.wav").write_bytes(_tiny_wav())
    settings = load_config()
    speech_cfg = dict(settings.get("speech") or {})
    speech_cfg["tts_cache_dir"] = str(cache)
    speech_cfg["tts_ref_dir"] = str(tmp_path / "refs")
    settings["speech"] = speech_cfg
    client = TestClient(create_app(settings))
    response = client.get(f"/media/tts/{audio_id}")
    assert response.status_code == 200
    assert response.content[:4] == b"RIFF"


def test_memory_mood_and_export(tmp_path: Path) -> None:
    sqlite = tmp_path / "memory.sqlite"
    vectors = tmp_path / "vectors"
    MemoryStore(sqlite, seed=True, vector_path=vectors)
    settings = load_config()
    memory_cfg = dict(settings.get("memory") or {})
    memory_cfg["sqlite_path"] = str(sqlite)
    memory_cfg["vector_path"] = str(vectors)
    settings["memory"] = memory_cfg
    client = TestClient(create_app(settings))
    mood = client.get("/api/memory/mood")
    assert mood.status_code == 200
    body = mood.json()
    assert body["cycle_enabled"] is False
    assert "energy" in body
    exported = client.post("/api/memory/export")
    assert exported.status_code == 200
    assert exported.json()["path"].endswith("export.md")


def test_summarize_empty_session() -> None:
    client = TestClient(create_app())
    response = client.post("/api/memory/summarize-session", json={"chat_id": "web:local"})
    assert response.status_code == 400


def test_style_and_episode_http_confirm(tmp_path: Path) -> None:
    sqlite = tmp_path / "memory.sqlite"
    vectors = tmp_path / "vectors"
    store = MemoryStore(sqlite, seed=True, vector_path=vectors)
    episode = store.add_episode("上周说过要早睡", status="pending")
    style = store.add_style_term("加糖", "事情顺利")
    episode_id = episode.id
    style_id = style.id
    del store

    settings = load_config()
    memory_cfg = dict(settings.get("memory") or {})
    memory_cfg["sqlite_path"] = str(sqlite)
    memory_cfg["vector_path"] = str(vectors)
    settings["memory"] = memory_cfg
    client = TestClient(create_app(settings))
    confirmed_ep = client.post(f"/api/memory/episodes/{episode_id}/confirm")
    assert confirmed_ep.status_code == 200
    assert confirmed_ep.json()["status"] == "active"
    confirmed_style = client.post(f"/api/memory/style/{style_id}/confirm")
    assert confirmed_style.status_code == 200
    assert confirmed_style.json()["status"] == "confirmed"
