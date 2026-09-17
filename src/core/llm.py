"""OpenAI 兼容 LLM provider（P1 接 API；本机 Ollama 仅作可选后备）。"""

from __future__ import annotations


class LLMError(Exception):
    """上游调用失败。"""


class LLMClient:
    """占位：P1 实现 chat() 调 LLM_BASE_URL。"""

    async def chat(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError("P1: wire OpenAI-compatible HTTP client")
