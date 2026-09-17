"""HTTP 健康检查与人设元数据。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from src.main import create_app


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
