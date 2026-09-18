"""情节摘要的 LanceDB 索引，文件落在 data/vectors/（gitignore）。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa

from src.memory.constants import EMBED_DIM, EMBED_ID_PREFIX, VECTOR_TABLE

logger = logging.getLogger(__name__)

_EMBED_ID_RE = re.compile(rf"^{re.escape(EMBED_ID_PREFIX)}\d+$")


@dataclass(frozen=True)
class VectorHit:
    episode_id: int
    embedding_id: str
    distance: float


class EpisodeIndex:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(self._path)
        self._ensure_table()

    def upsert(self, embedding_id: str, episode_id: int, vector: list[float]) -> None:
        _validate_embedding_id(embedding_id)
        table = self._table()
        table.delete(f"embedding_id = '{embedding_id}'")
        table.add(
            [
                {
                    "embedding_id": embedding_id,
                    "episode_id": int(episode_id),
                    "vector": [float(item) for item in vector],
                }
            ]
        )

    def delete(self, embedding_id: str) -> None:
        _validate_embedding_id(embedding_id)
        self._table().delete(f"embedding_id = '{embedding_id}'")

    def search(self, vector: list[float], k: int) -> list[VectorHit]:
        if k <= 0:
            return []
        table = self._table()
        if table.count_rows() == 0:
            return []
        query = np.array(vector, dtype=np.float32)
        rows = table.search(query).limit(k).to_list()
        hits: list[VectorHit] = []
        for row in rows:
            hits.append(
                VectorHit(
                    episode_id=int(row["episode_id"]),
                    embedding_id=str(row["embedding_id"]),
                    distance=float(row.get("_distance", 0.0)),
                )
            )
        return hits

    def _ensure_table(self) -> None:
        names = list(self._db.list_tables().tables or [])
        if VECTOR_TABLE in names:
            return
        schema = pa.schema(
            [
                pa.field("embedding_id", pa.string()),
                pa.field("episode_id", pa.int64()),
                pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
            ]
        )
        self._db.create_table(VECTOR_TABLE, schema=schema)
        logger.info("vector table created backend=lancedb table=%s", VECTOR_TABLE)

    def _table(self):
        return self._db.open_table(VECTOR_TABLE)


def embedding_id_for(episode_id: int) -> str:
    return f"{EMBED_ID_PREFIX}{int(episode_id)}"


def _validate_embedding_id(embedding_id: str) -> None:
    if not _EMBED_ID_RE.match(embedding_id):
        msg = f"invalid embedding_id={embedding_id}"
        raise ValueError(msg)
