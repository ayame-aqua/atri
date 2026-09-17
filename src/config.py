"""加载 config.yaml 与环境变量。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    load_dotenv(REPO_ROOT / ".env")
    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        msg = f"config must be a mapping: {config_path}"
        raise TypeError(msg)
    return data
