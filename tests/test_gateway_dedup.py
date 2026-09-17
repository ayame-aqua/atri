"""Gateway messageId 去重。"""

from __future__ import annotations

from src.core.types import InboundMessage, OutboundMessage
from src.gateway import Gateway


def _inbound(message_id: str = "m1") -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        channel="web",
        chat_type="dm",
        chat_id="web:local",
        sender_id="user",
        sender_name="你",
        text="你好",
        created_at=0.0,
    )


def test_first_message_accepted() -> None:
    gateway = Gateway(dedup_ttl_s=600)
    assert gateway.begin(_inbound()) is None


def test_in_flight_duplicate() -> None:
    gateway = Gateway(dedup_ttl_s=600)
    inbound = _inbound()
    assert gateway.begin(inbound) is None
    assert gateway.begin(inbound) == "DUPLICATE"


def test_success_cached_blocks_rerun() -> None:
    gateway = Gateway(dedup_ttl_s=600)
    inbound = _inbound()
    assert gateway.begin(inbound) is None
    outbound = OutboundMessage(
        message_id="r1",
        reply_to_id=inbound.message_id,
        chat_id=inbound.chat_id,
        texts=["嗯。"],
    )
    gateway.complete(inbound, outbound)
    assert gateway.begin(inbound) == "DUPLICATE"
    assert gateway.cached_outbound(inbound) is outbound


def test_failed_allows_retry() -> None:
    gateway = Gateway(dedup_ttl_s=600)
    inbound = _inbound()
    assert gateway.begin(inbound) is None
    gateway.fail(inbound)
    assert gateway.begin(inbound) is None
