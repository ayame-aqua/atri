"""本地哈希 n-gram 向量。不下载模型，CI 与本机都不依赖 GPU。"""

from __future__ import annotations

import hashlib
import math

from src.memory.constants import EMBED_DIM, NGRAM_SIZES


def embed_text(text: str) -> list[float]:
    vector = [0.0] * EMBED_DIM
    normalized = (text or "").casefold().strip()
    if not normalized:
        return vector
    for size in NGRAM_SIZES:
        for gram in _ngrams(normalized, size):
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % EMBED_DIM
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
    return _l2_normalize(vector)


def _ngrams(text: str, size: int) -> list[str]:
    if len(text) < size:
        return [text]
    return [text[i : i + size] for i in range(len(text) - size + 1)]


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(item * item for item in vector))
    if norm == 0.0:
        return vector
    return [item / norm for item in vector]
