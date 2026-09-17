"""Gateway.handle 去重与缓存回放。"""

from __future__ import annotations

import asyncio

from src.core.errors import DUPLICATE, LLM_FAILED
from src.core.llm import LLMError
from src.core.types import InboundMessage, OutboundMessage
from src.gateway import Gateway
from tests.test_gateway_dedup import _inbound


class _FakeAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, inbound: InboundMessage) -> OutboundMessage:
        self.calls += 1
        return OutboundMessage(
            message_id=f"r{self.calls}",
            reply_to_id=inbound.message_id,
            chat_id=inbound.chat_id,
            texts=["嗯。"],
            speech_ja="うん。",
        )


def test_handle_success_then_replay() -> None:
    agent = _FakeAgent()
    gateway = Gateway(dedup_ttl_s=600, agent=agent)  # type: ignore[arg-type]
    inbound = _inbound("same")
    first = asyncio.run(gateway.handle(inbound))
    assert first.outbound is not None
    assert agent.calls == 1
    second = asyncio.run(gateway.handle(inbound))
    assert second.replay is True
    assert second.outbound is first.outbound
    assert agent.calls == 1


def test_handle_in_flight_is_duplicate() -> None:
    gateway = Gateway(dedup_ttl_s=600, agent=_FakeAgent())  # type: ignore[arg-type]
    inbound = _inbound("inflight")
    assert gateway.begin(inbound) is None
    result = asyncio.run(gateway.handle(inbound))
    assert result.error_code == DUPLICATE


class _BoomAgent:
    async def run(self, inbound: InboundMessage) -> OutboundMessage:
        del inbound
        raise LLMError("nope")


def test_llm_error_allows_retry() -> None:
    gateway = Gateway(dedup_ttl_s=600, agent=_BoomAgent())  # type: ignore[arg-type]
    inbound = _inbound("retry")
    failed = asyncio.run(gateway.handle(inbound))
    assert failed.error_code == LLM_FAILED
    gateway.agent = _FakeAgent()  # type: ignore[assignment]
    ok = asyncio.run(gateway.handle(inbound))
    assert ok.outbound is not None
