"""Tests the only tool that writes, against a real tmp_path SQLite store (the
convention in tests/unit/memory/test_store.py -- no fakes for the store
itself). What's worth pinning is that the stored wording comes back verbatim,
because that string is what the model reads out and it is the whole of the
audible-write guarantee."""

import sqlite3
from pathlib import Path

from hugo.agent.tools import ToolFailure
from hugo.agent.tools.remember_fact import RememberFactTool
from hugo.memory.store import MemoryStore


class _FailingStore(MemoryStore):
    """A store whose write raises what sqlite would raise."""

    def __init__(self, error: Exception) -> None:
        super().__init__(Path("unused.db"))
        self._error = error

    async def add_fact(self, content: str) -> None:  # type: ignore[override]
        raise self._error


def _assert_speakable(text: str) -> None:
    """Failure text is paraphrased aloud, so it carries nothing internal: no
    exception class names, no file paths, no SQL (agent/tools/__init__.py)."""
    assert "sqlite" not in text.lower(), f"sqlite leaked: {text!r}"
    for class_tell in ("Error", "Exception", "OperationalError", "locked", "db"):
        assert class_tell not in text, f"internals leaked: {text!r}"


async def test_the_stored_wording_comes_back_verbatim(tmp_path: Path) -> None:
    """The model speaks this string back, so it has to BE what was stored --
    the user hears what HUGO now believes at the moment it happens."""
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    tool = RememberFactTool(store)

    result = await tool.invoke({"content": "stand-up meeting is at 9:30"})

    assert result == 'Saved: "stand-up meeting is at 9:30"'
    facts = await store.all_facts()
    assert [f.content for f in facts] == ["stand-up meeting is at 9:30"]


async def test_a_correction_is_a_new_row_not_an_edit(tmp_path: Path) -> None:
    """No delete path exists on purpose: a voice-driven delete against a fuzzy
    match needs a confirmation flow, and newest-wins recall doesn't."""
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()
    tool = RememberFactTool(store)

    await tool.invoke({"content": "stand-up meeting is at 9:30"})
    await tool.invoke({"content": "stand-up meeting is at 9:45"})

    assert [f.content for f in await store.all_facts()] == [
        "stand-up meeting is at 9:30",
        "stand-up meeting is at 9:45",
    ]


async def test_a_busy_database_is_retryable(tmp_path: Path) -> None:
    """A failed write MUST be audible: HUGO saying "I've written that down"
    over a write that didn't happen tells the user something false about their
    own data, which they'd only discover days later."""
    tool = RememberFactTool(_FailingStore(sqlite3.OperationalError("database is locked")))

    result = await tool.invoke({"content": "standup is at 9:30"})

    assert isinstance(result, ToolFailure)
    assert result.retryable
    _assert_speakable(result.text)


async def test_any_other_sqlite_failure_is_terminal() -> None:
    """Retrying a broken schema or a corrupt file costs the user ten seconds
    before the same bad news."""
    tool = RememberFactTool(_FailingStore(sqlite3.DatabaseError("file is not a database")))

    result = await tool.invoke({"content": "standup is at 9:30"})

    assert isinstance(result, ToolFailure)
    assert not result.retryable
    _assert_speakable(result.text)


async def test_missing_content_is_reported_without_writing(tmp_path: Path) -> None:
    """vLLM never validates arguments (unconstrained tool_choice="auto"), so
    the model really can call this with nothing in it."""
    store = MemoryStore(tmp_path / "memory.db")
    await store.initialize()

    result = await RememberFactTool(store).invoke({})

    assert isinstance(result, ToolFailure)
    assert not result.retryable
    assert "content" in result.text
    assert await store.all_facts() == []


def test_schema_is_flat_with_one_required_argument() -> None:
    function = RememberFactTool.schema["function"]

    assert function["name"] == "remember_fact"
    parameters = function["parameters"]
    assert parameters["required"] == ["content"]  # type: ignore[index]
    assert "$defs" not in repr(parameters) and "$ref" not in repr(parameters)
