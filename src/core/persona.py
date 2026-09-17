"""人设加载（P1）。"""

from __future__ import annotations

from pathlib import Path


def load_persona(path: str | Path) -> str:
    persona_path = Path(path)
    return persona_path.read_text(encoding="utf-8")
