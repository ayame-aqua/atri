"""SQLite 核心事实。P2-A：跨重启记得称呼和约定。"""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import REPO_ROOT

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


class MemoryStore:
    def __init__(
        self,
        path: Path | str | None = None,
        *,
        seed: bool = False,
    ) -> None:
        self._path = path
        self._seed = seed
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()
        if seed:
            self._seed_defaults()

    def profile_block(self) -> str:
        rows = self.list_facts(status="active")
        if not rows:
            return ""
        lines = [f"- {row.key}: {row.value}" for row in rows]
        return "长期记忆，不是刚刚这句对话：\n" + "\n".join(lines)

    def retrieve(self, query: str, k: int = 5) -> list[Any]:
        del query, k
        return []

    def add_fact(
        self,
        key: str,
        value: str,
        category: str = "profile",
        *,
        source: str = "manual",
        evidence: str | None = None,
        overwrite: bool = False,
    ) -> Fact:
        mapped_category = _category(category)
        existing = self.get_by_key(key)
        if existing is not None and not overwrite:
            if _protected(key):
                logger.info("memory skip protected key=%s", key)
                return existing
        if existing is not None and source != "user_cmd" and _protected(key):
            logger.info("memory skip protected key=%s", key)
            return existing
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO facts (key, value, category, status, source, evidence, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    status = 'active',
                    source = excluded.source,
                    evidence = excluded.evidence,
                    updated_at = datetime('now')
                """,
                (key, value, mapped_category, source, evidence),
            )
            conn.commit()
        fact = self.get_by_key(key)
        if fact is None:
            msg = f"memory write failed key={key}"
            raise RuntimeError(msg)
        logger.info("memory upsert key=%s source=%s", key, source)
        return fact

    def list_facts(self, status: str | None = "active") -> list[Fact]:
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
                "SELECT id, key, value, category, status, source, evidence "
                "FROM facts WHERE id = ?",
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
        new_status = current.status if status is None else status
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
        for fact in self.list_facts(status="active"):
            if needle in fact.key or needle in fact.value:
                updated = self.update_fact(fact.id, status="archived")
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
                source="user_cmd",
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
                source="user_cmd",
                evidence=raw,
                overwrite=True,
            )
            self.add_fact(
                KEY_NICKNAME,
                nickname,
                category="identity",
                source="user_cmd",
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
            key = item.get("key")
            value = item.get("value")
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            if not any(key.startswith(prefix) for prefix in LOW_RISK_PREFIXES):
                logger.info("memory skip high-risk candidate key=%s", key)
                continue
            if _protected(key):
                continue
            self.add_fact(
                key,
                value,
                category="preference",
                source="extract",
                overwrite=False,
            )

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


def _category(raw: str) -> str:
    allowed = {"identity", "relationship", "rule", "preference", "other"}
    if raw in allowed:
        return raw
    if raw == "profile":
        return "other"
    return "other"


def _protected(key: str) -> bool:
    if key in PROTECTED_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def _remember_key(value: str) -> str:
    slug = _SLUG_KEEP.sub("", value)[:MAX_SLUG] or "note"
    if "讨厌" in value or "别催" in value or "不要催" in value:
        return f"dislikes.{slug}"
    return f"prefers.{slug}"
