"""个人微信通道空壳（P7；默认实验性、可卸载）。"""

from __future__ import annotations

from src.core.types import OutboundMessage


class WechatChannel:
    name = "wechat"

    async def start(self, gateway: object) -> None:
        del gateway

    async def send(self, message: OutboundMessage) -> None:
        del message
        raise NotImplementedError("P7: experimental wechat adapter")
