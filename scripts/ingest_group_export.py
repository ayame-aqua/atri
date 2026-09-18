"""P2-B：从群导出文本生成待确认候选。不连 QQ。"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from src.config import REPO_ROOT, load_config  # noqa: E402
from src.core.llm import LLMClient, LLMError  # noqa: E402
from src.memory.ingest import (  # noqa: E402
    clean_export,
    drop_private_rows,
    ingest_candidates,
    load_candidates_json,
)
from src.memory.store import MemoryStore  # noqa: E402

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM = (
    "你从脱敏后的群聊记录抽取记忆候选。只输出 JSON，不要 markdown。"
    '格式：{"facts":[{"layer":"profile","key":"prefers.x","value":"...","evidence":"..."}],'
    '"style_terms":[{"layer":"style","term":"...","meaning":"...","usage":"...","evidence":"..."}],'
    '"episodes":[{"layer":"episode","summary":"..."}]}'
    "规则：不要手机号、住址、证件；不确定就少写；全部是待确认候选。"
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Ingest group export text into pending candidates")
    parser.add_argument("path", type=Path, help="Exported group chat text file")
    parser.add_argument(
        "--candidates-json",
        type=Path,
        help="Skip LLM; load already extracted JSON (for tests / 脱敏样例)",
    )
    parser.add_argument("--sqlite", type=Path, default=None, help="Override sqlite path")
    parser.add_argument("--vector", type=Path, default=None, help="Override LanceDB path")
    args = parser.parse_args()
    if not args.path.is_file():
        raise SystemExit(f"file not found: {args.path}")

    raw = args.path.read_text(encoding="utf-8")
    cleaned = clean_export(raw)
    if args.candidates_json:
        rows = load_candidates_json(args.candidates_json)
    else:
        rows = asyncio.run(_extract_with_llm("\n".join(cleaned)))
    rows = drop_private_rows(rows)

    settings = load_config()
    memory_cfg = settings.get("memory") or {}
    sqlite_rel = str(memory_cfg.get("sqlite_path", "data/memory.sqlite"))
    vector_rel = str(memory_cfg.get("vector_path", "data/vectors"))
    sqlite_path = args.sqlite or (REPO_ROOT / sqlite_rel)
    vector_path = args.vector or (REPO_ROOT / vector_rel)
    store = MemoryStore(sqlite_path, seed=True, vector_path=vector_path)
    written = ingest_candidates(store, rows)
    logger.info("ingest done path=%s cleaned=%s written=%s", args.path, len(cleaned), written)
    print(json.dumps({"cleaned": len(cleaned), "written": written}, ensure_ascii=False))


async def _extract_with_llm(cleaned: str) -> list[dict]:
    if not cleaned.strip():
        return []
    load_config()
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-flash")
    if not api_key.strip():
        raise SystemExit("LLM_API_KEY empty; pass --candidates-json for offline ingest")
    try:
        llm = LLMClient(api_key=api_key, base_url=base_url, model=model)
        raw = await llm.chat(
            [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": cleaned},
            ]
        )
    except LLMError:
        logger.exception("ingest llm extract failed")
        raise SystemExit("llm extract failed") from None
    try:
        data = json.loads(_strip_fence(raw))
    except json.JSONDecodeError:
        logger.exception("ingest llm json invalid")
        raise SystemExit("llm extract was not json") from None
    return _rows_from_payload(data)


def _rows_from_payload(data: object) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    rows: list[dict] = []
    mapping = {
        "facts": "profile",
        "style_terms": "style",
        "episodes": "episode",
        "candidates": None,
    }
    for key, layer in mapping.items():
        chunk = data.get(key)
        if not isinstance(chunk, list):
            continue
        for item in chunk:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            if layer and "layer" not in row:
                row["layer"] = layer
            rows.append(row)
    return rows


def _strip_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


if __name__ == "__main__":
    main()
