"""会话摘要：一两句，写入 pending episode。"""

from __future__ import annotations

from src.core.session import Turn
from src.memory.constants import SUMMARY_MAX_CHARS

SUMMARIZE_SYSTEM = "用一两句中文概括这次对话里发生的事。只输出摘要，不要解释，不要角色扮演。"


def format_transcript(turns: list[Turn]) -> str:
    lines: list[str] = []
    for turn in turns:
        role = "用户" if turn.role == "user" else "四季夏目"
        text = (turn.text or "").strip()
        if text:
            lines.append(f"{role}：{text}")
    return "\n".join(lines)


async def summarize_turns(llm: object, turns: list[Turn]) -> str:
    transcript = format_transcript(turns)
    if not transcript:
        msg = "session empty"
        raise ValueError(msg)
    chat = getattr(llm, "chat", None)
    if chat is None:
        msg = "llm has no chat"
        raise TypeError(msg)
    raw = await chat(
        [
            {"role": "system", "content": SUMMARIZE_SYSTEM},
            {"role": "user", "content": transcript},
        ]
    )
    if not isinstance(raw, str) or not raw.strip():
        msg = "empty summary"
        raise ValueError(msg)
    return raw.strip().splitlines()[0][:SUMMARY_MAX_CHARS]
