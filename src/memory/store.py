"""SQLite 记忆。P2-A 事实；P2-B 待确认、情节、风格。"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import REPO_ROOT
from src.memory.constants import (
    DEFAULT_CHAT_ID,
    DEFAULT_RETRIEVE_K,
    DEFAULT_STYLE_MAX,
    EPISODE_LAYERS,
    HIGH_RISK_PREFIXES,
    LAYER_PROFILE,
    RETRIEVE_K_MAX,
    RETRIEVE_K_MIN,
    SOURCE_EXTRACT,
    SOURCE_GROUP_IMPORT,
    SOURCE_USER_CMD,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_CANDIDATE,
    STATUS_CONFIRMED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STYLE_LAYERS,
)
from src.memory.embedder import embed_text
from src.memory.vectors import EpisodeIndex, embedding_id_for

logger = logging.getLogger(__name__)

SCHEMA_PATH = REPO_ROOT / "memory" / "schema.sql"
DEFAULT_NICKNAME = "你"
DEFAULT_RELATIONSHIP = "与四季夏目"
KEY_NICKNAME = "user.nickname_from_her"
KEY_DISPLAY_NAME = "user.display_name"
KEY_RELATIONSHIP = "relationship"
KEY_CREATED = "created_together_at"
PROTECTED_KEYS = frozenset({KEY_RELATIONSHIP})
PROTECTED_PREFIXES = ("rule.",)
LOW_RISK_PREFIXES = ("prefers.",)
MAX_SLUG = 24

_REMEMBER = re.compile(r"^记住[：:]\s*(.+)$")
_FORGET = re.compile(r"^忘掉[：:]?\s*(.+)$")
_INTRO = re.compile(r"我叫(.+?)[，,]\s*你叫我(.+)$")
_SLUG_KEEP = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(frozen=True)
class Fact:
    id: int
    key: str
    value: str
    category: str
    status: str
    source: str
    evidence: str | None


@dataclass(frozen=True)
class Episode:
    id: int
    summary: str
    happened_at: str
    source_chat_id: str
    status: str
    embedding_id: str | None


@dataclass(frozen=True)
class StyleTerm:
    id: int
    term: str
    meaning: str
    usage: str
    status: str
    evidence: str | None
    count: int


class MemoryStore:
    def __init__(
        self,
        path: Path | str | None = None,
        *,
        seed: bool = False,
        vector_path: Path | str | None = None,
        retrieve_k: int = DEFAULT_RETRIEVE_K,
        style_max: int = DEFAULT_STYLE_MAX,
    ) -> None:
        self._path = path
        self._seed = seed
        self._conn: sqlite3.Connection | None = None
        self._retrieve_k = _clamp_k(retrieve_k)
        self._style_max = max(1, int(style_max))
        self._index = EpisodeIndex(vector_path) if vector_path is not None else None
        self._ensure_schema()
        if seed:
            self._seed_defaults()

    def profile_block(self) -> str:
        rows = self.list_facts(status=STATUS_ACTIVE)
        if not rows:
            return ""
        lines = [f"- {row.key}: {row.value}" for row in rows]
        return "长期记忆，不是刚刚这句对话：\n" + "\n".join(lines)

    def style_block(self, limit: int | None = None) -> str:
        cap = self._style_max if limit is None else max(1, int(limit))
        rows = self.list_style(status=STATUS_CONFIRMED)[:cap]
        if not rows:
            return ""
        lines = []
        for row in rows:
            line = f"- {row.term}：{row.meaning}"
            if row.usage:
                line += f" 用法：{row.usage}"
            lines.append(line)
        return "已确认的口吻与黑话（按这个说，不是当前对话）：\n" + "\n".join(lines)

    def episodes_block(self, query: str, extra: str = "") -> str:
        text = " ".join(part for part in (query, extra) if part).strip()
        rows = self.retrieve(text, k=self._retrieve_k)
        if not rows:
            return ""
        lines = [f"- {row.happened_at} {row.source_chat_id}：{row.summary}" for row in rows]
        return "检索到的情节记忆（长期记忆，不是当前对话）：\n" + "\n".join(lines)

    def retrieve(self, query: str, k: int = DEFAULT_RETRIEVE_K) -> list[Episode]:
        if self._index is None:
            return []
        limit = _clamp_k(k)
        hits = self._index.search(embed_text(query), k=max(limit * 3, RETRIEVE_K_MAX))
        found: list[Episode] = []
        seen: set[int] = set()
        for hit in hits:
            if hit.episode_id in seen:
                continue
            episode = self.get_episode(hit.episode_id)
            if episode is None or episode.status != STATUS_ACTIVE:
                continue
            seen.add(episode.id)
            found.append(episode)
            if len(found) >= limit:
                break
        return found

    def add_fact(
        self,
        key: str,
        value: str,
        category: str = "profile",
        *,
        source: str = "manual",
        evidence: str | None = None,
        overwrite: bool = False,
        status: str = STATUS_ACTIVE,
    ) -> Fact:
        mapped_category = _category(category)
        write_status = _fact_status(status)
        existing = self.get_by_key(key)
        if existing is not None and not overwrite:
            if _protected(key):
                logger.info("memory skip protected key=%s", key)
                return existing
        if existing is not None and source != SOURCE_USER_CMD and _protected(key):
            logger.info("memory skip protected key=%s", key)
            return existing
        if (
            existing is not None
            and existing.status == STATUS_ACTIVE
            and source == SOURCE_EXTRACT
            and write_status == STATUS_PENDING
        ):
            logger.info("memory skip extract over active key=%s", key)
            return existing
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO facts (key, value, category, status, source, evidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    status = excluded.status,
                    source = excluded.source,
                    evidence = excluded.evidence,
                    updated_at = datetime('now')
                """,
                (key, value, mapped_category, write_status, source, evidence),
            )
            conn.commit()
        fact = self.get_by_key(key)
        if fact is None:
            msg = f"memory write failed key={key}"
            raise RuntimeError(msg)
        logger.info("memory upsert key=%s source=%s status=%s", key, source, fact.status)
        return fact

    def list_facts(self, status: str | None = STATUS_ACTIVE) -> list[Fact]:
        with self._session() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT id, key, value, category, status, source, evidence "
                    "FROM facts WHERE status = ? ORDER BY id",
                    (status,),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, key, value, category, status, source, evidence "
                    "FROM facts ORDER BY id"
                )
            return [_fact(row) for row in cursor.fetchall()]

    def get_by_id(self, fact_id: int) -> Fact | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, key, value, category, status, source, evidence FROM facts WHERE id = ?",
                (fact_id,),
            ).fetchone()
        return None if row is None else _fact(row)

    def get_by_key(self, key: str) -> Fact | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, key, value, category, status, source, evidence "
                "FROM facts WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else _fact(row)

    def update_fact(
        self,
        fact_id: int,
        *,
        value: str | None = None,
        status: str | None = None,
    ) -> Fact | None:
        current = self.get_by_id(fact_id)
        if current is None:
            return None
        new_value = current.value if value is None else value
        new_status = current.status if status is None else _fact_status(status)
        with self._session() as conn:
            conn.execute(
                "UPDATE facts SET value = ?, status = ?, updated_at = datetime('now') WHERE id = ?",
                (new_value, new_status, fact_id),
            )
            conn.commit()
        return self.get_by_id(fact_id)

    def delete_fact(self, fact_id: int) -> bool:
        with self._session() as conn:
            cursor = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            conn.commit()
            return cursor.rowcount > 0

    def forget(self, query: str) -> list[Fact]:
        needle = (query or "").strip()
        if not needle:
            return []
        hits: list[Fact] = []
        for fact in self.list_facts(status=STATUS_ACTIVE):
            if needle in fact.key or needle in fact.value:
                updated = self.update_fact(fact.id, status=STATUS_ARCHIVED)
                if updated is not None:
                    hits.append(updated)
                    logger.info("memory archived id=%s key=%s", fact.id, fact.key)
        return hits

    def apply_user_text(self, text: str) -> bool:
        """自然语言记住/忘掉/自我介绍。返回是否动过库。"""
        raw = (text or "").strip()
        remember = _REMEMBER.match(raw)
        if remember:
            value = remember.group(1).strip()
            key = _remember_key(value)
            self.add_fact(
                key,
                value,
                category="preference",
                source=SOURCE_USER_CMD,
                evidence=raw,
                overwrite=True,
            )
            return True
        forget = _FORGET.match(raw)
        if forget:
            self.forget(forget.group(1).strip())
            return True
        intro = _INTRO.search(raw)
        if intro:
            display = intro.group(1).strip()
            nickname = intro.group(2).strip()
            self.add_fact(
                KEY_DISPLAY_NAME,
                display,
                category="identity",
                source=SOURCE_USER_CMD,
                evidence=raw,
                overwrite=True,
            )
            self.add_fact(
                KEY_NICKNAME,
                nickname,
                category="identity",
                source=SOURCE_USER_CMD,
                evidence=raw,
                overwrite=True,
            )
            return True
        return False

    def ingest_candidates(self, candidates: list[Any], *, parse_ok: bool) -> None:
        if not parse_ok:
            logger.info("memory skip candidates parse_ok=false")
            return
        for item in candidates:
            if not isinstance(item, dict):
                continue
            self._ingest_one(item, source=SOURCE_EXTRACT)

    def add_episode(
        self,
        summary: str,
        *,
        source_chat_id: str = DEFAULT_CHAT_ID,
        status: str = STATUS_PENDING,
        happened_at: str | None = None,
    ) -> Episode:
        text = (summary or "").strip()
        if not text:
            msg = "episode summary required"
            raise ValueError(msg)
        write_status = _episode_status(status)
        chat_id = source_chat_id.strip() or DEFAULT_CHAT_ID
        with self._session() as conn:
            if happened_at:
                cursor = conn.execute(
                    """
                    INSERT INTO episodes (summary, happened_at, source_chat_id, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (text, happened_at, chat_id, write_status),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO episodes (summary, source_chat_id, status)
                    VALUES (?, ?, ?)
                    """,
                    (text, chat_id, write_status),
                )
            episode_id = int(cursor.lastrowid)
            embed_id = embedding_id_for(episode_id)
            conn.execute(
                "UPDATE episodes SET embedding_id = ? WHERE id = ?",
                (embed_id, episode_id),
            )
            conn.commit()
        if self._index is not None:
            self._index.upsert(embed_id, episode_id, embed_text(text))
        episode = self.get_episode(episode_id)
        if episode is None:
            msg = f"episode write failed id={episode_id}"
            raise RuntimeError(msg)
        logger.info("memory episode id=%s status=%s", episode.id, episode.status)
        return episode

    def list_episodes(self, status: str | None = None) -> list[Episode]:
        with self._session() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT id, summary, happened_at, source_chat_id, status, embedding_id "
                    "FROM episodes WHERE status = ? ORDER BY id",
                    (status,),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, summary, happened_at, source_chat_id, status, embedding_id "
                    "FROM episodes ORDER BY id"
                )
            return [_episode(row) for row in cursor.fetchall()]

    def get_episode(self, episode_id: int) -> Episode | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, summary, happened_at, source_chat_id, status, embedding_id "
                "FROM episodes WHERE id = ?",
                (episode_id,),
            ).fetchone()
        return None if row is None else _episode(row)

    def update_episode(
        self,
        episode_id: int,
        *,
        status: str | None = None,
        summary: str | None = None,
    ) -> Episode | None:
        current = self.get_episode(episode_id)
        if current is None:
            return None
        new_status = current.status if status is None else _episode_status(status)
        new_summary = current.summary if summary is None else summary.strip()
        with self._session() as conn:
            conn.execute(
                "UPDATE episodes SET summary = ?, status = ? WHERE id = ?",
                (new_summary, new_status, episode_id),
            )
            conn.commit()
        updated = self.get_episode(episode_id)
        if updated is not None and updated.embedding_id and self._index is not None:
            if new_status == STATUS_ARCHIVED:
                self._index.delete(updated.embedding_id)
            else:
                self._index.upsert(updated.embedding_id, updated.id, embed_text(updated.summary))
        return updated

    def add_style_term(
        self,
        term: str,
        meaning: str,
        *,
        usage: str = "",
        evidence: str | None = None,
        status: str = STATUS_CANDIDATE,
        source_count: int = 1,
    ) -> StyleTerm:
        name = (term or "").strip()
        sense = (meaning or "").strip()
        if not name or not sense:
            msg = "style term and meaning required"
            raise ValueError(msg)
        write_status = _style_status(status)
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO style_terms (term, meaning, usage, status, evidence, count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(term) DO UPDATE SET
                    meaning = CASE
                        WHEN style_terms.status = 'candidate' THEN excluded.meaning
                        ELSE style_terms.meaning
                    END,
                    usage = CASE
                        WHEN style_terms.status = 'candidate' THEN excluded.usage
                        ELSE style_terms.usage
                    END,
                    evidence = excluded.evidence,
                    count = style_terms.count + excluded.count,
                    updated_at = datetime('now')
                """,
                (name, sense, usage.strip(), write_status, evidence, source_count),
            )
            conn.commit()
        row = self.get_style_by_term(name)
        if row is None:
            msg = f"style write failed term={name}"
            raise RuntimeError(msg)
        logger.info("memory style id=%s term=%s status=%s", row.id, row.term, row.status)
        return row

    def list_style(self, status: str | None = None) -> list[StyleTerm]:
        with self._session() as conn:
            if status:
                cursor = conn.execute(
                    "SELECT id, term, meaning, usage, status, evidence, count "
                    "FROM style_terms WHERE status = ? ORDER BY id",
                    (status,),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, term, meaning, usage, status, evidence, count "
                    "FROM style_terms ORDER BY id"
                )
            return [_style(row) for row in cursor.fetchall()]

    def get_style(self, style_id: int) -> StyleTerm | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, term, meaning, usage, status, evidence, count "
                "FROM style_terms WHERE id = ?",
                (style_id,),
            ).fetchone()
        return None if row is None else _style(row)

    def get_style_by_term(self, term: str) -> StyleTerm | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT id, term, meaning, usage, status, evidence, count "
                "FROM style_terms WHERE term = ?",
                (term,),
            ).fetchone()
        return None if row is None else _style(row)

    def update_style(self, style_id: int, *, status: str) -> StyleTerm | None:
        if self.get_style(style_id) is None:
            return None
        write_status = _style_status(status)
        with self._session() as conn:
            conn.execute(
                "UPDATE style_terms SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (write_status, style_id),
            )
            conn.commit()
        return self.get_style(style_id)

    def confirm_style(self, style_id: int) -> StyleTerm | None:
        return self.update_style(style_id, status=STATUS_CONFIRMED)

    def ingest_import_rows(self, rows: list[dict[str, Any]]) -> int:
        """群导入：事实 pending、风格 candidate、情节 pending，不转正。"""
        written = 0
        for item in rows:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row.setdefault("layer", LAYER_PROFILE)
            self._ingest_one(row, source=SOURCE_GROUP_IMPORT)
            written += 1
        return written

    def _ingest_one(self, item: dict[str, Any], *, source: str) -> None:
        layer = item.get("layer") or LAYER_PROFILE
        if not isinstance(layer, str):
            return
        if layer in EPISODE_LAYERS:
            summary = item.get("summary") if isinstance(item.get("summary"), str) else None
            if summary is None and isinstance(item.get("value"), str):
                summary = item["value"]
            if not summary or not summary.strip():
                return
            chat_id = item.get("source_chat_id")
            source_chat_id = chat_id if isinstance(chat_id, str) and chat_id else DEFAULT_CHAT_ID
            self.add_episode(
                summary.strip(),
                source_chat_id=source_chat_id,
                status=STATUS_PENDING,
            )
            return
        if layer in STYLE_LAYERS:
            term = item.get("term") if isinstance(item.get("term"), str) else item.get("key")
            meaning = (
                item.get("meaning") if isinstance(item.get("meaning"), str) else item.get("value")
            )
            usage = item.get("usage") if isinstance(item.get("usage"), str) else ""
            evidence = item.get("evidence") if isinstance(item.get("evidence"), str) else None
            if not isinstance(term, str) or not isinstance(meaning, str):
                return
            self.add_style_term(
                term,
                meaning,
                usage=usage or "",
                evidence=evidence,
                status=STATUS_CANDIDATE,
            )
            return
        key = item.get("key")
        value = item.get("value")
        if not isinstance(key, str) or not isinstance(value, str):
            return
        if source == SOURCE_GROUP_IMPORT:
            self.add_fact(
                key,
                value,
                category=_category_for_key(key),
                source=source,
                overwrite=False,
                status=STATUS_PENDING,
            )
            return
        if any(key.startswith(prefix) for prefix in LOW_RISK_PREFIXES):
            self.add_fact(
                key,
                value,
                category="preference",
                source=source,
                overwrite=False,
                status=STATUS_ACTIVE,
            )
            return
        if _high_risk(key):
            self.add_fact(
                key,
                value,
                category=_category_for_key(key),
                source=source,
                overwrite=False,
                status=STATUS_PENDING,
            )
            return
        logger.info("memory skip unknown-risk candidate key=%s", key)

    def _ensure_schema(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with self._session() as conn:
            conn.executescript(sql)
            conn.commit()

    def _seed_defaults(self) -> None:
        if self.get_by_key(KEY_NICKNAME) is None:
            self.add_fact(
                KEY_NICKNAME,
                DEFAULT_NICKNAME,
                category="identity",
                source="manual",
            )
        if self.get_by_key(KEY_RELATIONSHIP) is None:
            self.add_fact(
                KEY_RELATIONSHIP,
                DEFAULT_RELATIONSHIP,
                category="relationship",
                source="manual",
            )
        if self.get_by_key(KEY_CREATED) is None:
            with self._session() as conn:
                now = conn.execute("SELECT datetime('now')").fetchone()[0]
            self.add_fact(
                KEY_CREATED,
                str(now),
                category="other",
                source="manual",
            )

    @contextmanager
    def _session(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            self._close_if_file(conn)

    def _connect(self) -> sqlite3.Connection:
        if self._path is None:
            if self._conn is None:
                self._conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
            return self._conn
        path = Path(self._path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_if_file(self, conn: sqlite3.Connection) -> None:
        if self._path is not None:
            conn.close()


def _fact(row: sqlite3.Row) -> Fact:
    return Fact(
        id=int(row["id"]),
        key=str(row["key"]),
        value=str(row["value"]),
        category=str(row["category"]),
        status=str(row["status"]),
        source=str(row["source"]),
        evidence=row["evidence"],
    )


def _episode(row: sqlite3.Row) -> Episode:
    return Episode(
        id=int(row["id"]),
        summary=str(row["summary"]),
        happened_at=str(row["happened_at"]),
        source_chat_id=str(row["source_chat_id"]),
        status=str(row["status"]),
        embedding_id=row["embedding_id"],
    )


def _style(row: sqlite3.Row) -> StyleTerm:
    return StyleTerm(
        id=int(row["id"]),
        term=str(row["term"]),
        meaning=str(row["meaning"]),
        usage=str(row["usage"]),
        status=str(row["status"]),
        evidence=row["evidence"],
        count=int(row["count"]),
    )


def _category(raw: str) -> str:
    allowed = {"identity", "relationship", "rule", "preference", "other"}
    if raw in allowed:
        return raw
    if raw == "profile":
        return "other"
    return "other"


def _category_for_key(key: str) -> str:
    if key == KEY_RELATIONSHIP:
        return "relationship"
    if key.startswith("rule."):
        return "rule"
    if key.startswith("dislikes.") or key.startswith("prefers."):
        return "preference"
    return "other"


def _protected(key: str) -> bool:
    if key in PROTECTED_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def _high_risk(key: str) -> bool:
    if key in PROTECTED_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in HIGH_RISK_PREFIXES)


def _remember_key(value: str) -> str:
    slug = _SLUG_KEEP.sub("", value)[:MAX_SLUG] or "note"
    if "讨厌" in value or "别催" in value or "不要催" in value:
        return f"dislikes.{slug}"
    return f"prefers.{slug}"


def _clamp_k(k: int) -> int:
    return max(RETRIEVE_K_MIN, min(int(k), RETRIEVE_K_MAX))


def _fact_status(raw: str) -> str:
    allowed = {STATUS_ACTIVE, STATUS_PENDING, STATUS_ARCHIVED}
    if raw in allowed:
        return raw
    return STATUS_ACTIVE


def _episode_status(raw: str) -> str:
    allowed = {STATUS_ACTIVE, STATUS_PENDING, STATUS_ARCHIVED}
    if raw in allowed:
        return raw
    return STATUS_PENDING


def _style_status(raw: str) -> str:
    allowed = {STATUS_CANDIDATE, STATUS_CONFIRMED, STATUS_REJECTED}
    if raw in allowed:
        return raw
    return STATUS_CANDIDATE
