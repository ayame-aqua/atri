"""QQ 通道空壳（P6 前禁止登录逻辑）。"""

from __future__ import annotations

from src.core.types import OutboundMessage


class QqChannel:
    name = "qq"

    async def start(self, gateway: object) -> None:
        del gateway

    async def send(self, message: OutboundMessage) -> None:
        del message
        raise NotImplementedError("P6: QQ send_text / send_sticker")
