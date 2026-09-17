"""Channel Gateway：去重后交给 Agent（P1 起）。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.core.types import InboundMessage, OutboundMessage


@dataclass
class DedupEntry:
    created_at: float
    outbound: OutboundMessage | None = None
    in_flight: bool = False
    failed: bool = False


@dataclass
class Gateway:
    """按 (chat_id, message_id) 去重；完整 Agent 接线在 P1 后续完成。"""

    dedup_ttl_s: float = 600.0
    _entries: dict[tuple[str, str], DedupEntry] = field(default_factory=dict)

    def _purge(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if now - entry.created_at > self.dedup_ttl_s and not entry.in_flight
        ]
        for key in expired:
            del self._entries[key]

    def begin(self, inbound: InboundMessage) -> str | None:
        """返回 None 表示可以处理；否则返回稳定错误码。"""
        now = time.monotonic()
        self._purge(now)
        key = (inbound.chat_id, inbound.message_id)
        existing = self._entries.get(key)
        if existing is None:
            self._entries[key] = DedupEntry(created_at=now, in_flight=True)
            return None
        if existing.in_flight:
            return "DUPLICATE"
        if existing.failed:
            existing.in_flight = True
            existing.failed = False
            return None
        return "DUPLICATE"

    def complete(self, inbound: InboundMessage, outbound: OutboundMessage) -> None:
        key = (inbound.chat_id, inbound.message_id)
        entry = self._entries.get(key)
        if entry is None:
            self._entries[key] = DedupEntry(
                created_at=time.monotonic(),
                outbound=outbound,
                in_flight=False,
            )
            return
        entry.outbound = outbound
        entry.in_flight = False
        entry.failed = False

    def fail(self, inbound: InboundMessage) -> None:
        key = (inbound.chat_id, inbound.message_id)
        entry = self._entries.get(key)
        if entry is None:
            return
        entry.in_flight = False
        entry.failed = True

    def cached_outbound(self, inbound: InboundMessage) -> OutboundMessage | None:
        entry = self._entries.get((inbound.chat_id, inbound.message_id))
        if entry is None:
            return None
        return entry.outbound
