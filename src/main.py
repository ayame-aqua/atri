"""四季夏目应用入口：FastAPI + WebSocket 网页聊天。"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.channels.web import assistant_text_frame, parse_user_text_frame
from src.config import REPO_ROOT, load_config
from src.core.agent import Agent
from src.core.errors import BAD_REQUEST, human_message
from src.core.living_notes import LivingNotesStore
from src.core.llm import LLMClient, LLMError
from src.core.persona import split_persona
from src.core.session import SessionStore
from src.gateway import Gateway
from src.memory.store import Fact, MemoryStore

logger = logging.getLogger(__name__)
WEB_DIR = REPO_ROOT / "web"


def _build_llm(config: dict[str, Any]) -> LLMClient:
    llm_cfg = config.get("llm") or {}
    timeout_s = float(llm_cfg.get("timeout_s", 60))
    disable_thinking = bool(llm_cfg.get("disable_thinking", True))
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-flash")
    return LLMClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_s=timeout_s,
        disable_thinking=disable_thinking,
    )


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    settings = config if config is not None else load_config()
    persona_rel = str(settings.get("character", "characters/natsume.md"))
    persona_path = persona_rel if os.path.isabs(persona_rel) else str(REPO_ROOT / persona_rel)
    session_cfg = settings.get("session") or {}
    max_turns = int(session_cfg.get("max_turns", 20))
    gateway_cfg = settings.get("gateway") or {}
    dedup_ttl_s = float(gateway_cfg.get("dedup_ttl_s", 600))
    server_cfg = settings.get("server") or {}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        try:
            llm = _build_llm(settings)
        except LLMError:
            logger.exception("llm client init failed")
            llm = None
        sessions = SessionStore(max_turns=max_turns * 2)
        memory_cfg = settings.get("memory") or {}
        sqlite_rel = str(memory_cfg.get("sqlite_path", "data/memory.sqlite"))
        sqlite_path = Path(sqlite_rel) if os.path.isabs(sqlite_rel) else REPO_ROOT / sqlite_rel
        memory = MemoryStore(sqlite_path, seed=True)
        living_notes = LivingNotesStore(REPO_ROOT / "data" / "living_notes.json")
        agent = (
            Agent(
                persona_path=persona_path,
                llm=llm,
                sessions=sessions,
                memory=memory,
                living_notes=living_notes,
            )
            if llm is not None
            else None
        )
        app.state.gateway = Gateway(dedup_ttl_s=dedup_ttl_s, agent=agent)
        app.state.memory = memory
        app.state.persona_path = persona_path
        app.state.llm_ready = llm is not None
        logger.info(
            "natsume web listening host=%s port=%s llm_ready=%s",
            server_cfg.get("host", "127.0.0.1"),
            server_cfg.get("port", 8787),
            app.state.llm_ready,
        )
        yield

    app = FastAPI(title="shiki-natsume", lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "llm_ready": bool(getattr(app.state, "llm_ready", False))}

    @app.get("/api/character")
    async def character() -> dict[str, Any]:
        meta, _body = split_persona(persona_path)
        name = meta.get("name") if isinstance(meta.get("name"), str) else "四季夏目"
        return {"name": name}

    @app.get("/memory")
    async def memory_page() -> FileResponse:
        return FileResponse(WEB_DIR / "memory.html")

    @app.get("/api/memory/facts")
    async def list_memory_facts(status: str = "active") -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        filter_status = None if status in {"", "all"} else status
        return {"facts": [_fact_json(item) for item in memory.list_facts(status=filter_status)]}

    @app.post("/api/memory/facts")
    async def create_memory_fact(payload: dict[str, Any]) -> dict[str, Any]:
        key = payload.get("key")
        value = payload.get("value")
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(status_code=400, detail="key required")
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(status_code=400, detail="value required")
        category = payload.get("category", "other")
        if not isinstance(category, str):
            category = "other"
        memory: MemoryStore = app.state.memory
        fact = memory.add_fact(
            key.strip(),
            value.strip(),
            category=category,
            source="manual",
            overwrite=True,
        )
        return _fact_json(fact)

    @app.patch("/api/memory/facts/{fact_id}")
    async def patch_memory_fact(fact_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        value = payload.get("value") if isinstance(payload.get("value"), str) else None
        status = payload.get("status") if isinstance(payload.get("status"), str) else None
        fact = memory.update_fact(fact_id, value=value, status=status)
        if fact is None:
            raise HTTPException(status_code=404, detail="fact not found")
        return _fact_json(fact)

    @app.delete("/api/memory/facts/{fact_id}")
    async def delete_memory_fact(fact_id: int) -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        if not memory.delete_fact(fact_id):
            raise HTTPException(status_code=404, detail="fact not found")
        return {"ok": True}

    @app.post("/api/memory/forget")
    async def forget_memory(payload: dict[str, Any]) -> dict[str, Any]:
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            raise HTTPException(status_code=400, detail="query required")
        memory: MemoryStore = app.state.memory
        hits = memory.forget(query.strip())
        return {"facts": [_fact_json(item) for item in hits]}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.websocket("/ws/chat")
    async def chat_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        gateway: Gateway = app.state.gateway
        try:
            while True:
                raw = await websocket.receive_text()
                await _handle_socket_text(websocket, gateway, raw)
        except WebSocketDisconnect:
            logger.info("websocket disconnected")

    if WEB_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")
    return app


async def _handle_socket_text(websocket: WebSocket, gateway: Gateway, raw: str) -> None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        await _send_error(websocket, None, BAD_REQUEST)
        return
    if not isinstance(payload, dict):
        await _send_error(websocket, None, BAD_REQUEST)
        return

    inbound = parse_user_text_frame(payload)
    if isinstance(inbound, str):
        await _send_error(websocket, payload.get("message_id"), inbound)
        return

    await websocket.send_json(
        {"type": "status", "message_id": inbound.message_id, "state": "thinking"}
    )
    result = await gateway.handle(inbound)
    if result.error_code or result.outbound is None:
        await _send_error(
            websocket,
            inbound.message_id,
            result.error_code or "INTERNAL",
        )
        await websocket.send_json(
            {"type": "status", "message_id": inbound.message_id, "state": "idle"}
        )
        return

    if result.replay:
        await websocket.send_json({"type": "duplicate", "message_id": inbound.message_id})
    await websocket.send_json(assistant_text_frame(result.outbound))
    await websocket.send_json({"type": "status", "message_id": inbound.message_id, "state": "idle"})


async def _send_error(websocket: WebSocket, message_id: Any, code: str) -> None:
    frame: dict[str, Any] = {
        "type": "error",
        "code": code,
        "message": human_message(code),
    }
    if isinstance(message_id, str) and message_id:
        frame["message_id"] = message_id
    await websocket.send_json(frame)


def _fact_json(fact: Fact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "key": fact.key,
        "value": fact.value,
        "category": fact.category,
        "status": fact.status,
        "source": fact.source,
        "evidence": fact.evidence,
    }


app = create_app()


def main() -> None:
    import uvicorn

    settings = load_config()
    server = settings.get("server") or {}
    host = str(server.get("host", "127.0.0.1"))
    port = int(server.get("port", 8787))
    uvicorn.run("src.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
