"""Channel Gateway：去重后交给 Agent。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from src.core.agent import Agent
from src.core.errors import DUPLICATE, INTERNAL, LLM_FAILED
from src.core.llm import LLMError
from src.core.types import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


@dataclass
class DedupEntry:
    created_at: float
    outbound: OutboundMessage | None = None
    in_flight: bool = False
    failed: bool = False


@dataclass
class HandleResult:
    outbound: OutboundMessage | None = None
    error_code: str | None = None
    replay: bool = False


@dataclass
class Gateway:
    """按 (chat_id, message_id) 去重后再调 Agent。"""

    dedup_ttl_s: float = 600.0
    agent: Agent | None = None
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
            return DUPLICATE
        if existing.failed:
            existing.in_flight = True
            existing.failed = False
            return None
        return DUPLICATE

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

    async def handle(self, inbound: InboundMessage) -> HandleResult:
        status = self.begin(inbound)
        if status == DUPLICATE:
            cached = self.cached_outbound(inbound)
            if cached is not None:
                return HandleResult(outbound=cached, replay=True)
            return HandleResult(error_code=DUPLICATE)

        if self.agent is None:
            logger.error("gateway has no agent chat_id=%s", inbound.chat_id)
            self.fail(inbound)
            return HandleResult(error_code=LLM_FAILED)

        try:
            outbound = await self.agent.run(inbound)
        except LLMError:
            logger.exception("gateway llm failed message_id=%s", inbound.message_id)
            self.fail(inbound)
            return HandleResult(error_code=LLM_FAILED)
        except Exception:
            logger.exception("gateway internal failed message_id=%s", inbound.message_id)
            self.fail(inbound)
            return HandleResult(error_code=INTERNAL)

        self.complete(inbound, outbound)
        return HandleResult(outbound=outbound)
