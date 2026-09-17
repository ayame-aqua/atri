"""用户纠正后记下的相处约束。不是微调，也不让模型自己改人设文件。

每轮拿自己的回复当训练数据会把 OOC 学进去。只在对方明确纠偏时写一条，
下次注入 system。落在 data/，不进 git，也不走 SQLite。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.core.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

MAX_LIVING_NOTES = 12
MAX_RULE_CHARS = 80
CORRECTION_MARKERS: tuple[str, ...] = (
    "ooc",
    "出戏",
    "人设",
    "不像你",
    "不像她",
    "不要这样说",
    "别这样说",
    "太客服",
    "太抬杠",
    "在编",
    "瞎编",
)

_EXTRACT_SYSTEM = (
    "你是人设编辑，不是角色。根据用户对上一句的纠正，写一条以后生成要用的约束。"
    "只输出 JSON。"
    "要求：一句中文；写处事，不写可背诵台词；不改身份（大学生、咖啡馆打工、不是高中生）。"
    "纠正含糊或不是人设问题则 {\"rule\": null}。"
)


def looks_like_correction(text: str) -> bool:
    haystack = (text or "").casefold()
    return any(marker.casefold() in haystack for marker in CORRECTION_MARKERS)


def parse_extracted_rule(raw: str) -> str | None:
    payload = _json_object(raw)
    if payload is None:
        return None
    rule = payload.get("rule")
    if not isinstance(rule, str):
        return None
    cleaned = " ".join(rule.split()).strip()
    if not cleaned:
        return None
    return cleaned[:MAX_RULE_CHARS]


def _json_object(raw: str) -> dict[str, object] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


class LivingNotesStore:
    def __init__(self, path: Path, *, max_notes: int = MAX_LIVING_NOTES) -> None:
        self._path = path
        self._max_notes = max_notes
        self._notes = self._load()

    def as_block(self) -> str:
        if not self._notes:
            return ""
        lines = "\n".join(f"- {note}" for note in self._notes)
        return "相处中记下的约束（用户纠正，不要读给对方听）：\n" + lines

    def add(self, rule: str) -> bool:
        cleaned = " ".join(rule.split()).strip()[:MAX_RULE_CHARS]
        if not cleaned:
            return False
        if any(
            cleaned == existing or cleaned in existing or existing in cleaned
            for existing in self._notes
        ):
            return False
        self._notes.append(cleaned)
        overflow = len(self._notes) - self._max_notes
        if overflow > 0:
            del self._notes[:overflow]
        self._save()
        return True

    def _load(self) -> list[str]:
        if not self._path.is_file():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("living notes load failed path=%s", self._path)
            return []
        if not isinstance(raw, list):
            return []
        notes: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                notes.append(item.strip()[:MAX_RULE_CHARS])
        return notes[-self._max_notes :]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._notes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


async def absorb_correction(
    llm: LLMClient,
    store: LivingNotesStore,
    *,
    user_text: str,
    last_reply: str,
) -> None:
    """从纠正里抽一条约束。抽取失败不影响这轮对话。"""
    user_payload = (
        f"上一句回复：{last_reply or '（没有）'}\n"
        f"用户纠正：{user_text}"
    )
    try:
        raw = await llm.chat(
            [
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": user_payload},
            ]
        )
    except LLMError:
        logger.exception("living note extract failed")
        return
    rule = parse_extracted_rule(raw)
    if not rule:
        logger.info("living note extract empty")
        return
    if store.add(rule):
        logger.info("living note added")
