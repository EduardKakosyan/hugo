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
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from hugo.memory.models import Fact


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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)
