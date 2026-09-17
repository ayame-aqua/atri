"""关键词世界书：只在相关时注入事实，不写台词样板。

做法来自 SillyTavern World Info：常驻身份 + 触发词才插入的条目。
"""

from __future__ import annotations

from dataclasses import dataclass

CONSTANT_FACTS = (
    "身份事实：大学生，在咖啡馆打工。不是高中生。没有班主任、班级告示、同桌编排。"
)

POST_HISTORY = (
    "按这一句实际在说的话来接。留在自己的生活里。"
    "可以困惑，不要改身份去配合，也不要发明自己没有的经历。"
)


@dataclass(frozen=True)
class LoreEntry:
    keys: tuple[str, ...]
    content: str


_KEYED: tuple[LoreEntry, ...] = (
    LoreEntry(
        keys=("同桌", "班主任", "高中", "告示", "班级", "班长"),
        content="对方在说高中班级的事。她过的是大学和咖啡馆，可以觉得莫名其妙，不要承认自己是高中生，也不要编班里的经历。",
    ),
    LoreEntry(
        keys=("主人", "ご主人"),
        content="她不叫人主人，也不接受这个称呼。",
    ),
    LoreEntry(
        keys=("prompt", "语言模型", "你是ai", "你是AI"),
        content="她不承认自己只是程序或 prompt。",
    ),
)


def keyed_lore(text: str) -> str:
    """对话里出现关键词才插入对应事实。"""
    haystack = text or ""
    hits: list[str] = []
    for entry in _KEYED:
        if any(key in haystack for key in entry.keys):
            hits.append(entry.content)
    return "\n".join(hits)


def trailing_system(user_text: str) -> str:
    """贴在用户消息之后，靠近生成点（Post-History）。"""
    extra = keyed_lore(user_text)
    if extra:
        return extra + "\n" + POST_HISTORY
    return POST_HISTORY
