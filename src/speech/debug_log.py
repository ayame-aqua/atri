"""本机语音调试日志。落在 data/，不进 git。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from src.config import REPO_ROOT

logger = logging.getLogger(__name__)

DEBUG_LOG_PATH = REPO_ROOT / "data" / "speech_debug.log"
_MAX_FIELD = 200


def speech_debug(event: str, **fields: object) -> None:
    stamp = datetime.now(UTC).astimezone().isoformat(timespec="milliseconds")
    parts = [f"event={event}"]
    for key, value in fields.items():
        text = str(value).replace("\n", " ").strip()
        if len(text) > _MAX_FIELD:
            text = text[:_MAX_FIELD]
        parts.append(f"{key}={text}")
    line = f"{stamp} {' '.join(parts)}"
    if event != "vad":
        logger.info("speech %s", " ".join(parts))
    path = DEBUG_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
