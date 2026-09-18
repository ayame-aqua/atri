"""情节记忆检索（P2-B）。"""

from __future__ import annotations

from src.memory.constants import DEFAULT_RETRIEVE_K
from src.memory.store import Episode, MemoryStore


def retrieve_episodes(
    store: MemoryStore,
    query: str,
    k: int = DEFAULT_RETRIEVE_K,
) -> list[Episode]:
    return store.retrieve(query, k=k)
