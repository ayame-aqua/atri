"""解析 LLM 输出中的 [[natsume]] 尾块；失败必须降级。

标记之前的可见正文是日语台词。中文气泡由翻译步骤生成，不在本模块。
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.types import EMOTIONS, NATSUME_MARKER, Emotion, ParsedNatsumeBlock

_LEGACY_EMOTION = re.compile(r"\[\[emotion:(\w+)\]\]", re.IGNORECASE)


def parse(raw: str) -> ParsedNatsumeBlock:
    text = raw or ""
    marker_idx = text.find(NATSUME_MARKER)
    if marker_idx < 0:
        return _parse_without_marker(text)

    visible = text[:marker_idx].rstrip()
    payload = text[marker_idx + len(NATSUME_MARKER) :].strip()
    if payload.startswith("```"):
        payload = _strip_fence(payload)

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ParsedNatsumeBlock(
            visible_text=visible,
            emotion="neutral",
            silent=False,
            memory_candidates=[],
            parse_ok=False,
            log_level="error",
        )

    if not isinstance(data, dict):
        return ParsedNatsumeBlock(
            visible_text=visible,
            emotion="neutral",
            silent=False,
            memory_candidates=[],
            parse_ok=False,
            log_level="error",
        )

    emotion, emotion_warn = _emotion_from(data.get("emotion"))
    silent = bool(data["silent"]) if "silent" in data else False
    candidates = data.get("memory_candidates", [])
    if not isinstance(candidates, list):
        candidates = []
        emotion_warn = True

    return ParsedNatsumeBlock(
        visible_text=visible,
        emotion=emotion,
        silent=silent,
        memory_candidates=candidates,
        parse_ok=True,
        log_level="warning" if emotion_warn or _missing_fields(data) else "debug",
    )


def _parse_without_marker(text: str) -> ParsedNatsumeBlock:
    match = _LEGACY_EMOTION.search(text)
    emotion: Emotion = "neutral"
    visible = text
    if match:
        candidate = match.group(1).lower()
        if candidate in EMOTIONS:
            emotion = candidate  # type: ignore[assignment]
        visible = (text[: match.start()] + text[match.end() :]).strip()
    return ParsedNatsumeBlock(
        visible_text=visible.strip(),
        emotion=emotion,
        silent=False,
        memory_candidates=[],
        parse_ok=False,
        log_level="warning",
    )


def _strip_fence(payload: str) -> str:
    lines = payload.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _emotion_from(value: Any) -> tuple[Emotion, bool]:
    if value is None:
        return "neutral", True
    if isinstance(value, str) and value in EMOTIONS:
        return value, False  # type: ignore[return-value]
    return "neutral", True


def _missing_fields(data: dict[str, Any]) -> bool:
    return any(key not in data for key in ("emotion", "silent", "memory_candidates"))
