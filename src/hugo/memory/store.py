"""Persistent durable-facts store — HUGO's memory across `hugo start`
sessions (single-user by design, per the project's grill session: no
speaker ID, one shared pool of "things about Eduard", no access control).

Caveat worth being explicit about: the DB lives under Config.state_dir,
which defaults to the DGX Spark's `jim` account's home directory — and
`jim` is a *shared team account* on dgx1, not exclusive to Eduard (see
docs/adr/0002's memory notes). This store doesn't attempt multi-user
isolation — that would mean re-opening the single-user decision, not this
module's call to make. It just means: if a teammate also runs `hugo start`
under `jim`, they read and write the same facts DB. Fine as long as only
Eduard actually runs HUGO regularly; worth flagging if that assumption
ever stops holding.

Uses stdlib sqlite3 (blocking) wrapped in asyncio.to_thread rather than an
async SQLite driver — this is a low-frequency path (facts read at startup,
written occasionally during conversation), not a hot loop, so the extra
dependency isn't worth it.
"""

import asyncio
import re
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from hugo.memory.models import Fact

_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def squash(text: str) -> str:
    """Lowercases and drops everything that isn't a letter or a digit.

    Recall matching has to be generous or it hides facts: HUGO writes down
    what the user said ("stand-up meeting is at 9:30") and the user asks
    back in their own words ("standup"), which plain substring matching
    misses on the hyphen alone. Squashing both sides makes them meet in the
    middle. The cost is false positives across word boundaries, which is
    the tolerable direction — a query is a hint, never a gate.
    """
    return _NOT_ALPHANUMERIC.sub("", text.lower())


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    async def add_fact(self, content: str) -> Fact:
        return await asyncio.to_thread(self._add_fact_sync, content)

    def _add_fact_sync(self, content: str) -> Fact:
        conn = self._connect()
        try:
            created_at = datetime.now(UTC)
            cursor = conn.execute(
                "INSERT INTO facts (content, created_at) VALUES (?, ?)",
                (content, created_at.isoformat()),
            )
            conn.commit()
            fact_id = cursor.lastrowid
            assert fact_id is not None
            return Fact(id=fact_id, content=content, created_at=created_at)
        finally:
            conn.close()

    async def all_facts(self) -> list[Fact]:
        return await asyncio.to_thread(self._all_facts_sync)

    def _all_facts_sync(self) -> list[Fact]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT id, content, created_at FROM facts ORDER BY id").fetchall()
            return [
                Fact(id=row[0], content=row[1], created_at=datetime.fromisoformat(row[2]))
                for row in rows
            ]
        finally:
            conn.close()

    async def search_facts(self, terms: Sequence[str], limit: int) -> list[Fact]:
        return await asyncio.to_thread(self._search_facts_sync, list(terms), limit)

    def _search_facts_sync(self, terms: list[str], limit: int) -> list[Fact]:
        """Newest first, optionally filtered — the read recall is built on.

        Descending id IS "the newest thing you said wins": a correction is
        a new row, so reading newest-first means the model sees 9:45 before
        it ever sees 9:30, and nothing has to be deleted or updated. No
        terms means no WHERE clause, i.e. the newest `limit` facts.

        Matching goes through `squash` on both sides rather than plain
        LIKE, registered as a SQL function so the two sides cannot drift
        apart. There is no index on content; the table holds a few dozen
        rows of a single user's standing facts, and the same growth that
        would make a scan hurt is the growth that makes FTS5 worth its
        migration story.
        """
        conn = self._connect()
        try:
            conn.create_function("squash", 1, squash, deterministic=True)
            sql = "SELECT id, content, created_at FROM facts"
            parameters: list[object] = []
            if terms:
                clauses = ["squash(content) LIKE '%' || ? || '%'"] * len(terms)
                sql += " WHERE " + " OR ".join(clauses)
                parameters.extend(squash(term) for term in terms)
            sql += " ORDER BY id DESC LIMIT ?"
            parameters.append(limit)
            rows = conn.execute(sql, parameters).fetchall()
            return [
                Fact(id=row[0], content=row[1], created_at=datetime.fromisoformat(row[2]))
                for row in rows
            ]
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)
