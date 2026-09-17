"""稳定错误码；前端按 code 分支。"""

from __future__ import annotations

BAD_REQUEST = "BAD_REQUEST"
DUPLICATE = "DUPLICATE"
LLM_FAILED = "LLM_FAILED"
INTERNAL = "INTERNAL"

HUMAN_MESSAGES: dict[str, str] = {
    BAD_REQUEST: "消息不完整",
    DUPLICATE: "这条已经处理过了",
    LLM_FAILED: "她这会儿没接上",
    INTERNAL: "内部出错了",
}


def human_message(code: str) -> str:
    return HUMAN_MESSAGES.get(code, "出错了")
