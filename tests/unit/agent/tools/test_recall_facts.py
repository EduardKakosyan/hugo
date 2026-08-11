"""Tests recall against a real tmp_path SQLite store. The behaviours worth
pinning are the two that make the query a hint rather than a gate: newest
first, and a miss that widens instead of denying."""

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from hugo.agent.tools import ToolFailure
from hugo.agent.tools.recall_facts import _RECALL_LIMIT, RecallFactsTool
from hugo.memory.models import Fact
from hugo.memory.store import MemoryStore

_ZONE = "America/Halifax"


class _FailingStore(MemoryStore):
    def __init__(self, error: Exception) -> None:
        super().__init__(Path("unused.db"))
        self._error = error

    async def search_facts(self, terms: Sequence[str], limit: int) -> list[Fact]:
        raise self._error


def _assert_speakable(text: str) -> None:
    assert "sqlite" not in text.lower(), f"sqlite leaked: {text!r}"
    for class_tell in ("Error", "Exception", "OperationalError", "locked"):
        assert class_tell not in text, f"internals leaked: {text!r}"


async def _store_with(tmp_path: Path, *contents: str) -> MemoryStore:
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    for content in contents:
        await store.add_fact(content)
    return store


async def test_a_hit_reads_newest_first(tmp_path: Path) -> None:
    """The correction has to arrive ahead of what it corrects: the model reads
    top-down, so 9:45 must be the first thing it sees."""
    store = await _store_with(
        tmp_path, "stand-up meeting is at 9:30", "stand-up meeting is at 9:45"
    )

    result = await RecallFactsTool(store, _ZONE).invoke({"query": "standup"})

    assert isinstance(result, str)
    lines = result.splitlines()
    assert lines[0].startswith("stand-up meeting is at 9:45")
    assert lines[1].startswith("stand-up meeting is at 9:30")


async def test_each_line_carries_a_spoken_timestamp(tmp_path: Path) -> None:
    """Rendered in the configured zone, not the UTC it is stored in: this
    string gets spoken, and reading a fact saved at 5:40 PM back as 9:40 PM is
    the same confidently-wrong answer the host-clock get_current_time shipped."""
    store = await _store_with(tmp_path, "the dentist is on Thursday")

    result = await RecallFactsTool(store, _ZONE).invoke({"query": "dentist"})

    assert isinstance(result, str)
    local = datetime.now(UTC).astimezone(ZoneInfo(_ZONE))
    assert local.strftime("%-d %B") in result
    assert local.strftime("%-I:%M %p") in result
    # No ISO strings and no row ids: nothing in the line is for a parser.
    assert "T" + local.strftime("%H") not in result


async def test_a_miss_falls_back_to_everything_rather_than_denying(tmp_path: Path) -> None:
    """A filter that hides a fact the user watched HUGO write down produces
    "you never told me that" — the exact failure the audible write prevents."""
    store = await _store_with(tmp_path, "stand-up meeting is at 9:30")

    result = await RecallFactsTool(store, _ZONE).invoke({"query": "dentist"})

    assert isinstance(result, str)
    assert "No facts matched 'dentist'" in result
    assert "stand-up meeting is at 9:30" in result


async def test_an_empty_query_lists_what_is_known(tmp_path: Path) -> None:
    """ "What do you know about me" is a real thing to say, and a required
    argument would answer it with a validation failure."""
    store = await _store_with(tmp_path, "Eduard prefers metric units")

    result = await RecallFactsTool(store, _ZONE).invoke({})

    assert isinstance(result, str)
    assert "Eduard prefers metric units" in result
    assert "No facts matched" not in result


async def test_an_empty_store_says_so_instead_of_matching_nothing(tmp_path: Path) -> None:
    store = await _store_with(tmp_path)

    result = await RecallFactsTool(store, _ZONE).invoke({"query": "standup"})

    assert result == "Nothing has been saved about the user yet."


async def test_both_paths_are_capped_at_the_recall_limit(tmp_path: Path) -> None:
    """The accepted cost of the miss-fallback is dumping the store, so the
    dump is bounded."""
    store = await _store_with(
        tmp_path, *(f"fact number {index}" for index in range(_RECALL_LIMIT + 10))
    )
    tool = RecallFactsTool(store, _ZONE)

    matched = await tool.invoke({"query": "fact"})
    missed = await tool.invoke({"query": "dentist"})

    assert isinstance(matched, str) and isinstance(missed, str)
    assert len(matched.splitlines()) == _RECALL_LIMIT
    # One extra line for the "no facts matched" preamble.
    assert len(missed.splitlines()) == _RECALL_LIMIT + 1


async def test_a_busy_database_is_retryable() -> None:
    tool = RecallFactsTool(_FailingStore(sqlite3.OperationalError("database is locked")), _ZONE)

    result = await tool.invoke({"query": "standup"})

    assert isinstance(result, ToolFailure)
    assert result.retryable
    _assert_speakable(result.text)


async def test_any_other_sqlite_failure_is_terminal() -> None:
    tool = RecallFactsTool(_FailingStore(sqlite3.DatabaseError("not a database")), _ZONE)

    result = await tool.invoke({"query": "standup"})

    assert isinstance(result, ToolFailure)
    assert not result.retryable
    _assert_speakable(result.text)


def test_schema_is_flat_with_an_optional_query() -> None:
    function = RecallFactsTool.schema["function"]

    assert function["name"] == "recall_facts"
    parameters = function["parameters"]
    assert "required" not in parameters  # type: ignore[operator]
    assert "query" in parameters["properties"]  # type: ignore[index]
    assert "$defs" not in repr(parameters) and "$ref" not in repr(parameters)
