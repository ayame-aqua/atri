"""OpenAI 兼容 LLM provider。默认云端；思考模式默认关，陪聊不需要长推理。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CHAT_PATH = "/chat/completions"
_V1_CHAT_PATH = "/v1/chat/completions"


class LLMError(Exception):
    """上游调用失败。"""


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_s: float = 60.0,
        disable_thinking: bool = True,
    ) -> None:
        if not api_key.strip():
            msg = "LLM_API_KEY is empty"
            raise LLMError(msg)
        self._api_key = api_key.strip()
        self._model = model
        self._timeout_s = timeout_s
        self._disable_thinking = disable_thinking
        self._url = _completions_url(base_url)

    async def chat(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if self._disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.exception("llm http failed")
            raise LLMError("llm request failed") from exc

        if response.status_code >= 400:
            logger.error("llm status=%s", response.status_code)
            raise LLMError(f"llm status {response.status_code}")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.exception("llm response shape invalid")
            raise LLMError("llm empty or invalid response") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMError("llm empty content")
        return content

    async def chat_stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """P1 整段返回；P5 再换成真正的 token 流。"""
        yield await self.chat(messages)


def _completions_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return root + _CHAT_PATH
    return root + _V1_CHAT_PATH
