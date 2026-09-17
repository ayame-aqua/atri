"""中文台词 → 日语（给 TTS）。短请求，不走人设。"""

from __future__ import annotations

import logging

from src.core.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

_TRANSLATE_SYSTEM = (
    "把中文台词译成日语口语。说话人是冷淡、别扭、话不多的年轻女生，用普通体。"
    "只输出日语译文，不要引号、不要解释、不要注音、不要中文。\n"
    "规则：\n"
    "- 译成嘴里会说出口的完整句子，不要电报体、不要体言止堆砌、不要把助词全删掉。\n"
    "- 保持原句的短和冷，不要扩写成敬语或热情安慰。\n"
    "- 原文没有「……」译文就不要加。问句用「？」。\n"
    "- 第一人称用「私」，对对方用「あんた」或省略，不要「ご主人様」。\n"
    "参考：\n"
    "哈？突然干嘛 → は？　急に何よ\n"
    "你说什么呢 → 何言ってるの\n"
    "没什么 → 別に\n"
    "那，饭吃了没 → で、ご飯は食べたの\n"
    "作业还没动 → 課題、まだ進んでない\n"
    "别拿我开玩笑……够了 → からかわないで……もういい\n"
    "水喝了没？早点睡 → 水、飲んだ？　寝な"
)


async def chinese_to_japanese(llm: LLMClient, chinese: str) -> str:
    text = chinese.strip()
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
        logger.warning("translate failed; leave speech_ja empty")
        return ""
    cleaned = translated.strip().strip("「」『』\"'")
    if _looks_like_chinese(cleaned):
        logger.warning("translate still contains chinese; drop speech_ja")
        return ""
    return cleaned


def _looks_like_chinese(text: str) -> bool:
    """汉字且几乎没有假名，当成中文漏出。日语汉字+假名放行。"""
    has_kana = any("\u3040" <= ch <= "\u30ff" for ch in text)
    if has_kana:
        return False
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)
