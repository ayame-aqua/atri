"""四季夏目应用入口：FastAPI + WebSocket 网页聊天。"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
from src.memory.store import MemoryStore

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
        memory = MemoryStore()
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
