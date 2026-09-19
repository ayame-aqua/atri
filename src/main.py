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

from src.channels.web import assistant_audio_frame, assistant_text_frame, parse_user_text_frame
from src.config import REPO_ROOT, load_config
from src.core.agent import Agent
from src.core.errors import BAD_REQUEST, human_message
from src.core.living_notes import LivingNotesStore
from src.core.llm import LLMClient, LLMError
from src.core.persona import split_persona
from src.core.session import SessionStore
from src.core.types import OutboundMessage
from src.gateway import Gateway
from src.memory.constants import (
    DEFAULT_CHAT_ID,
    DEFAULT_CYCLE_ENABLED,
    DEFAULT_DIARY_KEEP,
    DEFAULT_EPISODE_MIN_SCORE,
    DEFAULT_EXTRACT_EVERY_N,
    DEFAULT_MOOD_DECAY_PER_HOUR,
    DEFAULT_RETRIEVE_K,
    DEFAULT_STYLE_MAX,
    STATUS_ACTIVE,
    STATUS_CONFIRMED,
    STATUS_PENDING,
    VECTOR_BACKEND_LANCEDB,
)
from src.memory.store import Diary, Episode, Fact, Impression, MemoryStore, StyleTerm
from src.memory.summarize import summarize_turns
from src.speech.constants import (
    DEFAULT_CACHE_DIR,
    DEFAULT_GPT_WEIGHTS,
    DEFAULT_REF_DIR,
    DEFAULT_SOVITS_WEIGHTS,
    DEFAULT_TTS_API_BASE,
    DEFAULT_TTS_TIMEOUT_S,
    TTS_TEXT_LANG,
)
from src.speech.tts import SoVitsTts, TtsError

logger = logging.getLogger(__name__)
WEB_DIR = REPO_ROOT / "web"


def _attach_runtime(
    app: FastAPI,
    settings: dict[str, Any],
    *,
    persona_path: str,
    max_turns: int,
    dedup_ttl_s: float,
) -> None:
    try:
        llm = _build_llm(settings)
    except LLMError:
        logger.exception("llm client init failed")
        llm = None
    sessions = SessionStore(max_turns=max_turns * 2)
    memory_cfg = settings.get("memory") or {}
    sqlite_rel = str(memory_cfg.get("sqlite_path", "data/memory.sqlite"))
    sqlite_path = Path(sqlite_rel) if os.path.isabs(sqlite_rel) else REPO_ROOT / sqlite_rel
    vector_rel = str(memory_cfg.get("vector_path", "data/vectors"))
    vector_path = Path(vector_rel) if os.path.isabs(vector_rel) else REPO_ROOT / vector_rel
    backend = str(memory_cfg.get("vector_backend", VECTOR_BACKEND_LANCEDB))
    if backend != VECTOR_BACKEND_LANCEDB:
        logger.warning("memory vector_backend=%s unsupported, using lancedb", backend)
    retrieve_k = int(memory_cfg.get("retrieve_k", DEFAULT_RETRIEVE_K))
    style_max = int(memory_cfg.get("style_max", DEFAULT_STYLE_MAX))
    min_score = float(memory_cfg.get("episode_min_score", DEFAULT_EPISODE_MIN_SCORE))
    extract_every_n = int(memory_cfg.get("extract_every_n", DEFAULT_EXTRACT_EVERY_N))
    diary_keep = int(memory_cfg.get("diary_keep", DEFAULT_DIARY_KEEP))
    mood_cfg = memory_cfg.get("mood") or {}
    memory = MemoryStore(
        sqlite_path,
        seed=True,
        vector_path=vector_path,
        retrieve_k=retrieve_k,
        style_max=style_max,
        min_score=min_score,
        mood_enabled=bool(mood_cfg.get("enabled", True)),
        mood_decay_per_hour=float(mood_cfg.get("decay_per_hour", DEFAULT_MOOD_DECAY_PER_HOUR)),
        cycle_enabled=bool(mood_cfg.get("cycle_enabled", DEFAULT_CYCLE_ENABLED)),
        diary_keep=diary_keep,
    )
    living_notes = LivingNotesStore(REPO_ROOT / "data" / "living_notes.json")
    agent = (
        Agent(
            persona_path=persona_path,
            llm=llm,
            sessions=sessions,
            memory=memory,
            living_notes=living_notes,
            extract_every_n=extract_every_n,
        )
        if llm is not None
        else None
    )
    app.state.gateway = Gateway(dedup_ttl_s=dedup_ttl_s, agent=agent)
    app.state.memory = memory
    app.state.sessions = sessions
    app.state.llm = llm
    app.state.persona_path = persona_path
    app.state.llm_ready = llm is not None
    speech_cfg = settings.get("speech") or {}
    api_base = str(speech_cfg.get("tts_api_base", DEFAULT_TTS_API_BASE))
    ref_rel = str(speech_cfg.get("tts_ref_dir", DEFAULT_REF_DIR))
    cache_rel = str(speech_cfg.get("tts_cache_dir", DEFAULT_CACHE_DIR))
    ref_dir = Path(ref_rel) if os.path.isabs(ref_rel) else REPO_ROOT / ref_rel
    cache_dir = Path(cache_rel) if os.path.isabs(cache_rel) else REPO_ROOT / cache_rel
    timeout_s = float(speech_cfg.get("tts_timeout_s", DEFAULT_TTS_TIMEOUT_S))
    text_lang = str(speech_cfg.get("tts_text_lang", TTS_TEXT_LANG))
    gpt_rel = str(speech_cfg.get("tts_gpt_weights", DEFAULT_GPT_WEIGHTS))
    sovits_rel = str(speech_cfg.get("tts_sovits_weights", DEFAULT_SOVITS_WEIGHTS))
    gpt_weights = Path(gpt_rel) if os.path.isabs(gpt_rel) else REPO_ROOT / gpt_rel
    sovits_weights = Path(sovits_rel) if os.path.isabs(sovits_rel) else REPO_ROOT / sovits_rel
    app.state.tts = SoVitsTts(
        api_base=api_base,
        ref_dir=ref_dir,
        cache_dir=cache_dir,
        timeout_s=timeout_s,
        text_lang=text_lang,
        gpt_weights=gpt_weights,
        sovits_weights=sovits_weights,
    )


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
        logger.info(
            "natsume web listening host=%s port=%s llm_ready=%s",
            server_cfg.get("host", "127.0.0.1"),
            server_cfg.get("port", 8787),
            app.state.llm_ready,
        )
        yield

    app = FastAPI(title="shiki-natsume", lifespan=lifespan)
    _attach_runtime(
        app,
        settings,
        persona_path=persona_path,
        max_turns=max_turns,
        dedup_ttl_s=dedup_ttl_s,
    )

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

    @app.get("/api/memory/episodes")
    async def list_memory_episodes(status: str = "") -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        filter_status = None if status in {"", "all"} else status
        return {
            "episodes": [_episode_json(item) for item in memory.list_episodes(status=filter_status)]
        }

    @app.post("/api/memory/episodes/{episode_id}/confirm")
    async def confirm_memory_episode(episode_id: int) -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        episode = memory.update_episode(episode_id, status=STATUS_ACTIVE)
        if episode is None:
            raise HTTPException(status_code=404, detail="episode not found")
        return _episode_json(episode)

    @app.get("/api/memory/style")
    async def list_memory_style(status: str = "") -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        filter_status = None if status in {"", "all"} else status
        return {"style": [_style_json(item) for item in memory.list_style(status=filter_status)]}

    @app.post("/api/memory/style/{style_id}/confirm")
    async def confirm_memory_style(style_id: int) -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        term = memory.confirm_style(style_id)
        if term is None:
            raise HTTPException(status_code=404, detail="style not found")
        if term.status != STATUS_CONFIRMED:
            raise HTTPException(status_code=409, detail="style not confirmed")
        return _style_json(term)

    @app.post("/api/memory/summarize-session")
    async def summarize_memory_session(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = payload or {}
        chat_id = body.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id.strip():
            chat_id = DEFAULT_CHAT_ID
        sessions: SessionStore = app.state.sessions
        turns = sessions.history(chat_id.strip())
        if not turns:
            raise HTTPException(status_code=400, detail="session empty")
        llm = app.state.llm
        if llm is None:
            raise HTTPException(status_code=503, detail="llm not ready")
        try:
            summary = await summarize_turns(llm, turns)
        except (ValueError, TypeError, LLMError):
            logger.exception("summarize failed chat_id=%s", chat_id)
            raise HTTPException(status_code=502, detail="summarize failed") from None
        memory: MemoryStore = app.state.memory
        episode = memory.add_episode(summary, source_chat_id=chat_id, status=STATUS_PENDING)
        diary = memory.upsert_diary(summary)
        return {"episode": _episode_json(episode), "diary": _diary_json(diary)}

    @app.get("/api/memory/mood")
    async def get_memory_mood() -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        mood = memory.get_mood()
        return {
            "energy": mood.energy,
            "irritation": mood.irritation,
            "affection": mood.affection,
            "cycle_enabled": memory.cycle_enabled,
        }

    @app.post("/api/memory/impressions/{impression_id}/confirm")
    async def confirm_memory_impression(impression_id: int) -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        row = memory.update_impression(impression_id, status=STATUS_ACTIVE)
        if row is None:
            raise HTTPException(status_code=404, detail="impression not found")
        return _impression_json(row)

    @app.post("/api/memory/export")
    async def export_memory() -> dict[str, Any]:
        memory: MemoryStore = app.state.memory
        dest = REPO_ROOT / "data" / "memory" / "export.md"
        path = memory.export_markdown(dest)
        return {"path": str(path)}

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/media/tts/{audio_id}")
    async def tts_media(audio_id: str) -> FileResponse:
        tts: SoVitsTts | None = getattr(app.state, "tts", None)
        if tts is None:
            raise HTTPException(status_code=404, detail="tts not ready")
        path = tts.clip_path(audio_id)
        if path is None:
            raise HTTPException(status_code=404, detail="clip not found")
        return FileResponse(path, media_type="audio/wav")

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
    await _send_assistant_audio(websocket, result.outbound)


async def _send_assistant_audio(websocket: WebSocket, outbound: OutboundMessage) -> None:
    speech_ja = outbound.speech_ja
    if not speech_ja:
        return
    tts = getattr(websocket.app.state, "tts", None)
    if not isinstance(tts, SoVitsTts):
        return
    try:
        clip = await tts.synthesize_to_cache(speech_ja, outbound.emotion)
    except TtsError:
        logger.exception("tts failed message_id=%s", outbound.message_id)
        await websocket.send_json(
            {
                "type": "status",
                "message_id": outbound.message_id,
                "state": "tts_failed",
            }
        )
        return
    outbound.audio_url = f"/media/tts/{clip.audio_id}"
    await websocket.send_json(
        assistant_audio_frame(
            outbound,
            url=outbound.audio_url,
            duration_ms=clip.duration_ms,
        )
    )


async def _send_error(websocket: WebSocket, message_id: object, code: str) -> None:
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


def _episode_json(episode: Episode) -> dict[str, Any]:
    return {
        "id": episode.id,
        "summary": episode.summary,
        "happened_at": episode.happened_at,
        "source_chat_id": episode.source_chat_id,
        "status": episode.status,
        "embedding_id": episode.embedding_id,
    }


def _style_json(term: StyleTerm) -> dict[str, Any]:
    return {
        "id": term.id,
        "term": term.term,
        "meaning": term.meaning,
        "usage": term.usage,
        "status": term.status,
        "evidence": term.evidence,
        "count": term.count,
    }


def _diary_json(row: Diary) -> dict[str, Any]:
    return {"id": row.id, "day": row.day, "summary": row.summary}


def _impression_json(row: Impression) -> dict[str, Any]:
    return {
        "id": row.id,
        "text": row.text,
        "status": row.status,
        "source": row.source,
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
