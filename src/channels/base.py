"""Channel 抽象。"""

from __future__ import annotations

from typing import Protocol

from src.core.types import OutboundMessage


class Channel(Protocol):
    name: str

    async def start(self, gateway: object) -> None: ...

    async def send(self, message: OutboundMessage) -> None: ...
