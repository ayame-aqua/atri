"""人设加载（P1）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_FRONT_MATTER = "---"


def load_persona(path: str | Path) -> str:
    """返回人设正文（去掉 YAML 头），拼进 system。"""
    _, body = split_persona(path)
    return body


def split_persona(path: str | Path) -> tuple[dict[str, Any], str]:
    persona_path = Path(path)
    raw = persona_path.read_text(encoding="utf-8")
    if not raw.startswith(_FRONT_MATTER):
        return {}, raw.strip()
    rest = raw[len(_FRONT_MATTER) :]
    end = rest.find(f"\n{_FRONT_MATTER}")
    if end < 0:
        return {}, raw.strip()
    meta_raw = rest[:end]
    body = rest[end + len(_FRONT_MATTER) + 1 :].strip()
    meta = yaml.safe_load(meta_raw) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body
