"""日语台词 → 中文气泡。短请求，不走人设。"""

from __future__ import annotations

import logging

from src.core.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

_TRANSLATE_SYSTEM = (
    "你是翻译器。把用户给出的日语译成自然口语中文。只输出译文，不要引号，不要解释，不要补戏。"
)


async def japanese_to_chinese(llm: LLMClient, japanese: str) -> str:
    text = japanese.strip()
    if not text:
        return ""
    try:
        translated = await llm.chat(
            [
                {"role": "system", "content": _TRANSLATE_SYSTEM},
                {"role": "user", "content": text},
            ]
        )
    except LLMError:
        logger.warning("translate failed; fallback to japanese")
        return text
    cleaned = translated.strip().strip("「」『』\"'")
    return cleaned or text
