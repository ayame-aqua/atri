"""拼 prompt、调 LLM、解析尾块（P1 实现主体）。"""

from __future__ import annotations

from src.core.types import InboundMessage, OutboundMessage


class Agent:
    async def run(self, inbound: InboundMessage) -> OutboundMessage:
        raise NotImplementedError("P1: persona + session + llm + protocol")
