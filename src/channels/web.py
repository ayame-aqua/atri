"""网页 WebSocket 通道（P1）。"""

from __future__ import annotations

from src.core.types import OutboundMessage


class WebChannel:
    name = "web"

    async def start(self, gateway: object) -> None:
        del gateway
        raise NotImplementedError("P1: bind FastAPI WebSocket /ws/chat")

    async def send(self, message: OutboundMessage) -> None:
        del message
        raise NotImplementedError("P1: push assistant_text frames")
