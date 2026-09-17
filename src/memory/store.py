"""长期记忆存储。P1 为空实现；P2-A 接 SQLite。"""

from __future__ import annotations

from typing import Any


class MemoryStore:
    def profile_block(self) -> str:
        return ""

    def retrieve(self, query: str, k: int = 5) -> list[Any]:
        del query, k
        return []

    def add_fact(self, key: str, value: str, category: str = "profile") -> None:
        del key, value, category
        raise NotImplementedError("P2-A: persist facts to SQLite")
