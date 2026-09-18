"""群导出清洗与待确认入库。不连 QQ。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.memory.constants import LONG_DIGIT_LEN
from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)

SYSTEM_MARKERS = (
    "系统消息",
    "加入了群",
    "退出了群",
    "离开了群",
    "邀请",
    "拍了拍",
    "撤回了一条消息",
)
AD_MARKERS = ("加微信", "领优惠", "点击链接", "免费领取")
LONG_DIGITS = re.compile(rf"\d{{{LONG_DIGIT_LEN},}}")


def clean_export(raw: str) -> list[str]:
    """去掉系统提示、入群、广告，以及含过长数字串的行。"""
    kept: list[str] = []
    for line in (raw or "").splitlines():
        text = line.strip()
        if not text:
            continue
        if _is_system(text) or _is_ad(text):
            continue
        if LONG_DIGITS.search(text):
            continue
        kept.append(text)
    return kept


def load_candidates_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        rows: list[Any] = []
        for key in ("facts", "style_terms", "episodes", "candidates"):
            chunk = data.get(key)
            if isinstance(chunk, list):
                rows.extend(chunk)
        if rows:
            return [_normalize_row(item) for item in rows if isinstance(item, dict)]
        msg = f"candidates json has no lists: {path}"
        raise ValueError(msg)
    if not isinstance(data, list):
        msg = f"candidates json must be list or object: {path}"
        raise ValueError(msg)
    return [_normalize_row(item) for item in data if isinstance(item, dict)]


def drop_private_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for row in rows:
        blob = " ".join(_string_fields(row))
        if LONG_DIGITS.search(blob):
            logger.info("ingest drop private row")
            continue
        kept.append(row)
    return kept


def ingest_candidates(store: MemoryStore, rows: list[dict[str, Any]]) -> int:
    safe = drop_private_rows(rows)
    return store.ingest_import_rows(safe)


def _normalize_row(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    kind = row.get("type")
    if isinstance(kind, str) and "layer" not in row:
        if kind in {"fact", "facts", "profile"}:
            row["layer"] = "profile"
        elif kind in {"style", "style_term"}:
            row["layer"] = "style"
        elif kind in {"episode", "episodes"}:
            row["layer"] = "episode"
    return row


def _string_fields(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in row.values():
        if isinstance(item, str):
            values.append(item)
    return values


def _is_system(text: str) -> bool:
    return any(marker in text for marker in SYSTEM_MARKERS)


def _is_ad(text: str) -> bool:
    return any(marker in text for marker in AD_MARKERS)
