"""HTTP 健康检查与人设元数据。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from src.config import load_config
from src.main import create_app
from src.memory.store import MemoryStore


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


def test_memory_page() -> None:
    client = TestClient(create_app())
    response = client.get("/memory")
    assert response.status_code == 200
    assert "记忆" in response.text
    assert "待确认" in response.text


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
