"""语音输入通道（P3；与 Web 共用 Agent / 记忆）。"""

from __future__ import annotations

from src.core.types import OutboundMessage


class VoiceChannel:
    name = "voice"

    async def start(self, gateway: object) -> None:
        del gateway
        # P3-B 再挂麦克风上行；P3-A 只出声

    async def send(self, message: OutboundMessage) -> None:
        del message
