"""每 N 轮抽持久记忆。失败只打日志，不挡这一轮对话。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.core.session import Turn
from src.memory.constants import SOURCE_EXTRACT, STATUS_PENDING
from src.memory.store import MemoryStore
from src.memory.summarize import format_transcript

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM = (
    "你是记忆编辑，不是角色。根据对话抽出应长期记住的事实。"
    "只输出一个 JSON 对象，不要解释，不要代码围栏。"
    '{"facts":[{"key":"prefers.xxx","value":"中文"}],'
    '"impression":"她对对方的稳定看法或null","diary":"今天一两句或null"}'
    "没有就 facts=[]，impression 和 diary 用 null。不要编造。"
)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


async def extract_pending(
    llm: object,
    store: MemoryStore,
    turns: list[Turn],
    *,
    chat_id: str,
) -> None:
    transcript = format_transcript(turns)
    if not transcript:
        return
    chat = getattr(llm, "chat", None)
    if chat is None:
        logger.warning("memory extract skipped: llm has no chat")
        return
    try:
        raw = await chat(
            [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": transcript},
            ]
        )
    except Exception:
        logger.exception("memory extract llm failed chat_id=%s", chat_id)
        return
    payload = _parse_extract(raw if isinstance(raw, str) else "")
    if payload is None:
        logger.warning("memory extract parse failed chat_id=%s", chat_id)
        return
    facts = payload.get("facts")
    if isinstance(facts, list):
        for item in facts:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            value = item.get("value")
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            store.add(
                value,
                layer="profile",
                key=key,
                status=STATUS_PENDING,
                source=SOURCE_EXTRACT,
            )
    impression = payload.get("impression")
    if isinstance(impression, str) and impression.strip():
        store.set_impression(impression.strip(), status=STATUS_PENDING, source=SOURCE_EXTRACT)
    diary = payload.get("diary")
    if isinstance(diary, str) and diary.strip():
        store.upsert_diary(diary.strip())
    logger.info("memory extract done chat_id=%s", chat_id)


def _parse_extract(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    match = _JSON_OBJECT.search(text)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
