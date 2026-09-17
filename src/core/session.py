"""短期会话上下文（进程内）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Turn:
    role: str
    text: str
    emotion: str | None = None


@dataclass
class SessionStore:
    max_turns: int = 20
    _turns: dict[str, list[Turn]] = field(default_factory=dict)

    def history(self, chat_id: str) -> list[Turn]:
        return list(self._turns.get(chat_id, []))

    def append(self, chat_id: str, turn: Turn) -> None:
        bucket = self._turns.setdefault(chat_id, [])
        bucket.append(turn)
        overflow = len(bucket) - self.max_turns
        if overflow > 0:
            del bucket[:overflow]
