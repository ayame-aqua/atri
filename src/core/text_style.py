"""中文台词的标点收口。模型爱堆句号，展示前压成口语停顿。"""

from __future__ import annotations


def soften_chinese_punctuation(text: str) -> str:
    """句中的「。」改成逗号，去掉句末句号。问号、省略号不动。"""
    cleaned = text.strip()
    if not cleaned:
        return ""
    if cleaned.endswith("。"):
        cleaned = cleaned[:-1]
    return cleaned.replace("。", "，")
